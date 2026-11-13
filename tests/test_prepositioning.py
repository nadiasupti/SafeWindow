"""Relief pre-positioning helpers on small hand-made cases."""
import numpy as np
import pytest

from safewindow.prepositioning import best_possible, covered, distance_km, greedy_sites, random_mean


def test_distance_one_degree_of_latitude():
    d = distance_km([24.0], [91.0], [25.0, 24.0], [91.0, 91.0])
    assert d.shape == (1, 2)
    assert d[0, 0] == pytest.approx(111.19, abs=0.05) and d[0, 1] == 0


# 3 sites x 4 villages, distances in km
DIST = np.array([[1.0, 2.0, 9.0, 9.0],
                 [9.0, 9.0, 1.0, 9.0],
                 [9.0, 4.0, 9.0, 3.0]])
PEOPLE = [100, 50, 400, 10]


def test_greedy_takes_the_most_people_first():
    assert greedy_sites(DIST, PEOPLE, 1, 5) == [1]                 # 400 people
    assert greedy_sites(DIST, PEOPLE, 2, 5) == [1, 0]              # then 150
    assert greedy_sites(DIST, PEOPLE, 3, 5) == [1, 0, 2]           # then the last 10


def test_greedy_stops_when_nothing_is_left_to_cover():
    assert greedy_sites(DIST, PEOPLE, 3, 1.5) == [1, 0]            # site 2 reaches nobody within 1.5 km


def test_greedy_tie_goes_to_the_nearer_site():
    dist = np.array([[4.0], [2.0]])
    assert greedy_sites(dist, [10], 1, 5) == [1]


def test_covered_and_yardsticks():
    assert covered(DIST, [0], 5).tolist() == [True, True, False, False]
    assert covered(DIST, [], 5).tolist() == [False] * 4
    # one random site: (150 + 400 + 60) / 3
    assert random_mean(DIST, PEOPLE, 1, 5) == pytest.approx(610 / 3)
    assert best_possible(DIST, PEOPLE, 2, 5) == 550
    assert best_possible(DIST, PEOPLE, 3, 5) == 560
