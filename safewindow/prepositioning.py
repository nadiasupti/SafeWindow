"""Relief pre-positioning: which few existing places lie closest to the villages that get cut off.

Learned on one flood, tested on a later one (no hindsight): the sites are chosen from the earlier flood's isolated
villages only, then scored on the villages the later flood isolated.

A site "covers" a village within `radius_km` in a straight line. Straight line on purpose: during the flood the
roads from any shelter to an isolated village are, by definition, cut (that is what "isolated" means), so stock
has to move into the villages before the roads close, or by boat, which the model does not know about.
Candidate sites are the pipeline's (unverified) shelter candidates. This is an analysis, not a decision.
"""
from __future__ import annotations

import itertools
import math
import random

import numpy as np


def distance_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km between every point 1 (rows) and every point 2 (columns)."""
    la1, lo1 = np.radians(np.asarray(lat1, float))[:, None], np.radians(np.asarray(lon1, float))[:, None]
    la2, lo2 = np.radians(np.asarray(lat2, float))[None, :], np.radians(np.asarray(lon2, float))[None, :]
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def covered(dist: np.ndarray, sites, radius_km: float) -> np.ndarray:
    """Which targets (columns) lie within radius of at least one chosen site (rows)."""
    sites = list(sites)
    if not sites:
        return np.zeros(dist.shape[1], dtype=bool)
    return (dist[sites] <= radius_km).any(axis=0)


def greedy_sites(dist: np.ndarray, weights, k: int, radius_km: float) -> list[int]:
    """Up to k sites, each adding the most uncovered weight (people); ties go to the site nearer its targets.
    Stops early when no site adds anything."""
    w = np.asarray(weights, float)
    chosen: list[int] = []
    done = np.zeros(dist.shape[1], dtype=bool)
    for _ in range(k):
        best, best_key = None, None
        for s in range(dist.shape[0]):
            if s in chosen:
                continue
            new = (dist[s] <= radius_km) & ~done
            gain = w[new].sum()
            if gain <= 0:
                continue
            key = (gain, -dist[s][new].sum(), -s)
            if best_key is None or key > best_key:
                best, best_key = s, key
        if best is None:
            break
        chosen.append(best)
        done |= dist[best] <= radius_km
    return chosen


def random_mean(dist: np.ndarray, weights, k: int, radius_km: float, max_exact: int = 50000, seed: int = 0) -> float:
    """Average people covered by k sites picked at random: exact over every combination when there are few,
    otherwise over a fixed random sample. The yardstick a choice has to beat."""
    w = np.asarray(weights, float)
    n = dist.shape[0]
    k = min(k, n)
    total = math.comb(n, k)
    if total <= max_exact:
        combos = itertools.combinations(range(n), k)
    else:
        rng = random.Random(seed)
        combos = (rng.sample(range(n), k) for _ in range(max_exact))
        total = max_exact
    return float(sum(w[covered(dist, c, radius_km)].sum() for c in combos) / total)


def best_possible(dist: np.ndarray, weights, k: int, radius_km: float, max_exact: int = 200000) -> float | None:
    """The most people any k sites could cover (with hindsight), when the combinations are few enough to try."""
    w = np.asarray(weights, float)
    n = dist.shape[0]
    k = min(k, n)
    if math.comb(n, k) > max_exact:
        return None
    return float(max(w[covered(dist, c, radius_km)].sum() for c in itertools.combinations(range(n), k)))
