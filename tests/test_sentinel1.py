"""Tests for the Sentinel-1 threshold choice: a map is only classified when Otsu finds dark water."""

import importlib.util
from pathlib import Path

import numpy as np

S1_PATH = Path(__file__).parents[1] / "pipeline" / "02a_sentinel1_gee.py"
SPEC = importlib.util.spec_from_file_location("sentinel1_step", S1_PATH)
s1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s1)

CENTERS = np.arange(-30, 10, 0.25)


def histogram(water_db: float, land_db: float = -8.0, water_share: float = 0.6, n: int = 100_000) -> np.ndarray:
    def peak(mu):
        return np.exp(-0.5 * ((CENTERS - mu) / 1.5) ** 2)
    h = water_share * peak(water_db) / peak(water_db).sum() + (1 - water_share) * peak(land_db) / peak(land_db).sum()
    return h * n


def test_calm_water_gives_a_usable_otsu_threshold():
    t, status = s1.choose_threshold(histogram(-22.0), CENTERS)
    assert status == "otsu"
    assert -18 < t < -12


def test_wind_roughened_water_is_not_classified():
    # water peak near -15 dB, as on 23 Jun 2022 and 17 Jun 2024: Otsu lands above -12 dB
    t, status = s1.choose_threshold(histogram(-15.0), CENTERS)
    assert status == "otsu_failed"
    assert t > s1.OTSU_PLAUSIBLE_DB[1]


def test_outside_the_swath_is_unknown():
    # swath: 2 seen by the radar, 1 not seen, 0 beyond the study area (export clip)
    cls = np.array([[1, 0, 1, 0, 0]], "uint8")
    swath = np.array([[2, 2, 1, 1, 0]], "uint8")
    assert s1.combine_with_swath(cls, swath).tolist() == [[1, 0, 255, 255, 0]]


def test_too_few_pixels_is_not_classified():
    assert s1.choose_threshold(histogram(-22.0, n=500), CENTERS) == (None, "too_few_pixels")
    assert s1.choose_threshold(None, None) == (None, "too_few_pixels")
