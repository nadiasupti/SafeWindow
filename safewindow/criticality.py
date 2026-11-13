"""Road criticality: which single road segment, if closed, leaves villages with no road path to any shelter.

This only reads the pipeline's road network and snapped villages / shelters; it changes no result.

A segment matters on its own only if it is a *bridge* of the road graph in the graph-theory sense (a cut edge:
removing it splits the network in two). A segment with a parallel road between the same two junctions is never
one. For each such segment, the villages on the side with no shelter lose every road path. Segments that would
strand exactly the same villages are reported together, as one road stretch.

The same test on the roads seen open on one radar date gives the villages that were still connected but hung on
a single road: one more closed segment and they would have lost every road path ("fragile" on that date).

Limits: OpenStreetMap roads are incomplete and shelters are unverified candidates, so this is a planning signal,
not an engineering assessment. Boat-dependent villages (far from any road) are left out.
"""
from __future__ import annotations

from collections import Counter

import networkx as nx
import pandas as pd


def _graph(edges: pd.DataFrame, open_edge_ids=None) -> tuple[nx.Graph, Counter]:
    """Simple graph of the (open) roads, and how many parallel segments join each pair of junctions."""
    g = nx.Graph()
    g.add_nodes_from(pd.unique(edges[["u", "v"]].values.ravel()))
    sub = edges if open_edge_ids is None else edges[edges["edge_id"].isin(set(open_edge_ids))]
    parallel: Counter = Counter()
    for eid, u, v in sub[["edge_id", "u", "v"]].itertuples(index=False):
        if u == v:
            continue
        parallel[frozenset((u, v))] += 1
        if not g.has_edge(u, v):
            g.add_edge(u, v, edge_id=eid)
    return g, parallel


def stranding_segments(edges: pd.DataFrame, villages: pd.DataFrame, shelters: pd.DataFrame,
                       open_edge_ids=None) -> dict[str, frozenset]:
    """{edge_id: village ids that would lose every road path to a shelter if only that segment closed}.

    villages: village_id, node_id, boat_dependent. shelters: node_id, road_reachable.
    open_edge_ids: the roads to use (default: every road, i.e. the dry network)."""
    g, parallel = _graph(edges, open_edge_ids)
    cut_edges = [(u, v) for u, v in nx.bridges(g) if parallel[frozenset((u, v))] == 1]

    # 2-edge-connected pieces: what stays together whichever single segment closes
    pieces = g.copy()
    pieces.remove_edges_from(cut_edges)
    piece_of = {n: i for i, comp in enumerate(nx.connected_components(pieces)) for n in comp}

    on_road = villages[~villages["boat_dependent"].astype(bool)]
    village_ids: dict[int, set] = {}
    for vid, node in on_road[["village_id", "node_id"]].itertuples(index=False):
        if node in piece_of:
            village_ids.setdefault(piece_of[node], set()).add(vid)
    shelter_count: Counter = Counter(
        piece_of[n] for n in shelters.loc[shelters["road_reachable"].astype(bool), "node_id"] if n in piece_of)

    # the pieces joined by the cut edges form a forest: count villages and shelters on each side of every edge
    tree = nx.Graph()
    tree.add_nodes_from(set(piece_of.values()))
    for u, v in cut_edges:
        tree.add_edge(piece_of[u], piece_of[v], edge_id=g[u][v]["edge_id"])

    out: dict[str, frozenset] = {}
    for comp in nx.connected_components(tree):
        root = next(iter(comp))
        sub_villages: dict[int, frozenset] = {}
        sub_shelters: dict[int, int] = {}
        parent = nx.dfs_predecessors(tree, root)
        for n in nx.dfs_postorder_nodes(tree, root):
            vs, sc = set(village_ids.get(n, ())), shelter_count.get(n, 0)
            for child in tree.neighbors(n):
                if parent.get(child) == n:
                    vs |= sub_villages[child]
                    sc += sub_shelters[child]
            sub_villages[n], sub_shelters[n] = frozenset(vs), sc
        total = sub_shelters[root]
        if total == 0:
            continue                                   # no shelter anywhere on this network: nothing to lose
        for n, p in parent.items():
            if sub_shelters[n] == 0:
                lost = sub_villages[n]                 # the cut-off side is this subtree
            elif sub_shelters[n] == total:
                lost = sub_villages[root] - sub_villages[n]   # every shelter is in the subtree: the rest is cut off
            else:
                continue                               # shelters on both sides
            if lost:
                out[tree[n][p]["edge_id"]] = frozenset(lost)
    return out


