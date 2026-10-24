"""NASA-ISRO NISAR (L-band) water maps on the SafeWindow grid, compared with SafeWindow's Sentinel-1 (C-band) maps.

    $env:SAFEWINDOW_REGION="punjab_trimmu_2026"; $env:SAFEWINDOW_DATA_DIR="data/punjab_trimmu_2026"
    python scripts/nisar_compare.py data/experiments/nisar_trimmu_2026 \
        --pair 2026-07-24:2026-06-18:2026-07-25 --pair 2026-07-12:2026-06-18:2026-07-13

Each --pair is NISAR flood date : NISAR baseline date (same track) : SafeWindow
Sentinel-1 date. Needs an Earthdata login saved with earthaccess.

NISAR GCOV granules are about 6.5 GB; only the HHHH chunks over the study
area are read over HTTPS (HDF5 partial reads). HH gamma0 power is averaged
onto the 20 m grid and converted to dB. Water is HH below the Otsu threshold,
chosen with the same rule as for Sentinel-1 (choose_threshold in
pipeline/02a_sentinel1_gee.py), so nothing is tuned for NISAR. "New water" is
water on the flood date that was not water on the baseline date.

No independent flood map exists for this event, so this is agreement between
two radars on different satellites and bands, not validation against ground truth.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from safewindow import config
from safewindow.flood import Grid, write_flood_map
from safewindow.places import load_study_area

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("s1", ROOT / "pipeline" / "02a_sentinel1_gee.py")
s1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s1)

GCOV = "NISAR_L2_GCOV_PROVISIONAL_V1"
MARGIN_M = 200


def hh_on_grid(earthaccess, day: str, grid: Grid, bbox, attempts: int = 3) -> tuple[np.ndarray, str]:
    """hh_on_grid_once, retried: long HTTPS range reads of 6.5 GB files can be cut by the server.
    Only network and read errors are retried; anything else (e.g. no overlap) fails at once."""
    import time
    transient: tuple[type[BaseException], ...] = (OSError, RuntimeError)
    try:
        import aiohttp
        transient += (aiohttp.ClientError,)               # payload and connection errors from fsspec
    except ImportError:
        pass
    for attempt in range(1, attempts + 1):
        try:
            return hh_on_grid_once(earthaccess, day, grid, bbox)
        except transient as exc:
            if attempt == attempts:
                raise
            print(f"  {day}: read failed ({type(exc).__name__}), retrying in {30 * attempt}s", flush=True)
            time.sleep(30 * attempt)


def hh_on_grid_once(earthaccess, day: str, grid: Grid, bbox) -> tuple[np.ndarray, str]:
    """HH gamma0 (dB) of the NISAR granule on `day`, averaged onto the grid (NaN where no data)."""
    import h5py
    res = earthaccess.search_data(short_name=GCOV, bounding_box=bbox, temporal=(day, day))
    if not res:
        raise SystemExit(f"no NISAR GCOV granule on {day}")
    granule = res[0]["umm"]["GranuleUR"]
    url = next(u for u in res[0].data_links() if u.endswith(".h5"))
    with h5py.File(earthaccess.open([url])[0], "r") as h:
        g = h["science/LSAR/GCOV/grids/frequencyA"]
        src_crs = f"EPSG:{int(g['projection'].attrs['epsg_code'])}"
        x, y = g["xCoordinates"][:], g["yCoordinates"][:]
        # the project grid's bounds in the granule's projection (frames can be in a neighbouring UTM zone)
        left, bottom, right, top = transform_bounds(grid.crs, src_crs, *grid.bounds)
        cols = np.where((x >= left - MARGIN_M) & (x <= right + MARGIN_M))[0]
        rows = np.where((y >= bottom - MARGIN_M) & (y <= top + MARGIN_M))[0]
        c0, c1, r0, r1 = cols.min(), cols.max() + 1, rows.min(), rows.max() + 1
        power = g["HHHH"][r0:r1, c0:c1].astype("float32")
    dx, dy = x[1] - x[0], y[1] - y[0]               # dy < 0 (north-up)
    src_transform = from_origin(x[c0] - dx / 2, y[r0] - dy / 2, dx, -dy)
    out = np.full((grid.height, grid.width), np.nan, dtype="float32")
    reproject(power, out, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan, resampling=Resampling.average)
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10 * np.log10(out)
    db[~np.isfinite(db)] = np.nan
    print(f"  {day}: {granule}, native spacing {abs(dx):.1f} m, read {r1 - r0} x {c1 - c0} px")
    return db, granule


def water_map(db: np.ndarray, inside: np.ndarray, hist_png: Path, day: str) -> tuple[np.ndarray, float | None, str]:
    vals = db[inside & np.isfinite(db)]
    counts, edges = np.histogram(vals, bins=np.arange(-40, 10.25, 0.25))
    centers = (edges[:-1] + edges[1:]) / 2
    t, status = s1.choose_threshold(counts.astype(float), centers)
    if t is not None:
        s1.save_histogram(counts, centers, t, day, hist_png, usable=status == "otsu", sensor="NISAR L-band HH")
    out = np.full(db.shape, config.UNKNOWN, dtype="uint8")
    if status == "otsu":
        known = np.isfinite(db)
        out[known] = config.DRY
        out[known & (db < t)] = config.FLOODED
    return out, t, status


def agreement(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> dict:
    """IoU, and how much of each map's flood the other one confirms."""
    m = mask & (a != config.UNKNOWN) & (b != config.UNKNOWN)
    fa, fb = (a == config.FLOODED) & m, (b == config.FLOODED) & m
    both, either = (fa & fb).sum(), (fa | fb).sum()
    km2 = config.GRID_RES_M ** 2 / 1e6
    return {"compared_km2": round(m.sum() * km2, 1), "a_km2": round(fa.sum() * km2, 1), "b_km2": round(fb.sum() * km2, 1),
            "iou": round(both / either, 3) if either else None,
            "share_of_a_in_b": round(both / fa.sum(), 3) if fa.sum() else None,
            "share_of_b_in_a": round(both / fb.sum(), 3) if fb.sum() else None}


