"""Which DEM best redraws an observed flood from its water level: NASA NASADEM or Copernicus GLO-30?

    $env:SAFEWINDOW_DATA_DIR="data/live"; python scripts/dem_bathtub_check.py data/experiments/dem_check_2022

pipeline/02d_dem_gapfill.py estimates flood between radar dates with a
"bathtub" rule: the water level is the median ground height at the edge of
the observed flood, and every pixel lower than that level is flooded. That
only works if the DEM represents the floodplain well. This check takes every
radar date that covers the whole study area, derives the level from that
date's own flood edge, redraws the flood from the DEM alone and scores it
against the observed map (IoU). Both DEMs are downloaded through Earth Engine
onto the project grid. It measures the DEMs, not the radar maps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_benchmark as bb  # noqa: E402

from safewindow import config, gee  # noqa: E402
from safewindow.flood import Grid  # noqa: E402

DEMS = {
    "NASADEM (NASA)": lambda ee: ee.Image("NASA/NASADEM_HGT/001").select("elevation").toFloat(),
    "Copernicus GLO-30 (ESA)": lambda ee: ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic().toFloat(),
}
MIN_COVER = 0.95
MIN_EDGE_PX = 100          # 02d_dem_gapfill.py skips dates with fewer flood-edge pixels


def edge_pixels(flood: np.ndarray) -> np.ndarray:
    """Flooded pixels with at least one dry 4-neighbour (as in 02d_dem_gapfill.py)."""
    f, d = flood == config.FLOODED, flood == config.DRY
    nb = np.zeros_like(d)
    nb[1:, :] |= d[:-1, :]
    nb[:-1, :] |= d[1:, :]
    nb[:, 1:] |= d[:, :-1]
    nb[:, :-1] |= d[:, 1:]
    return f & nb


def main() -> None:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = config.get_paths()
    grid = Grid.load(paths.grid)
    inside = bb.study_zones(grid, gpd.read_file(paths.study_area))["all"]
    ee = gee.init()
    region = gee.study_area_geometry(paths)
    dems = {}
    for name, make in DEMS.items():
        tif = out_dir / f"{name.split()[0].lower()}.tif"
        if not tif.exists():
            gee.download_to_grid(make(ee), grid, tif, name.split()[0].lower(), region=region,
                                 dtype="float32", nodata=-9999)
        with rasterio.open(tif) as src:
            dem = src.read(1).astype("float64")
        dem[dem <= -9999] = np.nan
        dems[name] = dem

    rows = []
    for tif in sorted(paths.flood_dir.glob("sentinel1_*.tif")):
        with rasterio.open(tif) as src:
            obs = src.read(1)
        known = inside & (obs != config.UNKNOWN)
        if known.sum() < MIN_COVER * inside.sum():
            continue
        edges = edge_pixels(obs) & inside
        for name, dem in dems.items():
            ok = known & np.isfinite(dem)
            if (edges & ok).sum() < MIN_EDGE_PX:        # same rule as 02d_dem_gapfill.py
                print(f"{tif.stem}: too few flood-edge pixels for {name}, skipped")
                continue
            level = float(np.median(dem[edges & ok]))
            drawn = (dem <= level) & ok
            truth = (obs == config.FLOODED) & ok
            inter, union = (drawn & truth).sum(), (drawn | truth).sum()
            rows.append({"date": tif.stem.split("_")[1], "dem": name, "level_m": round(level, 2),
                         "observed_flood_pct": round(float(truth.sum() / ok.sum() * 100), 1),
                         "redrawn_flood_pct": round(float(drawn.sum() / ok.sum() * 100), 1),
                         "iou": round(float(inter / union), 3) if union else None})
    out = pd.DataFrame(rows)
    out.to_csv(out_dir / "dem_bathtub_check.csv", index=False)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    print("\nmean IoU by DEM:")
    print(out.groupby("dem")["iou"].agg(["mean", "min", "max", "count"]).round(3).to_string())


if __name__ == "__main__":
    main()