def stranded_weight(edges: pd.DataFrame, weight_by_node: dict, shelters: pd.DataFrame,
                    open_edge_ids=None) -> dict[str, float]:
    """{edge_id: total weight (e.g. mapped buildings) at junctions that lose every road path to a shelter if only
    that segment closed}. The same forest as stranding_segments, with sums instead of sets, so it stays fast with
    many thousands of weighted junctions."""
    g, parallel = _graph(edges, open_edge_ids)
    cut_edges = [(u, v) for u, v in nx.bridges(g) if parallel[frozenset((u, v))] == 1]
    pieces = g.copy()
    pieces.remove_edges_from(cut_edges)
    piece_of = {n: i for i, comp in enumerate(nx.connected_components(pieces)) for n in comp}
    weight: Counter = Counter()
    for node, w in weight_by_node.items():
        if node in piece_of:
            weight[piece_of[node]] += w
    shelter_count: Counter = Counter(
        piece_of[n] for n in shelters.loc[shelters["road_reachable"].astype(bool), "node_id"] if n in piece_of)
    tree = nx.Graph()
    tree.add_nodes_from(set(piece_of.values()))
    for u, v in cut_edges:
        tree.add_edge(piece_of[u], piece_of[v], edge_id=g[u][v]["edge_id"])
    out: dict[str, float] = {}
    for comp in nx.connected_components(tree):
        root = next(iter(comp))
        sub_w: dict[int, float] = {}
        sub_s: dict[int, int] = {}
        parent = nx.dfs_predecessors(tree, root)
        for n in nx.dfs_postorder_nodes(tree, root):
            w, sc = weight.get(n, 0), shelter_count.get(n, 0)
            for child in tree.neighbors(n):
                if parent.get(child) == n:
                    w += sub_w[child]
                    sc += sub_s[child]
            sub_w[n], sub_s[n] = w, sc
        total = sub_s[root]
        if total == 0:
            continue
        for n, p in parent.items():
            if sub_s[n] == 0:
                lost = sub_w[n]
            elif sub_s[n] == total:
                lost = sub_w[root] - sub_w[n]
            else:
                continue
            if lost:
                out[tree[n][p]["edge_id"]] = lost
    return out


def road_stretches(stranding: dict[str, frozenset], edges: pd.DataFrame, villages: pd.DataFrame) -> pd.DataFrame:
    """Segments that strand the same villages, as one stretch each, most people first.

    Columns: rank, village_ids (tuple), villages (n), population, n_segments, length_m, edge_ids (tuple)."""
    if not stranding:
        return pd.DataFrame(columns=["rank", "village_ids", "villages", "population", "n_segments", "length_m",
                                     "edge_ids"])
    length = edges.drop_duplicates("edge_id").set_index("edge_id")["length_m"]
    population = villages.set_index("village_id")["population"].fillna(0)
    groups: dict[frozenset, list] = {}
    for eid, lost in stranding.items():
        groups.setdefault(lost, []).append(eid)
    rows = []
    for lost, eids in groups.items():
        ids = tuple(sorted(lost))
        rows.append({"village_ids": ids, "villages": len(ids), "population": int(population.reindex(ids).sum()),
                     "n_segments": len(eids), "length_m": round(float(length.reindex(eids).sum()), 1),
                     "edge_ids": tuple(sorted(eids))})
    df = pd.DataFrame(rows).sort_values(["population", "villages", "length_m"], ascending=[False, False, True])
    df.insert(0, "rank", range(1, len(df) + 1))
    return df.reset_index(drop=True)


def fragile_villages(edges: pd.DataFrame, villages: pd.DataFrame, shelters: pd.DataFrame,
                     open_edge_ids) -> set:
    """Villages reachable over the roads seen open, but through a single segment somewhere: one more closure
    and they would lose every road path."""
    return set().union(*stranding_segments(edges, villages, shelters, open_edge_ids).values())
