"""Score a region's SafeWindow flood maps against independent flood analyses listed in a YAML file.

    $env:SAFEWINDOW_REGION="sunamganj_2024"; $env:SAFEWINDOW_DATA_DIR="data/sunamganj_2024"
    python scripts/benchmark_region.py regions/sunamganj_2024_benchmark.yaml

The 2022 benchmark (scripts/build_benchmark.py) is kept as published. This
script adds what a new flood needs:
  - each reference can be scored against several SafeWindow dates, and the
    date gap is reported, because the flood changes between images;
  - an `exclude` layer (e.g. cloud in an optical image) is left out of the comparison;
  - a prediction "D1+D2" is the union of two maps, for a cumulative reference.
Scores use the same rules as the 2022 benchmark (scripts/build_benchmark.py):
same confusion counts, metrics and 1 km block bootstrap.

Writes to <data>/: benchmark/<id>_reference.tif, benchmark.csv,
model_evaluation.csv/.json, benchmark_manifest.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_benchmark as bb  # noqa: E402

from safewindow import config  # noqa: E402
from safewindow.flood import Grid, write_flood_map  # noqa: E402


def load_spec(path: Path) -> dict:
    import yaml
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec["shapefile_dir"] = (path.parent / spec["shapefile_dir"]).resolve()
    return spec


def reference_mask(shp_dir: Path, ref: dict, grid: Grid, study: gpd.GeoDataFrame) -> np.ndarray:
    """0 dry, 1 flooded inside the analysed area; 255 outside it or inside `exclude`.
    `exclude_where` ({column: value}) keeps only the matching features of the
    exclude layer, e.g. Copernicus EMS footprints marked 'Not Analysed - No data'."""
    out = bb.reference_mask(shp_dir, ref, grid, study)
    if ref.get("exclude"):
        ex = gpd.read_file(shp_dir / f"{ref['exclude']}.shp")
        for col, value in (ref.get("exclude_where") or {}).items():
            ex = ex[ex[col].astype(str) == str(value)]
        if len(ex):
            out[bb.burn(ex, grid) == 1] = config.UNKNOWN
    return out


def prediction(paths, pred: str) -> tuple[np.ndarray, list[Path]]:
    """One SafeWindow map, or the union of several joined with '+'."""
    files = [paths.flood_dir / f"sentinel1_{d.replace('-', '')}.tif" for d in pred.split("+")]
    maps = []
    for f in files:
        with rasterio.open(f) as src:
            maps.append(src.read(1))
    flooded = np.any([m == config.FLOODED for m in maps], axis=0)
    known = np.any([m != config.UNKNOWN for m in maps], axis=0)
    out = np.full(maps[0].shape, config.UNKNOWN, dtype="uint8")
    out[known] = config.DRY
    out[flooded] = config.FLOODED
    return out, files


def gap_days(ref_date: str, pred: str) -> int:
    """Days from the reference to the prediction (negative: our map is earlier). For unions, the largest gap."""
    refs = [date.fromisoformat(d) for d in ref_date.split("+")]
    preds = [date.fromisoformat(d) for d in pred.split("+")]
    return max(((p - r).days for r in refs for p in preds), key=abs)


def score(pred, reference, mask, grid) -> dict:
    tp, fp, fn, tn = bb.confusion(pred, reference, mask)
    return {"area_km2": round(mask.sum() * grid.res ** 2 / 1e6, 1), "pixels_compared": int(mask.sum()),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            **{k: round(float(v), 4) for k, v in bb.scores(tp, fp, fn, tn).items()}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("references", type=Path, help="YAML list of references, e.g. regions/sunamganj_2024_benchmark.yaml")
    args = ap.parse_args()
    spec = load_spec(args.references)
    paths = config.get_paths().ensure()
    out_dir = paths.data
    (out_dir / "benchmark").mkdir(exist_ok=True)
    grid = Grid.load(paths.grid)
    study = gpd.read_file(paths.study_area)
    zones = bb.study_zones(grid, study)

    rows, eval_json, manifest_refs = [], [], []
    for ref in spec["references"]:
        shp_dir = spec["shapefile_dir"] / ref["dir"] if ref.get("dir") else spec["shapefile_dir"]
        reference = reference_mask(shp_dir, ref, grid, study)
        ref_tif = out_dir / "benchmark" / f"{ref['id']}_reference.tif"
        write_flood_map(reference, grid, ref_tif)
        preds = []
        for pred_date in ref["predictions"]:
            pred, files = prediction(paths, pred_date)
            valid_all = (pred != config.UNKNOWN) & (reference != config.UNKNOWN)
            base = {"reference": ref["id"], "tier": ref["tier"], "sensor": ref["sensor"], "date": ref["date"],
                    "pred_date": pred_date, "gap_days": gap_days(ref["date"], pred_date)}
            for zone, zmask in zones.items():
                mask = valid_all & zmask
                if not mask.any():
                    continue
                row = {**base, "zone": zone, **score(pred, reference, mask, grid)}
                if zone == "all":
                    ci = bb.bootstrap_ci(pred, reference, mask)
                    row.update({k: str(v) for k, v in ci.items()})
                    eval_json.append({**row, **ci})
                rows.append(row)
            preds.append({"pred_date": pred_date, "files": [f.relative_to(out_dir).as_posix() for f in files],
                          "sha256": [bb.sha256(f) for f in files]})
        manifest_refs.append({**{k: v for k, v in ref.items() if k != "predictions"},
                              "tier_meaning": spec["tiers"][ref["tier"]],
                              "reference_raster": ref_tif.relative_to(out_dir).as_posix(),
                              "reference_sha256": bb.sha256(ref_tif), "predictions": preds,
                              "analysed_share_of_study_area_pct": round(float(
                                  100 * ((reference != config.UNKNOWN) & zones["all"]).sum() / zones["all"].sum()), 1)})

    ev = pd.DataFrame(rows)
    ev[["reference", "tier", "sensor", "date", "pred_date", "gap_days", "zone", "pixels_compared",
        "tp", "fp", "fn", "tn"]].to_csv(out_dir / "benchmark.csv", index=False)
    ev.drop(columns=["tp", "fp", "fn", "tn", "pixels_compared"]).to_csv(out_dir / "model_evaluation.csv", index=False)
    (out_dir / "model_evaluation.json").write_text(json.dumps({
        "task": "per-pixel flood / not-flood agreement of SafeWindow Sentinel-1 maps with independent flood analyses",
        "region": config.REGION.id, "tiers": spec["tiers"], "details": eval_json,
        "caveat": "References are preliminary satellite analyses, not field-validated ground truth. "
                  "Scores against references from another date include real flood change.",
    }, indent=2), encoding="utf-8")
    (out_dir / "benchmark_manifest.json").write_text(json.dumps({
        "name": f"SafeWindow flood-extent benchmark, {config.REGION.name}",
        "region": config.REGION.id, "event_code": spec.get("event_code"), "publisher": spec.get("publisher"),
        "license": spec.get("license"), "archives": spec.get("archives", []),
        "independence_note": "No reference was used to build or tune SafeWindow; the method and thresholds are "
                             "unchanged from the 2022 study.",
        "tiers": spec["tiers"], "references": manifest_refs,
    }, indent=2, default=str), encoding="utf-8")
    pd.set_option("display.width", 250)
    cols = ["reference", "tier", "pred_date", "gap_days", "area_km2", "iou", "iou_ci95", "precision", "recall"]
    print(ev[ev["zone"] == "all"][cols].to_string(index=False))


if __name__ == "__main__":
    main()
