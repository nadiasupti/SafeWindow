"""Score two versions of the flood maps against the same benchmark references.

    python scripts/ablation_compare.py <base data dir> <variant data dir> [--label "no NASADEM slope mask"]

Uses the references and prediction dates recorded in <base>/benchmark_manifest.json
(written by scripts/build_benchmark.py or scripts/benchmark_region.py). Both
versions are scored on exactly the same pixels: inside the study area, inside
the reference's analysed area, and classified in both versions. This measures
what one input (e.g. NASA NASADEM) changes, holding everything else fixed.
"""
from __future__ import annotations

import argparse
import json
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


def load_map(data_dir: Path, pred_date: str) -> np.ndarray:
    """One flood map, or the union of several joined with '+' (as in benchmark_region)."""
    maps = []
    for day in pred_date.split("+"):
        with rasterio.open(data_dir / "processed" / "flood" / f"sentinel1_{day.replace('-', '')}.tif") as src:
            maps.append(src.read(1))
    flooded = np.any([m == config.FLOODED for m in maps], axis=0)
    known = np.any([m != config.UNKNOWN for m in maps], axis=0)
    out = np.full(maps[0].shape, config.UNKNOWN, dtype="uint8")
    out[known] = config.DRY
    out[flooded] = config.FLOODED
    return out


def pairs(manifest: dict):
    """(reference id, tier, reference raster, prediction date) for every scored pair."""
    for ref in manifest["references"]:
        if "predictions" in ref:                      # benchmark_region.py
            for p in ref["predictions"]:
                yield ref["id"], ref["tier"], ref["reference_raster"], p["pred_date"]
        else:                                         # build_benchmark.py (2022)
            yield ref["id"], ref["tier"], ref["reference_raster"], ref["pred_date"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", type=Path)
    ap.add_argument("variant", type=Path)
    ap.add_argument("--label", default="variant")
    args = ap.parse_args()

    manifest = json.loads((args.base / "benchmark_manifest.json").read_text(encoding="utf-8"))
    grid = Grid.load(args.base / "processed" / "grid.json")
    inside = bb.study_zones(grid, gpd.read_file(args.base / "processed" / "study_area.gpkg"))["all"]
    rows = []
    for ref_id, tier, raster, pred_date in pairs(manifest):
        try:
            variant = load_map(args.variant, pred_date)
        except rasterio.errors.RasterioIOError:
            continue                                  # date not built in the variant
        base = load_map(args.base, pred_date)
        with rasterio.open(args.base / raster) as src:
            ref = src.read(1)
        mask = inside & (ref != config.UNKNOWN) & (base != config.UNKNOWN) & (variant != config.UNKNOWN)
        if not mask.any():
            continue
        row = {"reference": ref_id, "tier": tier, "pred_date": pred_date,
               "km2": round(mask.sum() * grid.res ** 2 / 1e6, 1)}
        for name, pred in (("base", base), ("variant", variant)):
            s = bb.scores(*bb.confusion(pred, ref, mask))
            row.update({f"{k}_{name}": round(float(s[k]), 4) for k in ("iou", "precision", "recall")})
            row[f"flood_km2_{name}"] = round(float((pred[mask] == config.FLOODED).sum()) * grid.res ** 2 / 1e6, 1)
        row["iou_change"] = round(row["iou_base"] - row["iou_variant"], 4)
        rows.append(row)
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"base = published method; variant = {args.label}; iou_change = base - variant")
    print(out.to_string(index=False))
    out.to_csv(args.variant / "ablation_compare.csv", index=False)


if __name__ == "__main__":
    main()
