"""Hidden water: what NISAR's L-band sees around a village that Sentinel-1's C-band does not."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import nisar_villages as nv  # noqa: E402

BOUNDS = [[24.0, 91.0], [25.0, 92.0]]
LAND, WATER, EDGE = (238, 232, 217, 255), (30, 110, 230, 255), (140, 140, 140, 60)


def png(path, water_cols=(), edge_cols=(), size=100):
    px = np.zeros((size, size, 4), np.uint8)
    px[:] = LAND
    for c in water_cols:
        px[:, c] = WATER
    for c in edge_cols:
        px[:, c] = EDGE
    Image.fromarray(px).save(path)


@pytest.fixture()
def region(tmp_path):
    d = tmp_path / "results" / "nisar"
    d.mkdir(parents=True)
    # NISAR sees water in the west 60 columns; Sentinel-1 only in the west 20: the gap is on the west side
    png(d / "20260620_hh_water.png", water_cols=range(0, 60))
    png(d / "20260620_s1_water.png", water_cols=range(0, 20))
    png(d / "20260701_hv_water.png", water_cols=range(0, 60))          # a date with HV only
    png(d / "20260701_s1_water.png", water_cols=range(0, 20))
    png(d / "20260710_hh_water.png", water_cols=range(0, 60))          # no Sentinel-1 map: skipped
    scene = lambda date, layers, s1date="2026-06-19": {                                   # noqa: E731
        "date": date, "layers": layers, "sentinel1": {"date": s1date, "water_km2": 5.0},
        "hh": {"status": "otsu" if "hh_water" in layers else "otsu_failed", "water_km2": 8.0 if "hh_water" in layers else 0.0},
        "hv": {"status": "otsu", "water_km2": 7.5}}
    (d / "nisar.json").write_text(json.dumps({"region": "demo", "bounds": BOUNDS, "scenes": [
        scene("2026-06-20", {"hh_water": "20260620_hh_water.png", "s1_water": "20260620_s1_water.png"}),
        scene("2026-07-01", {"hv_water": "20260701_hv_water.png", "s1_water": "20260701_s1_water.png"}),
        scene("2026-07-10", {"hh_water": "20260710_hh_water.png"})]}), encoding="utf-8")
    return d


VILLAGES = [{"village_id": "west", "name": "West", "lat": 24.5, "lon": 91.2},       # inside NISAR water, partly S1
            {"village_id": "east", "name": "East", "lat": 24.5, "lon": 91.85},      # dry in both
            {"village_id": "out", "name": "Outside", "lat": 30.0, "lon": 91.5}]


def test_the_gap_is_nisar_water_minus_sentinel1_water_around_each_village(region):
    s = nv.region_summary(region, VILLAGES, radius_km=5)
    first = s["dates"][0]
    assert first["polarization"] == "HH" and first["sentinel1_date"] == "2026-06-19"
    assert first["villages"]["west"]["nisar"] > first["villages"]["west"]["sentinel1"]
    assert first["villages"]["west"]["hidden"] > 0.3
    assert first["villages"]["east"]["hidden"] == 0.0
    assert first["villages"]["out"]["hidden"] is None                    # outside the map: no number, no guess
    assert first["villages_with_a_gap"] == 1


def test_the_summary_is_strict_json_so_a_browser_can_read_it(region):
    villages = [{"village_id": "west", "name": "West", "name_bn": None, "lat": 24.5, "lon": 91.2}]
    json.dumps(nv.region_summary(region, villages, radius_km=5), allow_nan=False)      # raises on NaN or Infinity
    json.dumps(nv.time_series(region), allow_nan=False)


def test_hv_is_used_when_hh_has_no_map_and_a_date_without_sentinel1_is_skipped(region):
    s = nv.region_summary(region, VILLAGES, radius_km=5)
    assert [d["date"] for d in s["dates"]] == ["2026-06-20", "2026-07-01"]
    assert s["dates"][1]["polarization"] == "HV"


def test_frame_edge_and_no_data_pixels_are_not_counted_as_dry(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    png(a, water_cols=range(0, 30), edge_cols=range(30, 100))            # NISAR: no data east of column 30
    png(b, water_cols=())
    gap = nv.village_gap(nv.load_water(a), nv.load_water(b), BOUNDS, 24.5, 91.8, radius_km=5)   # village in the no-data strip
    assert gap["hidden"] is None and gap["unknown"] > 0.5


def test_time_series_reports_failed_thresholds_as_missing_not_zero(region):
    rows = nv.time_series(region)
    assert rows[0]["hh_km2"] == 8.0 and rows[0]["s1_km2"] == 5.0
    assert rows[2]["hh_km2"] is not None                                  # that date's HH has a map
    meta = json.loads((region / "nisar.json").read_text(encoding="utf-8"))
    meta["scenes"][0]["hh"] = {"status": "otsu_failed", "water_km2": 0.0}
    (region / "nisar.json").write_text(json.dumps(meta), encoding="utf-8")
    assert nv.time_series(region)[0]["hh_km2"] is None


def test_the_real_results_give_a_gap_for_both_regions():
    root = Path(__file__).resolve().parent.parent / "data"
    for rid in ("sunamganj_2026", "punjab_trimmu_2026"):
        f = root / rid / "results" / "nisar" / "village_water.json"
        assert f.exists(), "run scripts/nisar_village_water.py"
        def refuse(constant):
            raise ValueError(f"{constant} is not valid JSON: a browser cannot read {f.name}")
        d = json.loads(f.read_text(encoding="utf-8"), parse_constant=refuse)
        assert d["dates"] and all(x["median_hidden"] is not None for x in d["dates"]) and d["series"]
