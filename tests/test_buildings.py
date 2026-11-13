"""Buildings: the village rule applied to buildings, nearness to mapped water, cells and priority clusters."""
import random

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from safewindow import config
from safewindow.buildings import cells, near_water, priority_clusters, snap_buildings, status_codes
from safewindow.criticality import stranded_weight, stranding_segments

#   A ---- B ---- C ---- S(shelter)        (as in tests/test_engine.py)
#                 |
#                 D
XY = {"A": (0, 0), "B": (1000, 0), "C": (2000, 0), "S": (3000, 0), "D": (2000, -1000)}
EDGES = pd.DataFrame([("AB", "A", "B", 1000.0), ("BC", "B", "C", 1000.0), ("CS", "C", "S", 1000.0),
                      ("CD", "C", "D", 1000.0)], columns=["edge_id", "u", "v", "length_m"])
NODES = gpd.GeoDataFrame({"node_id": list(XY)}, geometry=[Point(p) for p in XY.values()], crs=config.CRS)


def test_buildings_follow_the_village_rule():
    b = snap_buildings(np.array([[10, 10], [2000, -1040], [1000, 3000]]), NODES)
    assert b["node_id"].tolist() == ["A", "D", "B"] and b["far"].tolist() == [False, False, True]
    open_all = pd.Series({"AB": "open", "BC": "open", "CS": "open", "CD": "open"})
    assert status_codes(EDGES, open_all, b, ["S"]).tolist() == ["c", "c", "b"]
    cut = open_all.copy()
    cut["BC"] = "cut"                       # A is cut off, D still reaches S
    assert status_codes(EDGES, cut, b, ["S"]).tolist() == ["i", "c", "b"]
    # a road fragment with no link to any shelter even when dry: "n" on every date, never "isolated"
    e2 = pd.concat([EDGES, pd.DataFrame([("XY", "X", "Y", 100.0)], columns=EDGES.columns)])
    n2 = pd.concat([NODES, gpd.GeoDataFrame({"node_id": ["X", "Y"]}, geometry=[Point(0, 5000), Point(100, 5000)],
                                            crs=config.CRS)])
    b2 = snap_buildings(np.array([[10, 10], [5, 5010]]), n2)
    from safewindow.buildings import dry_reach
    assert status_codes(e2, open_all, b2, ["S"], dry_reach(e2, ["S"])).tolist() == ["c", "n"]
    unknown = open_all.copy()
    unknown["BC"] = "unknown"               # cloud over BC: cannot tell
    assert status_codes(EDGES, unknown, b, ["S"]).tolist() == ["u", "c", "b"]


def test_near_water_is_within_the_distance_and_unknown_is_not_a_no():
    f = np.full((10, 10), config.DRY, dtype="uint8")
    f[5, 5] = config.FLOODED
    f[0, 0] = config.UNKNOWN
    rows, cols = np.array([5, 5, 5, 0]), np.array([7, 8, 9, 0])
    near, unseen = near_water(f, rows, cols, near_m=50, res_m=20)       # 50 m = 2.5 pixels
    assert near.tolist() == [True, False, False, False]                  # 40 m yes, 60 m no
    assert unseen.tolist() == [False, False, False, True]                # unknown pixel: neither


def test_cells_sum_buildings_and_clusters_rank_by_building_dates():
    b = pd.DataFrame({"x": [10, 20, 410, 2000], "y": [10, 20, 10, 2000], "far": [False, False, False, True]})
    codes = [np.array(["i", "c", "i", "b"]), np.array(["i", "i", "c", "b"])]
    near = [np.array([True, False, False, False]), np.array([False, False, False, False])]
    c = cells(b, codes, near, cell_m=400).set_index(["cx", "cy"])
    assert c.loc[(0, 0), "n"] == 2 and c.loc[(0, 0), "i"] == [1, 2] and c.loc[(0, 0), "w"] == [1, 0]
    assert c.loc[(5, 5), "far"] == 1
    cl = priority_clusters(c.reset_index(), ["2022-05-16", "2022-05-23"])
    # each cell on its own: (0,0) has 1 + 2 = 3 building-dates isolated, (1,0) has 1; (5,5) none
    assert cl["score"].tolist() == [3, 1] and cl.loc[0, "buildings"] == 2
    assert cl.loc[0, "dates_isolated"] == 2 and cl.loc[0, "first_isolated"] == "2022-05-16"
    assert cl.loc[1, "first_isolated"] == "2022-05-16" and cl.loc[1, "dates_isolated"] == 1


def test_stranded_weight_sums_what_stranding_segments_lists():
    rng = random.Random(3)
    for _ in range(40):
        n = rng.randint(4, 14)
        nodes = [f"N{i}" for i in range(n)]
        e = pd.DataFrame([(f"E{k}", rng.choice(nodes), rng.choice(nodes), 1.0) for k in range(rng.randint(3, 20))],
                         columns=["edge_id", "u", "v", "length_m"])
        weights = {x: rng.randint(1, 9) for x in rng.sample(nodes, rng.randint(1, n))}
        v = pd.DataFrame({"village_id": list(weights), "node_id": list(weights), "boat_dependent": False,
                          "population": 0})
        s = pd.DataFrame({"node_id": rng.sample(nodes, rng.randint(1, 3)), "road_reachable": True})
        want = {eid: sum(weights[x] for x in lost) for eid, lost in stranding_segments(e, v, s).items()}
        assert stranded_weight(e, weights, s) == want
