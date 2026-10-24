"""Check SafeWindow road results against dated news reports of cut roads.

    python scripts/road_reports_check.py

The reports come from the region file (`road_reports` in regions/*.yaml).
Each names one of the routes below, a question the model answers on every
satellite date. For sunamganj_2022 these are two reports from The Daily Star:

  1. "Road communications between Chhatak and Dowarabazar upazilas of
     Sunamganj were cut yesterday" (20 May 2022, so cut on 19 May).
     Test: is there any road route between the two upazila towns?
  2. "road communication with Sunamganj has been cut off from other parts of
     the country since Thursday" (18 June 2022, so since 16 June).
     Test: is there any road route between the two ends of the
     Sunamganj-Sylhet Highway inside the study area (south of Sunamganj town
     to the edge towards Sylhet), and how much of the highway is cut?

A route is 'open' if it exists using only roads seen open, 'cut' if it does
not exist even when every unknown road is assumed open, and 'unknown' in
between, the same rule as for villages.

Writes <data>/results/road_reports_check.csv and prints a summary.
"""
from __future__ import annotations

import unicodedata

import geopandas as gpd
import networkx as nx
import pandas as pd

from safewindow import config
from safewindow.isolation import snap
from safewindow.roads import build_graph, load_network

REPORTS = config.REGION.road_reports
TOWNS = {"Chhatak": "osm1472175218", "Dowarabazar": "osm2481972070"}   # OSM place=town nodes
HIGHWAY_NAMES = ("Sunamganj - Sylhet Highway", "সুনামগঞ্জ-সিলেট মহাসড়ক")


def route_status(edges: pd.DataFrame, status: pd.Series, a: str, b: str) -> str:
    status = status.reindex(edges["edge_id"]).fillna("unknown")

    def linked(g: nx.Graph) -> bool:
        return a in g and b in g and nx.has_path(g, a, b)

    if linked(build_graph(edges, status.index[status == "open"])):
        return "open"
    return "unknown" if linked(build_graph(edges, status.index[status != "cut"])) else "cut"


def main() -> None:
    config.utf8_console()
    paths = config.get_paths()
    nodes, edges = load_network(paths)
    rs = pd.read_csv(paths.road_status, dtype={"edge_id": str})
    col = f"status_{round(config.CUT_THRESHOLD * 100)}"

    # Only the routes the region's reports ask about are built.
    routes, hw_edges = {}, None
    for r in REPORTS:
        name = r["route"]
        if name in routes or (name == "points" and r["id"] in routes):
            continue
        if name == "chhatak_dowarabazar":
            villages = gpd.read_file(paths.villages).to_crs(config.CRS)
            towns = villages[villages["village_id"].astype(str).isin(TOWNS.values())].set_index("village_id")
            town_node = dict(zip(towns.index, snap(towns.geometry, nodes)[0]))
            routes[name] = (town_node[TOWNS["Chhatak"]], town_node[TOWNS["Dowarabazar"]])
        elif name == "sunamganj_sylhet_highway":
            # Bengali letters such as ড় have two Unicode encodings in OSM; compare normalised names
            wanted = {unicodedata.normalize("NFC", n) for n in HIGHWAY_NAMES}
            hw = edges["name"].fillna("").map(lambda n: unicodedata.normalize("NFC", n)).isin(wanted)
            hw_edges = edges[hw]
            hw_km = hw_edges["length_m"].sum() / 1000
            # The highway's ends inside the study area: just south of Sunamganj town (west)
            # and the edge of the study area towards Sylhet (east). Any road may be used.
            hw_nodes = nodes.set_index("node_id").loc[sorted(set(hw_edges["u"]) | set(hw_edges["v"]))]
            routes[name] = (hw_nodes.geometry.x.idxmin(), hw_nodes.geometry.x.idxmax())
        elif name == "points":
            # any two places, given as lon/lat in the region file
            ends = gpd.GeoSeries(gpd.points_from_xy([r["from"][0], r["to"][0]], [r["from"][1], r["to"][1]]),
                                 crs=config.CRS_WGS84).to_crs(config.CRS)
            ids, dist = snap(ends, nodes)
            for end, d in zip(("from", "to"), dist):
                if d > 500:
                    print(f"  WARNING: report {r['id']!r} '{end}' point is {d:.0f} m from the nearest road junction")
            routes[r["id"]] = (ids[0], ids[1])
        else:
            raise SystemExit(f"report {r['id']!r}: unknown route {name!r}; use chhatak_dowarabazar, "
                             "sunamganj_sylhet_highway or points (with from/to)")

    rows = []
    for day, grp in rs.groupby("date"):
        grp = grp.set_index("edge_id")
        row = {"date": day}
        for t in config.SENSITIVITY_THRESHOLDS:
            st = grp[f"status_{round(t * 100)}"]
            for name, (u, v) in routes.items():
                row[f"{name}_{round(t * 100)}"] = route_status(edges, st, u, v)
        if hw_edges is not None:
            hst = grp[col].reindex(hw_edges["edge_id"]).fillna("unknown").to_numpy()
            row["highway_km_cut"] = round(hw_edges["length_m"][hst == "cut"].sum() / 1000, 1)
            row["highway_km_unknown"] = round(hw_edges["length_m"][hst == "unknown"].sum() / 1000, 1)
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(paths.results / "road_reports_check.csv", index=False)

    # For each report: the model's answer on the last observation before the
    # reported date and on the first one on or after it, skipping dates when
    # the radar did not cover the route (unknown at the main threshold).
    verdicts = []
    for r in REPORTS:
        name = r["id"] if r["route"] == "points" else r["route"]
        known = out[out[f"{name}_{round(config.CUT_THRESHOLD * 100)}"] != "unknown"]
        before = known[known["date"] < r["event_date"]].tail(1)
        after = known[known["date"] >= r["event_date"]].head(1)

        def answer(obs: pd.DataFrame) -> tuple[str, str]:
            if obs.empty:
                return "none", "no radar view of the route"
            return obs["date"].iloc[0], "/".join(obs[f"{name}_{round(t * 100)}"].iloc[0]
                                                  for t in config.SENSITIVITY_THRESHOLDS)

        (b_date, b_route), (a_date, a_route) = answer(before), answer(after)
        verdicts.append({
            "report": r["id"], "event_date": r["event_date"], "source": r["source"], "url": r["url"], "quote": r["quote"],
            "last_observation_before": b_date, "route_before": b_route,
            "first_observation_after": a_date, "route_after": a_route,
        })
    verdict = pd.DataFrame(verdicts)
    verdict.to_csv(paths.results / "road_reports_verdict.csv", index=False)

    if hw_edges is not None:
        print(f"Sunamganj-Sylhet Highway inside the study area: {hw_km:.1f} km in {len(hw_edges)} segments")
    print("Route status per date at cut thresholds 10% / 20% / 40%:")
    show = out[["date"]].copy()
    for name in routes:
        show[name] = out[[f"{name}_{round(t * 100)}" for t in config.SENSITIVITY_THRESHOLDS]].agg("/".join, axis=1)
    if hw_edges is not None:
        show["highway_km_cut"] = out["highway_km_cut"]
    print(show.to_string(index=False))
    print("\nAgainst the reports (10% / 20% / 40%):")
    print(verdict[["report", "event_date", "last_observation_before", "route_before",
                   "first_observation_after", "route_after"]].to_string(index=False))


if __name__ == "__main__":
    main()
