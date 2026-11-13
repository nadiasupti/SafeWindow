"""Road criticality on tiny hand-made networks (answers worked out by hand)."""
import pandas as pd

from safewindow.criticality import fragile_villages, road_stretches, stranding_segments


def net(edges, villages, shelters):
    e = pd.DataFrame([(eid, u, v, length) for eid, u, v, length in edges], columns=["edge_id", "u", "v", "length_m"])
    v = pd.DataFrame([(vid, node, boat, pop) for vid, node, boat, pop in villages],
                     columns=["village_id", "node_id", "boat_dependent", "population"])
    s = pd.DataFrame([(node, True) for node in shelters], columns=["node_id", "road_reachable"])
    return e, v, s


#   V1 at A --AB-- B --BC-- C(shelter)        a chain: each segment strands what lies behind it
#                  |
#                  BD
#                  D: V2
CHAIN = net([("AB", "A", "B", 100), ("BC", "B", "C", 200), ("BD", "B", "D", 50)],
            [("V1", "A", False, 1000), ("V2", "D", False, 300)], ["C"])


def test_chain_each_segment_strands_what_is_behind_it():
    out = stranding_segments(*CHAIN)
    assert out == {"AB": {"V1"}, "BC": {"V1", "V2"}, "BD": {"V2"}}


def test_stretches_most_people_first():
    e, v, _ = CHAIN
    st = road_stretches(stranding_segments(*CHAIN), e, v)
    assert st["edge_ids"].tolist() == [("BC",), ("AB",), ("BD",)]
    top = st.iloc[0]
    assert top["villages"] == 2 and top["population"] == 1300 and top["length_m"] == 200 and top["rank"] == 1


def test_a_loop_has_no_single_point_of_failure():
    # A-B-C-A triangle with the shelter at C: closing any one side leaves another way round
    e, v, s = net([("AB", "A", "B", 1), ("BC", "B", "C", 1), ("CA", "C", "A", 1)],
                  [("V1", "A", False, 10), ("V2", "B", False, 10)], ["C"])
    assert stranding_segments(e, v, s) == {}


def test_parallel_roads_are_not_a_single_point_of_failure():
    e, v, s = net([("AB1", "A", "B", 1), ("AB2", "A", "B", 5)], [("V1", "A", False, 10)], ["B"])
    assert stranding_segments(e, v, s) == {}
    # with only one of the two roads open, the other becomes the only link
    assert stranding_segments(e, v, s, open_edge_ids=["AB1"]) == {"AB1": {"V1"}}


def test_shelters_on_both_sides_strand_nobody():
    e, v, s = net([("AB", "A", "B", 1), ("BC", "B", "C", 1)], [("V1", "B", False, 10)], ["A", "C"])
    assert stranding_segments(e, v, s) == {}


def test_every_shelter_beyond_the_segment():
    # shelters only in the far subtree: the village side is the one cut off
    e, v, s = net([("AB", "A", "B", 1), ("BC", "B", "C", 1), ("CD", "C", "D", 1)],
                  [("V1", "A", False, 10), ("V2", "B", False, 10)], ["D"])
    out = stranding_segments(e, v, s)
    assert out["CD"] == {"V1", "V2"} and out["BC"] == {"V1", "V2"} and out["AB"] == {"V1"}


def test_boat_dependent_and_unreachable_villages_are_left_out():
    e, v, s = net([("AB", "A", "B", 1)], [("V1", "A", True, 10), ("V2", "A", False, 10)], ["B"])
    assert stranding_segments(e, v, s) == {"AB": {"V2"}}
    # a network piece with no shelter at all: nothing to lose
    e2, v2, s2 = net([("AB", "A", "B", 1), ("XY", "X", "Y", 1)], [("V3", "X", False, 10)], ["B"])
    assert stranding_segments(e2, v2, s2) == {}


def test_fragile_on_a_date_uses_only_roads_seen_open():
    e, v, s = net([("AB", "A", "B", 1), ("BC", "B", "C", 1), ("CA", "C", "A", 1)],
                  [("V1", "A", False, 10), ("V2", "B", False, 10)], ["C"])
    assert fragile_villages(e, v, s, ["AB", "BC", "CA"]) == set()          # full loop: nobody fragile
    assert fragile_villages(e, v, s, ["AB", "BC"]) == {"V1", "V2"}         # CA closed: both hang on BC
    assert fragile_villages(e, v, s, ["CA"]) == {"V1"}                     # V2 already cut off: not "fragile"


def test_matches_removing_each_segment_one_by_one():
    """The fast forest method gives exactly what brute force gives: close one segment, re-check every village."""
    import random

    import networkx as nx

    rng = random.Random(7)
    for trial in range(40):
        n = rng.randint(4, 14)
        nodes = [f"N{i}" for i in range(n)]
        edges = [(f"E{k}", rng.choice(nodes), rng.choice(nodes), 1.0) for k in range(rng.randint(3, 20))]
        vill = [(f"V{i}", rng.choice(nodes), rng.random() < 0.1, rng.randint(1, 100)) for i in range(rng.randint(1, 6))]
        shel = rng.sample(nodes, rng.randint(1, 3))
        e, v, s = net(edges, vill, shel)

        def reachable(edge_ids):
            g = nx.MultiGraph()
            g.add_nodes_from(nodes)
            g.add_edges_from((u, w) for eid, u, w, _ in edges if eid in edge_ids and u != w)
            seen = set().union(*(nx.node_connected_component(g, x) for x in shel))
            return {vid for vid, node, boat, _ in vill if not boat and node in seen}

        everything = {eid for eid, *_ in edges}
        before = reachable(everything)
        brute = {}
        for eid in everything:
            lost = before - reachable(everything - {eid})
            if lost:
                brute[eid] = lost
        assert stranding_segments(e, v, s) == brute, trial
