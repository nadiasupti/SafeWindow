"""Score SafeWindow Sentinel-1 flood maps against independent UNOSAT references.

    python scripts/build_benchmark.py <unosat_shp_dir> [--archive FL20220525BGD_SHP.zip] [--data data/live]

Download the archive (337 MB) from SOURCE_URL below and extract the four
Chaohu1_20220525_* and RCM1_20220618_* AnalysisExtent / FloodExtent shapefiles.

The references are UNOSAT analyses from sensors other than Sentinel-1
(Chaohu-1 on 25 May 2022, RCM-1 on 18 June 2022), taken from event
FL20220525BGD. Our maps are produced without using them, with no tuning on
these dates: the Otsu threshold, the 3 dB change rule and the slope mask are
fixed in pipeline/02a_sentinel1_gee.py.

Writes to <data>/:
  benchmark/<id>_reference.tif   reference flood mask on the project grid
  benchmark.csv                  confusion counts per reference date and upazila
  benchmark_manifest.json        reference sources, split strategy, checksums
  model_evaluation.csv/.json     IoU, precision, recall, F1, accuracy, bootstrap CI

UNOSAT states these products are preliminary and not field validated. This is
agreement between two satellite analyses, not ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

from safewindow import config
from safewindow.flood import Grid, write_flood_map

REFERENCES = [
    {"id": "chaohu1_20220525", "date": "2022-05-25", "sensor": "Chaohu-1 SAR", "stem": "Chaohu1_20220525"},
    {"id": "rcm1_20220618", "date": "2022-06-18", "sensor": "RCM-1 SAR", "stem": "RCM1_20220618"},
]
SOURCE_URL = "https://unosat-maps.web.cern.ch/BD/FL20220525BGD/FL20220525BGD_SHP.zip"
BLOCK = 50          # 1 km blocks for the bootstrap
N_BOOT = 500
SEED = 20221018


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def burn(gdf: gpd.GeoDataFrame, grid: Grid) -> np.ndarray:
    gdf = gdf.to_crs(grid.crs)
    shapes = [(g, 1) for g in gdf.geometry if g is not None and not g.is_empty]
    if not shapes:
        return np.zeros((grid.height, grid.width), "uint8")
    return rasterize(shapes, out_shape=(grid.height, grid.width), transform=grid.transform,
                     fill=0, dtype="uint8", all_touched=False)


def reference_mask(shp_dir: Path, ref: dict, grid: Grid, study: gpd.GeoDataFrame) -> np.ndarray:
    """0 dry, 1 flooded inside UNOSAT's analysed area; 255 outside it."""
    bbox = tuple(study.to_crs(4326).total_bounds)
    analysis = gpd.read_file(shp_dir / f"{ref['stem']}_AnalysisExtent_Sylhet.shp")
    flood = gpd.read_file(shp_dir / f"{ref['stem']}_FloodExtent_Sylhet.shp", bbox=bbox)
    analysed, flooded = burn(analysis, grid), burn(flood, grid)
    out = np.full(analysed.shape, config.UNKNOWN, dtype="uint8")
    out[analysed == 1] = config.DRY
    out[flooded == 1] = config.FLOODED
    return out


def scores(tp: float, fp: float, fn: float, tn: float) -> dict:
    n = tp + fp + fn + tn
    return {
        "iou": tp / (tp + fp + fn) if tp + fp + fn else np.nan,
        "precision": tp / (tp + fp) if tp + fp else np.nan,
        "recall": tp / (tp + fn) if tp + fn else np.nan,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else np.nan,
        "accuracy": (tp + tn) / n if n else np.nan,
    }


def confusion(pred: np.ndarray, ref: np.ndarray, mask: np.ndarray) -> tuple[int, int, int, int]:
    p, r = pred[mask] == config.FLOODED, ref[mask] == config.FLOODED
    return int((p & r).sum()), int((p & ~r).sum()), int((~p & r).sum()), int((~p & ~r).sum())


