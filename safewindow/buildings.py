"""Mapped buildings: their road access to a shelter and their nearness to mapped flood water, per radar date.

Buildings are Google Open Buildings v3 footprints (confidence >= 0.75), as centroids. Each building is joined to
its nearest road junction, exactly as villages are (safewindow/isolation.py): more than BOAT_DEPENDENT_M from any
road means "far from roads" (boat-dependent). On each radar date a building is then
  connected  - its junction reaches a shelter over roads seen open,
  isolated   - it cannot even if every road not seen cut were open,
  uncertain  - in between (roads not seen),
the same rule as for villages, so nothing new is decided here. One addition: a building whose junction cannot
reach any shelter even with every mapped road open (a road fragment OpenStreetMap does not join to the network)
is "no mapped road link" on every date, not "isolated": the flood did not cut it off, the map has no link.

"Near mapped water" means a flooded pixel of that date's map lies within NEAR_WATER_M of the building. It is not
"flooded inside": radar often misses water between buildings (walls and water reflect the signal back brightly),
and homesteads in the haor stand on raised ground. A mapped building is not a count of people.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .isolation import reachable_from, snap
from .roads import build_graph

NEAR_WATER_M = 50
CELL_M = 500                  # buildings are summed into square cells of this size for the app
CODES = {"connected": "c", "isolated": "i", "uncertain": "u", "far": "b", "no_road_link": "n"}


def dry_reach(edges, shelter_nodes) -> set:
    """Junctions that reach a shelter with every mapped road open."""
    return reachable_from(build_graph(edges), shelter_nodes)


def snap_buildings(xy: np.ndarray, nodes) -> pd.DataFrame:
    """Nearest road junction of every building (x, y in the network's projection) and whether it is far from roads."""
    import geopandas as gpd
    pts = gpd.GeoSeries(gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=nodes.crs)
    node, dist = snap(pts, nodes)
    return pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1], "node_id": node, "snap_m": dist,
                         "far": dist > config.BOAT_DEPENDENT_M})


def status_codes(edges, road_status: pd.Series, b: pd.DataFrame, shelter_nodes, linked: set | None = None) -> np.ndarray:
    """One code per building for one date: c, i, u, b (far from roads) or n (no mapped road link to any shelter even
    when dry; `linked` = dry_reach(...)); the village rule applied to buildings."""
    status = road_status.reindex(edges["edge_id"]).fillna("unknown")
    g_pes = build_graph(edges, status.index[status == "open"])
    g_opt = build_graph(edges, status.index[status != "cut"])
    reach_pes, reach_opt = reachable_from(g_pes, shelter_nodes), reachable_from(g_opt, shelter_nodes)
    node = b["node_id"]
    out = np.where(node.isin(reach_pes), "c", np.where(node.isin(reach_opt), "u", "i"))
    if linked is not None:
        out = np.where(node.isin(linked), out, "n")
    return np.where(b["far"].to_numpy(), "b", out)


def near_water(flood: np.ndarray, rows: np.ndarray, cols: np.ndarray, near_m: float = NEAR_WATER_M,
               res_m: float = config.GRID_RES_M) -> tuple[np.ndarray, np.ndarray]:
    """(near mapped water, not seen) per building for one flood map. "Not seen": the building's own pixel is unknown
    and no mapped water is near it, so neither yes nor no can be said."""
    from scipy import ndimage
    r = int(np.ceil(near_m / res_m))
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    disk = (yy ** 2 + xx ** 2) * res_m ** 2 <= near_m ** 2
    wet = ndimage.binary_dilation(flood == config.FLOODED, structure=disk)
    inside = (rows >= 0) & (rows < flood.shape[0]) & (cols >= 0) & (cols < flood.shape[1])
    rr, cc = np.clip(rows, 0, flood.shape[0] - 1), np.clip(cols, 0, flood.shape[1] - 1)
    near = inside & wet[rr, cc]
    unseen = inside & ~near & (flood[rr, cc] == config.UNKNOWN)
    return near, unseen


def cells(b: pd.DataFrame, codes: list[np.ndarray], near: list[np.ndarray], cell_m: float = CELL_M) -> pd.DataFrame:
    """Buildings summed per square cell: n, far, and per date the number isolated, uncertain and near water."""
    key = pd.Series(list(zip(np.floor(b["x"] / cell_m).astype(int), np.floor(b["y"] / cell_m).astype(int))))
    g = pd.DataFrame({"key": key, "far": b["far"].to_numpy()})
    rows = []
    for k, idx in g.groupby("key").groups.items():
        idx = np.asarray(idx)
        rows.append({"cx": int(k[0]), "cy": int(k[1]), "x": (k[0] + 0.5) * cell_m, "y": (k[1] + 0.5) * cell_m,
                     "n": len(idx), "far": int(g["far"].to_numpy()[idx].sum()),
                     "noroad": int((codes[0][idx] == "n").sum()) if codes else 0,
                     "i": [int((c[idx] == "i").sum()) for c in codes],
                     "u": [int((c[idx] == "u").sum()) for c in codes],
                     "w": [int(w[idx].sum()) for w in near]})
    return pd.DataFrame(rows)


def priority_clusters(cell_df: pd.DataFrame, dates: list[str], top: int | None = None) -> pd.DataFrame:
    """Cells (CELL_M) with buildings seen isolated, ranked for field verification (a cell is small enough to visit;
    joining neighbouring cells made areas tens of km across).

    Score (shown with the result): building-dates seen isolated = the sum over radar dates of the buildings seen
    isolated in the cell. More buildings, isolated on more radar dates, come first. It ranks where to check first;
    it is not a rescue list."""
    rows = []
    for r in cell_df.itertuples():
        per_date = np.asarray(r.i)
        if per_date.sum() == 0:
            continue
        rows.append({"cells": 1, "buildings": int(r.n), "max_isolated": int(per_date.max()),
                     "dates_isolated": int((per_date > 0).sum()), "first_isolated": dates[int(np.argmax(per_date > 0))],
                     "score": int(per_date.sum()), "x": float(r.x), "y": float(r.y)})
    if not rows:
        return pd.DataFrame(columns=["rank", "cells", "buildings", "max_isolated", "dates_isolated",
                                     "first_isolated", "score", "x", "y"])
    out = pd.DataFrame(rows).sort_values(["score", "buildings"], ascending=False).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out if top is None else out.head(top)
