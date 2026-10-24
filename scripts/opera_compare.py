"""Put NASA OPERA DSWx-S1 water maps on the SafeWindow grid, as "new water" maps (docs/phase4_report.md, section 4.4).

    python scripts/opera_compare.py <out dir> --dates 2025-08-28 2025-09-01 --dry-start 2025-04-01 --dry-end 2025-05-31
    python scripts/ablation_compare.py <region data dir> <out dir> --label "NASA OPERA DSWx-S1"

Needs an Earthdata login saved with earthaccess (persist=True). Uses the grid
and study area of SAFEWINDOW_DATA_DIR.

DSWx-S1 B01_WTR: 0 not water, 1 open water, 3 inundated vegetation, 255 no data.
OPERA maps all water, while SafeWindow maps water that is new compared with the
dry season. So OPERA "new water" = water on the flood date AND not water on
most of the dry-season dates. Written as <out>/processed/flood/sentinel1_<date>.tif
(0 dry, 1 new water, 255 unknown) so scripts/ablation_compare.py can score it
against the same references, on the same pixels, as SafeWindow.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from safewindow import config
from safewindow.flood import Grid, write_flood_map
from safewindow.places import load_study_area

WATER, NODATA = (1, 3), 255


def granules(earthaccess, bbox, day_from: str, day_to: str):
    return earthaccess.search_data(short_name="OPERA_L3_DSWX-S1_V1", bounding_box=bbox, temporal=(day_from, day_to))


def wtr_on_grid(earthaccess, results, grid: Grid, cache: Path) -> dict[str, np.ndarray]:
    """Download the B01_WTR layers and mosaic them per acquisition date onto the grid.
    Returns {date: array} with 1 water, 0 not water, 255 no data."""
    by_day: dict[str, list] = {}
    for g in results:
        day = g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10]
        by_day.setdefault(day, []).append(g)
    out = {}
    for day, gs in sorted(by_day.items()):
        links = [u for g in gs for u in g.data_links() if u.endswith("_B01_WTR.tif")]
        files = earthaccess.download(links, str(cache / day), show_progress=False)
        water = np.zeros((grid.height, grid.width), bool)
        seen = np.zeros((grid.height, grid.width), bool)
        for f in files:
            with rasterio.open(f) as src:
                tile = np.full((grid.height, grid.width), NODATA, dtype="uint8")
                reproject(rasterio.band(src, 1), tile, src_nodata=None, dst_transform=grid.transform,
                          dst_crs=grid.crs, resampling=Resampling.nearest)
            valid = (tile != NODATA) & ~np.isin(tile, (250, 251, 252, 253, 254))
            water |= valid & np.isin(tile, WATER)
            seen |= valid
        arr = np.full((grid.height, grid.width), NODATA, dtype="uint8")
        arr[seen] = 0
        arr[water] = 1
        out[day] = arr
        print(f"  OPERA {day}: {len(files)} tiles, water {water.sum() * grid.res ** 2 / 1e6:.0f} km2, "
              f"seen {seen.mean() * 100:.0f}% of grid")
    return out


def main() -> None:
    import earthaccess
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--dry-start", required=True)
    ap.add_argument("--dry-end", required=True)
    args = ap.parse_args()

    earthaccess.login(strategy="netrc")
    paths = config.get_paths()
    grid = Grid.load(paths.grid)
    bbox = tuple(load_study_area(paths).to_crs(config.CRS_WGS84).total_bounds)
    cache = args.out / "opera_raw"

    print("dry season ...")
    dry = wtr_on_grid(earthaccess, granules(earthaccess, bbox, args.dry_start, args.dry_end), grid, cache)
    stack = np.stack(list(dry.values()))
    seen = (stack != NODATA).sum(0)
    usual_water = (stack == 1).sum(0) > np.maximum(seen, 1) / 2      # water on most dry dates
    print(f"  {len(dry)} dry dates; usual water {usual_water.sum() * grid.res ** 2 / 1e6:.0f} km2")

    (args.out / "processed" / "flood").mkdir(parents=True, exist_ok=True)
    for name in ("grid.json", "study_area.gpkg"):
        shutil.copy2(paths.processed / name, args.out / "processed" / name)
    for day in args.dates:
        wet = wtr_on_grid(earthaccess, granules(earthaccess, bbox, day, day), grid, cache).get(day)
        if wet is None:
            print(f"  no OPERA granule on {day}")
            continue
        new = np.full(wet.shape, config.UNKNOWN, dtype="uint8")
        known = (wet != NODATA) & (seen > 0)
        new[known] = config.DRY
        new[known & (wet == 1) & ~usual_water] = config.FLOODED
        write_flood_map(new, grid, args.out / "processed" / "flood" / f"sentinel1_{day.replace('-', '')}.tif")
        print(f"  {day}: OPERA new water {(new == config.FLOODED).sum() * grid.res ** 2 / 1e6:.0f} km2")


if __name__ == "__main__":
    main()
