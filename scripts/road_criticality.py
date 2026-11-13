"""Which road stretch, if closed, leaves the most villages with no road path to any shelter?

    python scripts/road_criticality.py                     # every flood package (data/*/app)
    python scripts/road_criticality.py data/live           # one package

Reads, per package, the pipeline's own outputs (nothing is recomputed or changed):
    processed/road_edges.gpkg         the road network
    results/villages_snapped.csv      village -> road junction, boat-dependent flag, population
    results/shelters_snapped.csv      shelter candidate -> road junction (unverified)
    results/road_status.csv           open / cut / unknown per segment and radar date (at the package's
                                      cut threshold, as in the app)

Writes, next to the other analyses in results/:
    road_criticality.csv        one row per road stretch: villages and people who would lose every road path
    road_criticality.geojson    the same stretches as lines (WGS84), for the app
    road_criticality_by_date.geojson   the same test on the roads seen open on each radar date: the stretches
                                that were a village's only remaining road link that day (`dates`)
    fragile_villages.csv        date, village_id: connected that day over roads seen open, but through a single
                                segment somewhere (one more closure and they would be cut off)

The dry network (every mapped road open) shows which roads matter before any flood. OSM roads are incomplete
and shelters unverified, so this is a planning signal, not an engineering assessment. See
safewindow/criticality.py for the method.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from safewindow.criticality import fragile_villages, road_stretches, stranded_weight, stranding_segments  # noqa: E402

SIMPLIFY_DEG = 0.00005     # about 5 m, as the app's other road layers


def load(pkg: Path):
    edges = gpd.read_file(pkg / "processed" / "road_edges.gpkg")
    for c in ("edge_id", "u", "v"):
        edges[c] = edges[c].astype(str)
    villages = pd.read_csv(pkg / "results" / "villages_snapped.csv", dtype={"village_id": str, "node_id": str})
    shelters = pd.read_csv(pkg / "results" / "shelters_snapped.csv", dtype={"shelter_id": str, "node_id": str})
    meta = json.loads((pkg / "app" / "meta.json").read_text(encoding="utf-8"))
    threshold = meta.get("cut_threshold", 0.2)
    status = pd.read_csv(pkg / "results" / "road_status.csv", dtype={"edge_id": str})
    status["date"] = pd.to_datetime(status["date"]).dt.strftime("%Y-%m-%d")
    return edges, villages, shelters, status, f"status_{round(threshold * 100)}", list(meta["dates"])


def _lines(stretches: pd.DataFrame, edges: gpd.GeoDataFrame, villages: pd.DataFrame, extra: dict | None = None):
    names = villages.set_index("village_id")
    local = names["name_bn"].where(names["name_bn"].notna(), names["name"]) if "name_bn" in names else names["name"]
    geom = edges.drop_duplicates("edge_id").set_index("edge_id").geometry
    lines = gpd.GeoDataFrame(
        {"rank": stretches["rank"], "villages": stretches["villages"], "population": stretches["population"],
         "n_segments": stretches["n_segments"], "length_m": stretches["length_m"],
         "village_ids": [list(ids) for ids in stretches["village_ids"]],
         "names": [[str(names.loc[i, "name"]) for i in ids] for ids in stretches["village_ids"]],
         "names_bn": [[str(local.loc[i]) for i in ids] for ids in stretches["village_ids"]], **(extra or {})},
        geometry=[geom.reindex(list(eids)).union_all() for eids in stretches["edge_ids"]], crs=edges.crs,
    ).to_crs(4326)
    lines["geometry"] = lines.geometry.simplify(SIMPLIFY_DEG)
    return lines


def building_weights(pkg: Path, edges) -> dict | None:
    """Mapped buildings per road junction (not those far from roads), if building_exposure.py fetched them."""
    from building_exposure import load_buildings
    nodes = gpd.read_file(pkg / "processed" / "road_nodes.gpkg")
    nodes["node_id"] = nodes["node_id"].astype(str)
    xy = load_buildings(pkg, nodes.crs)
    if xy is None:
        return None
    from safewindow.buildings import snap_buildings
    b = snap_buildings(xy, nodes)
    return b.loc[~b["far"], "node_id"].value_counts().to_dict()


def with_buildings(stretches: pd.DataFrame, weight: dict | None) -> pd.DataFrame:
    """Mapped buildings that would lose every road path if a segment of the stretch closed (the most for any
    one segment of it); None when there is no building data."""
    stretches = stretches.copy()
    stretches["buildings"] = (None if weight is None else
                              [int(max((weight.get(e, 0) for e in eids), default=0)) for eids in stretches["edge_ids"]])
    return stretches


def analyse(pkg: Path):
    edges, villages, shelters, status, col, dates = load(pkg)
    weights = building_weights(pkg, edges)
    w_dry = None if weights is None else stranded_weight(edges, weights, shelters)
    stretches = with_buildings(road_stretches(stranding_segments(edges, villages, shelters), edges, villages), w_dry)
    lines = _lines(stretches, edges, villages, {"buildings": stretches["buildings"].tolist()})

    rows, by_key = [], {}
    for day in dates:
        open_ids = status.loc[(status["date"] == day) & (status[col] == "open"), "edge_id"]
        stranding = stranding_segments(edges, villages, shelters, open_ids)
        for vid in sorted(fragile_villages(edges, villages, shelters, open_ids)):
            rows.append({"date": day, "village_id": vid})
        w_day = None if weights is None else stranded_weight(edges, weights, shelters, open_ids)
        for r in with_buildings(road_stretches(stranding, edges, villages), w_day).itertuples(index=False):
            key = (r.edge_ids, r.village_ids)               # the same stretch, stranding the same villages
            entry = by_key.setdefault(key, {"row": r._asdict(), "dates": []})
            entry["dates"].append(day)
            if r.buildings is not None:                     # the most on any date it was the only link
                entry["row"]["buildings"] = max(entry["row"]["buildings"] or 0, r.buildings)
    fragile = pd.DataFrame(rows, columns=["date", "village_id"])
    if by_key:
        daily = pd.DataFrame([v["row"] for v in by_key.values()])
        daily_lines = _lines(daily, edges, villages, {"dates": [v["dates"] for v in by_key.values()],
                                                      "buildings": daily["buildings"].tolist()})
    else:
        daily_lines = gpd.GeoDataFrame({"dates": []}, geometry=[], crs=4326)
    return stretches, lines, fragile, daily_lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packages", nargs="*", type=Path, help="flood packages (default: every data/*/app)")
    args = ap.parse_args()
    pkgs = args.packages or sorted(p.parent for p in (ROOT / "data").glob("*/app") if (p / "meta.json").exists())
    for pkg in pkgs:
        stretches, lines, fragile, daily = analyse(pkg)
        out = pkg / "results"
        stretches.assign(village_ids=stretches["village_ids"].map(";".join),
                         edge_ids=stretches["edge_ids"].map(";".join)).to_csv(out / "road_criticality.csv", index=False)
        if len(lines):
            lines.to_file(out / "road_criticality.geojson", driver="GeoJSON")
        else:
            (out / "road_criticality.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        fragile.to_csv(out / "fragile_villages.csv", index=False)
        if len(daily):
            daily.to_file(out / "road_criticality_by_date.geojson", driver="GeoJSON")
        else:
            (out / "road_criticality_by_date.geojson").write_text('{"type":"FeatureCollection","features":[]}',
                                                                  encoding="utf-8")
        top = stretches.head(3)
        print(f"{pkg.name}: {len(stretches)} stretches strand at least one village; "
              f"{fragile['village_id'].nunique()} villages were fragile on some date")
        for r in top.itertuples():
            print(f"   #{r.rank}: {r.villages} villages, {r.population:,} people, {r.n_segments} segments, "
                  f"{r.length_m / 1000:.1f} km")


if __name__ == "__main__":
    main()
