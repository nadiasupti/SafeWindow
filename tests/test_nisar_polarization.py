"""Helpers of scripts/nisar_polarization.py that need no network."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import nisar_polarization as npz  # noqa: E402


def test_nearest_sentinel1_within_the_gap(tmp_path):
    for d in ("20260719", "20260722", "20260801"):
        (tmp_path / f"sentinel1_{d}.tif").write_bytes(b"")
    gap, path, day = npz.nearest_s1(tmp_path, "2026-07-24", 3)
    assert (gap, day) == (2, "2026-07-22") and path.name == "sentinel1_20260722.tif"
    assert npz.nearest_s1(tmp_path, "2026-07-10", 3) is None          # nothing within 3 days: no comparison


def test_medians_describe_only_valid_pixels_and_need_enough_of_them():
    hh = np.full((10, 10), -20.0)
    hv = np.full((10, 10), -28.0)
    hh[0, 0] = np.nan
    m = np.ones((10, 10), bool)
    out = npz.medians(hh, hv, m)
    assert out == {"pixels": 99, "hh_db": -20.0, "hv_db": -28.0, "hh_minus_hv_db": 8.0}
    few = np.zeros((10, 10), bool)
    few[0, :5] = True
    assert npz.medians(hh, hv, few) is None


def test_water_maps_are_saved_without_any_colour_or_transparency_change(tmp_path):
    from PIL import Image
    a = np.zeros((40, 50, 4), np.uint8)
    a[:20] = (30, 110, 230, 255)                 # water
    a[20:, :25] = (140, 140, 140, 60)            # no data, half transparent
    a[20:, 25:] = (238, 232, 218, 255)           # land
    npz.save_png(a, tmp_path / "w.png")
    assert (np.array(Image.open(tmp_path / "w.png").convert("RGBA")) == a).all()