def bootstrap_ci(pred, ref, valid) -> dict:
    """95% interval from resampling 1 km blocks (pixels are spatially correlated)."""
    h, w = pred.shape
    by, bx = -(-h // BLOCK), -(-w // BLOCK)
    p, r = (pred == config.FLOODED) & valid, (ref == config.FLOODED) & valid
    stats = np.zeros((by, bx, 4))
    for i in range(by):
        for j in range(bx):
            sl = (slice(i * BLOCK, (i + 1) * BLOCK), slice(j * BLOCK, (j + 1) * BLOCK))
            v, pp, rr = valid[sl], p[sl], r[sl]
            stats[i, j] = [(pp & rr).sum(), (pp & ~rr & v).sum(), (~pp & rr & v).sum(), (~pp & ~rr & v).sum()]
    flat = stats.reshape(-1, 4)
    flat = flat[flat.sum(axis=1) > 0]
    rng = np.random.default_rng(SEED)
    draws = {k: [] for k in ("iou", "precision", "recall", "f1")}
    for _ in range(N_BOOT):
        tp, fp, fn, tn = flat[rng.integers(0, len(flat), len(flat))].sum(axis=0)
        s = scores(tp, fp, fn, tn)
        for k in draws:
            draws[k].append(s[k])
    return {f"{k}_ci95": [round(float(np.nanpercentile(v, 2.5)), 4), round(float(np.nanpercentile(v, 97.5)), 4)]
            for k, v in draws.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shp_dir", type=Path, help="folder with the extracted UNOSAT shapefiles")
    ap.add_argument("--archive", type=Path, help="the downloaded UNOSAT zip, to record its SHA-256")
    ap.add_argument("--data", default=None, help="data directory (default: config data dir)")
    args = ap.parse_args()

    paths = config.get_paths().ensure() if args.data is None else config.Paths(Path(args.data).resolve())
    out_dir = paths.data
    (out_dir / "benchmark").mkdir(exist_ok=True)
    grid = Grid.load(paths.grid)
    study = gpd.read_file(paths.study_area)
    upazilas = study.to_crs(grid.crs)

    rows, eval_rows, eval_json, manifest_refs = [], [], [], []
    for ref in REFERENCES:
        pred_path = paths.flood_dir / f"sentinel1_{ref['date'].replace('-', '')}.tif"
        with rasterio.open(pred_path) as src:
            pred = src.read(1)
        reference = reference_mask(args.shp_dir, ref, grid, study)
        ref_tif = out_dir / "benchmark" / f"{ref['id']}_reference.tif"
        write_flood_map(reference, grid, ref_tif)

        valid_all = (pred != config.UNKNOWN) & (reference != config.UNKNOWN)
        zones = {"all": np.ones_like(valid_all)}
        for name, geom in zip(upazilas["upazila"], upazilas.geometry):
            zones[name] = rasterize([(geom, 1)], out_shape=pred.shape, transform=grid.transform,
                                    fill=0, dtype="uint8").astype(bool)
        zones["all"] = np.any([z for k, z in zones.items() if k != "all"], axis=0)

        for zone, zmask in zones.items():
            mask = valid_all & zmask
            if not mask.any():
                continue
            tp, fp, fn, tn = confusion(pred, reference, mask)
            s = scores(tp, fp, fn, tn)
            rows.append({"reference": ref["id"], "date": ref["date"], "sensor": ref["sensor"], "zone": zone,
                         "pixels_compared": int(mask.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn})
            row = {"reference": ref["id"], "date": ref["date"], "zone": zone,
                   "area_km2": round(mask.sum() * grid.res ** 2 / 1e6, 1), **{k: round(float(v), 4) for k, v in s.items()}}
            if zone == "all":
                ci = bootstrap_ci(pred, reference, mask)
                row.update({k: str(v) for k, v in ci.items()})
                eval_json.append({**row, **ci, "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}})
            eval_rows.append(row)
        manifest_refs.append({**ref, "reference_raster": ref_tif.relative_to(out_dir).as_posix(),
                              "reference_sha256": sha256(ref_tif),
                              "prediction": pred_path.relative_to(out_dir).as_posix(),
                              "prediction_sha256": sha256(pred_path),
                              "analysed_share_of_study_area_pct": round(float(
                                  100 * ((reference != config.UNKNOWN) & zones["all"]).sum() / zones["all"].sum()), 1)})

    pd.DataFrame(rows).to_csv(out_dir / "benchmark.csv", index=False)
    ev = pd.DataFrame(eval_rows)
    ev.to_csv(out_dir / "model_evaluation.csv", index=False)

    allz = [r for r in eval_json]
    headline = {r["reference"]: {k: r[k] for k in ("iou", "precision", "recall", "f1", "accuracy")} for r in allz}
    (out_dir / "model_evaluation.json").write_text(json.dumps({
        "task": "per-pixel flood / not-flood agreement of SafeWindow Sentinel-1 maps with UNOSAT SAR analyses",
        "metrics": headline,
        "details": allz,
        "error_distribution": "see model_evaluation.csv: same metrics per upazila zone",
        "caveat": "References are independent satellite analyses (preliminary, not field validated), not ground truth.",
    }, indent=2), encoding="utf-8")
    (out_dir / "benchmark_manifest.json").write_text(json.dumps({
        "name": "SafeWindow Sunamganj flood-extent benchmark",
        "region": "Sunamganj Sadar, Chhatak, Dowarabazar (Sunamganj and Sylhet districts, Bangladesh)",
        "independent_evaluation": True,
        "independence_note": "Reference sensors (Chaohu-1, RCM-1) differ from Sentinel-1; the UNOSAT analyses were produced by "
                             "UNITAR-UNOSAT, not by this team.",
        "split_strategy": "Fixed temporal hold-out: both reference dates (25 May, 18 Jun 2022) are test-only. The method has no "
                          "trained parameters; thresholds were fixed before scoring and not tuned on these dates. "
                          "Geographic strata: the three upazilas, reported separately.",
        "source_archive": {"url": SOURCE_URL, "event_code": "FL20220525BGD", "publisher": "UNITAR-UNOSAT",
                           "license": "CC BY-SA (as listed on HDX)",
                           "sha256": sha256(args.archive) if args.archive else None},
        "references": manifest_refs,
        "limitations": ["Two reference dates only.", "Preliminary UNOSAT products, not field validated.",
                        "UNOSAT flood extent (not total water extent) is used, because SafeWindow also leaves out permanent water."],
    }, indent=2), encoding="utf-8")
    print(ev[ev["zone"] == "all"].to_string(index=False))
    print(ev.to_string(index=False))


if __name__ == "__main__":
    main()
