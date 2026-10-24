"""Find Sentinel-1 dates whose flood map is not comparable with the others.

    python scripts/otsu_fallback_check.py data/live data/sunamganj_2024

When the Otsu threshold fell outside -26..-12 dB, pipeline/02a_sentinel1_gee.py
used a fixed -18 dB instead (until 24 Oct 2026; such maps are now set unknown). This happens when open water is not dark, e.g.
wind-roughened haor water peaking near -15 dB (see processed/flood/otsu/*.png).
The fixed threshold then catches only a small tail of the water.

To compare dates fairly, this script measures the flooded share inside the
area seen on every date. A fallback date that drops far below its neighbours
is suspect. Writes <data>/results/otsu_fallback_check.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from safewindow import config

FALLBACK_DB = -18.0


def check(data_dir: Path) -> pd.DataFrame:
    flood = data_dir / "processed" / "flood"
    log = pd.read_csv(flood / "sentinel1_log.csv")
    maps = {}
    for day in log["date"]:
        with rasterio.open(flood / f"sentinel1_{day.replace('-', '')}.tif") as src:
            maps[day] = src.read(1)
    common = np.all([m != config.UNKNOWN for m in maps.values()], axis=0)
    out = log[["date", "relative_orbit", "otsu_db"]].copy()
    # logs written since 24 Oct 2026 carry a status; older ones logged the fallback as -18 dB
    out["fallback"] = log["status"] != "otsu" if "status" in log else out["otsu_db"] == FALLBACK_DB
    out["covered_pct"] = [round(float((maps[d] != config.UNKNOWN).mean() * 100), 1) for d in out["date"]]
    out["common_area_km2"] = round(common.sum() * config.GRID_RES_M ** 2 / 1e6, 1)
    out["common_flood_pct"] = [round(float((maps[d][common] == config.FLOODED).mean() * 100), 1) for d in out["date"]]
    neighbours = (out["common_flood_pct"].shift(1) + out["common_flood_pct"].shift(-1)) / 2
    out["neighbour_mean_pct"] = neighbours.round(1)
    return out


def main() -> None:
    pd.set_option("display.width", 200)
    for arg in sys.argv[1:] or [str(config.get_paths().data)]:
        data_dir = Path(arg)
        out = check(data_dir)
        (data_dir / "results").mkdir(exist_ok=True)
        out.to_csv(data_dir / "results" / "otsu_fallback_check.csv", index=False)
        print(f"\n{data_dir}  (area seen on every date: {out['common_area_km2'].iloc[0]} km2)")
        print(out.drop(columns="common_area_km2").to_string(index=False))


if __name__ == "__main__":
    main()
