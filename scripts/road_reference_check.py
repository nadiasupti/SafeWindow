"""Compare SafeWindow road cuts with an independent map of flood-affected roads.

    $env:SAFEWINDOW_REGION="sunamganj_2024"; $env:SAFEWINDOW_DATA_DIR="data/sunamganj_2024"
    python scripts/road_reference_check.py <affected_roads.shp> <analysis_extent.shp> --dates 2024-06-29 2024-06-19

For 2024 the reference is UNOSAT's SAOCOM_20240626_PotentiallyAffectedRoad_Sylhet
(roads in water on the 26 June SAOCOM image). Both directions are reported,
inside the reference's analysed area and the study area:

  reference -> model  of the affected road km, how much our model has cut / unknown / open
  model -> reference  of our cut road km, how much lies on an affected road

A road segment of ours is matched to the reference when they overlap within
MATCH_M metres (the two road datasets are digitised separately). This is
agreement between two satellite analyses, not ground truth.

Writes <data>/results/road_reference_check.csv.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

from safewindow import config
from safewindow.places import load_study_area
from safewindow.roads import load_network

MATCH_M = 30


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("affected_roads", type=Path)
    ap.add_argument("analysis_extent", type=Path)
    ap.add_argument("--dates", nargs="+", required=True, help="SafeWindow dates to compare")
    args = ap.parse_args()
    paths = config.get_paths()

    area = gpd.read_file(args.analysis_extent).to_crs(config.CRS).union_all().intersection(
        load_study_area(paths).union_all())
    ref = gpd.read_file(args.affected_roads).to_crs(config.CRS)
    ref = gpd.GeoDataFrame(geometry=ref.intersection(area), crs=config.CRS)
    ref = ref[~ref.is_empty]
    ref_km = ref.length.sum() / 1000
    ref_zone = ref.buffer(MATCH_M).union_all()

    _, edges = load_network(paths)
    edges = edges[edges.intersects(area)].copy()
    edges["geometry"] = edges.intersection(area)
    edges["km"] = edges.length / 1000
    edges["on_ref"] = edges.intersection(ref_zone).length / 1000   # km of each edge on an affected road

    rs = pd.read_csv(paths.road_status, dtype={"edge_id": str})
    rows = []
    for day in args.dates:
        day_rs = rs[rs["date"] == day].set_index("edge_id")
        if day_rs.empty:
            raise SystemExit(f"no road status for {day}")
        for t in config.SENSITIVITY_THRESHOLDS:
            st = day_rs[f"status_{round(t * 100)}"].reindex(edges["edge_id"]).fillna("unknown").to_numpy()
            on_ref = {s: edges["on_ref"][st == s].sum() for s in ("cut", "unknown", "open")}
            ref_total = sum(on_ref.values())
            cut_km = edges["km"][st == "cut"].sum()
            rows.append({
                "date": day, "threshold": t, "reference_km": round(ref_km, 1),
                "reference_km_matched": round(ref_total, 1),
                "ref_share_cut": round(on_ref["cut"] / ref_total, 3) if ref_total else None,
                "ref_share_unknown": round(on_ref["unknown"] / ref_total, 3) if ref_total else None,
                "ref_share_open": round(on_ref["open"] / ref_total, 3) if ref_total else None,
                "model_cut_km": round(cut_km, 1),
                "model_cut_share_on_reference": round(on_ref["cut"] / cut_km, 3) if cut_km else None,
            })
    out = pd.DataFrame(rows)
    out.to_csv(paths.results / "road_reference_check.csv", index=False)
    print(f"Reference affected roads inside its analysed area and the study area: {ref_km:.1f} km")
    print(f"Our road network there: {edges['km'].sum():.1f} km ({len(edges)} segments)")
    pd.set_option("display.width", 250)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