def main() -> None:
    import earthaccess
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--pair", action="append", required=True, help="NISAR_DATE:NISAR_BASELINE_DATE:S1_DATE")
    args = ap.parse_args()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_benchmark as bb

    earthaccess.login(strategy="netrc")
    paths = config.get_paths()
    grid = Grid.load(paths.grid)
    study = load_study_area(paths)
    bbox = tuple(study.to_crs(config.CRS_WGS84).total_bounds)
    inside = bb.study_zones(grid, study.to_crs(grid.crs))["all"]
    flood_dir = args.out / "processed" / "flood"
    flood_dir.mkdir(parents=True, exist_ok=True)

    cache, results = {}, []
    for pair in args.pair:
        day, base_day, s1_day = pair.split(":")
        maps = {}
        for d in (day, base_day):
            if d not in cache:
                db, granule = hh_on_grid(earthaccess, d, grid, bbox)
                w, t, status = water_map(db, inside, args.out / "histograms" / f"nisar_hh_{d}.png", d)
                write_flood_map(w, grid, flood_dir / f"nisar_water_{d.replace('-', '')}.tif")
                cache[d] = (w, t, status, granule)
            maps[d] = cache[d][0]
        wet, base = maps[day], maps[base_day]
        new = np.full(wet.shape, config.UNKNOWN, dtype="uint8")
        known = (wet != config.UNKNOWN) & (base != config.UNKNOWN)
        new[known] = config.DRY
        new[known & (wet == config.FLOODED) & (base != config.FLOODED)] = config.FLOODED
        write_flood_map(new, grid, flood_dir / f"nisar_newwater_{day.replace('-', '')}.tif")

        with rasterio.open(paths.flood_dir / f"sentinel1_{s1_day.replace('-', '')}.tif") as src:
            sw = src.read(1)
        # how much of SafeWindow's flood NISAR already saw as water on the baseline date
        # (pre-existing water such as irrigated paddies, if the baseline was before the flood)
        sw_flood = (sw == config.FLOODED) & inside & (base != config.UNKNOWN)
        pre_existing = round(float((base[sw_flood] == config.FLOODED).mean()), 3) if sw_flood.any() else None
        row = {"nisar_date": day, "nisar_baseline": base_day, "sentinel1_date": s1_day,
               "nisar_threshold_db": None if cache[day][1] is None else round(cache[day][1], 2),
               "nisar_status": cache[day][2], "nisar_granule": cache[day][3],
               "new_water_vs_safewindow": agreement(new, sw, inside),
               # SafeWindow maps water new since the dry season; in a monsoon wetland that is most
               # water, so NISAR's water on the day (no baseline) is also compared
               "all_water_vs_safewindow": agreement(wet, sw, inside),
               "share_of_safewindow_flood_already_water_on_baseline": pre_existing}
        results.append(row)
        print(json.dumps(row, indent=2), flush=True)
        # saved after every pair, so a later network failure does not lose finished pairs
        (args.out / "nisar_compare.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (args.out / "nisar_compare.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
