"""How many days after NASA GPM IMERG rain does the flooded area respond? (docs/phase4_report.md, section 4.3)

    python scripts/rain_flood_lag.py <flood data dir> <rainfall_daily.csv>

Flood signal: the flooded share of the study area on each Sentinel-1 date
whose classified map covers at least MIN_COVER of the study area (so dates
are comparable). Rain signal: for each rainfall box, the total over a window
of W days ending L days before the radar date. For every (box, W, L), the
Spearman rank correlation with the flood signal is reported.

With roughly ten radar dates per flood this is exploratory: it shows the
timing that fits best, not a validated forecast rule.
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

from safewindow import config  # noqa: E402
from safewindow.flood import Grid  # noqa: E402

MIN_COVER = 0.95
WINDOWS = (1, 3, 5, 7, 10)
LAGS = range(0, 8)


def flood_series(data_dir: Path) -> pd.DataFrame:
    grid = Grid.load(data_dir / "processed" / "grid.json")
    inside = bb.study_zones(grid, gpd.read_file(data_dir / "processed" / "study_area.gpkg"))["all"]
    rows = []
    for tif in sorted((data_dir / "processed" / "flood").glob("sentinel1_*.tif")):
        with rasterio.open(tif) as src:
            m = src.read(1)[inside]
        known = m != config.UNKNOWN
        if known.mean() >= MIN_COVER:
            rows.append({"date": pd.Timestamp(tif.stem.split("_")[1]),
                         "flood_pct": round(float((m[known] == config.FLOODED).mean() * 100), 2)})
    return pd.DataFrame(rows)


def rain_total(rain: pd.Series, day: pd.Timestamp, window: int, lag: int) -> float:
    end = day - pd.Timedelta(days=lag)
    part = rain[(rain.index > end - pd.Timedelta(days=window)) & (rain.index <= end)]
    return float(part.sum()) if len(part) == window else np.nan


def main() -> None:
    data_dir, rain_csv = Path(sys.argv[1]), Path(sys.argv[2])
    flood = flood_series(data_dir)
    rain = pd.read_csv(rain_csv, parse_dates=["date"]).set_index("date")
    rows = []
    for box in [c for c in rain.columns if c.endswith("_mm")]:
        for w in WINDOWS:
            for lag in LAGS:
                x = flood["date"].map(lambda d: rain_total(rain[box], d, w, lag))
                ok = x.notna()
                if ok.sum() >= 5:
                    rho = pd.Series(x[ok].to_numpy()).corr(flood["flood_pct"][ok].reset_index(drop=True),
                                                         method="spearman")
                    rows.append({"box": box, "window_days": w, "lag_days": lag, "n_dates": int(ok.sum()),
                                 "spearman": round(float(rho), 2)})
    out = pd.DataFrame(rows).sort_values("spearman", ascending=False)
    pd.set_option("display.width", 200)
    print(f"{data_dir}: {len(flood)} radar dates with >= {MIN_COVER:.0%} coverage")
    print(flood.assign(date=flood["date"].dt.strftime("%Y-%m-%d")).to_string(index=False))
    print("\nbest rain windows (Spearman rho with flooded share):")
    print(out.head(8).to_string(index=False))
    for box in out["box"].unique():
        b = out[out["box"] == box]
        print(f"\n{box}: best lag per window -> " +
              ", ".join(f"W{w}: lag {g.iloc[0]['lag_days']} (rho {g.iloc[0]['spearman']})"
                        for w, g in b.groupby("window_days")))
    out.to_csv(data_dir / "results" / "rain_flood_lag.csv", index=False)


if __name__ == "__main__":
    main()
