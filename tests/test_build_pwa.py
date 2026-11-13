import json
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_pwa  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATES = ["2022-05-16", "2022-05-23", "2022-05-25"]
WGS84 = "EPSG:4326"


def package(root: Path) -> Path:
    """A tiny flood package in the layout pipeline/08_build_app_data.py writes."""
    app = root / "live" / "app"
    (app / "flood").mkdir(parents=True)
    bounds = [[24.8, 91.2], [25.2, 91.8]]
    (app / "meta.json").write_text(json.dumps({
        "region": "sunamganj_2022", "data_label": "REAL DATA - test", "dates": DATES,
        "flood_bounds": {d: bounds for d in DATES}, "sources": {DATES[0]: "sentinel1", DATES[1]: float("nan"),
                                                                DATES[2]: "sentinel1"},
        "unknown_pct": {d: 0.0 for d in DATES}, "cut_threshold": 0.2, "default_supply_days": 7,
        "supply_days_range": [2, 14], "app_start": DATES[0], "app_end": DATES[-1]}))
    gpd.GeoDataFrame({
        "village_id": ["v1", "v2"], "name": ["Dolkotob", "Patharia"], "name_bn": ["দোলকোটব", None],
        "population": [1200, None], "outcome": ["isolated", "connected_when_seen"],
        "last_connected": ["2022-05-16", None], "first_isolated": ["2022-05-23", None],
        "isolated_from_earliest": ["2022-05-17", None], "reconnected": [None, None], "safe_exit_date": ["2022-05-16", None],
        "n_dates_isolated": [2, 0], "n_dates_connected": [1, 2], "n_dates_uncertain": [0, 1], "urgency_rank": [1, None],
        "exit_shelter": ["School A", None], "exit_route_m": [2300, None], "boat_dependent": [False, False],
    }, geometry=[Point(91.4, 25.0), Point(91.5, 25.05)], crs=WGS84).to_file(app / "villages.geojson", driver="GeoJSON")
    pd.DataFrame({"date": DATES * 2, "village_id": ["v1"] * 3 + ["v2"] * 2 + ["v2"],
                  "status": ["connected", "isolated", "isolated", "connected", "uncertain", "connected"],
                  "dist_to_shelter_m": 0, "nearest_shelter_id": ""}).iloc[:5].to_csv(app / "village_status.csv", index=False)
    road = LineString([(91.40001, 25.00001), (91.40002, 25.000015), (91.41, 25.01)])
    gpd.GeoDataFrame({"date": [DATES[1], DATES[2], DATES[2]], "edge_id": ["e1", "e1", "e2"], "highway": "track"},
                     geometry=[road, road, LineString([(91.5, 25.0), (91.6, 25.1)])], crs=WGS84
                     ).to_file(app / "cut_roads.geojson", driver="GeoJSON")
    gpd.GeoDataFrame({"village_id": ["v1"], "date": [DATES[0]], "shelter_id": ["s1"], "length_m": [2300],
                      "shelter_name": ["School A"]}, geometry=[LineString([(91.4, 25.0), (91.42, 25.02)])], crs=WGS84
                     ).to_file(app / "exit_routes.geojson", driver="GeoJSON")
    gpd.GeoDataFrame({"shelter_id": ["s1"], "name": ["School A"], "type": ["school"], "source": ["OpenStreetMap"]},
                     geometry=[Point(91.42, 25.02)], crs=WGS84).to_file(app / "shelters.geojson", driver="GeoJSON")
    for d in DATES:
        (app / "flood" / f"{d.replace('-', '')}.png").write_bytes(b"\x89PNG test")
    return app


def test_writes_the_same_layout_for_a_flood(tmp_path):
    package(tmp_path / "data")
    floods = build_pwa.build(tmp_path / "data", tmp_path / "out")
    assert [f["id"] for f in floods] == ["sunamganj_2022"] and floods[0]["villages"] == 2
    dest = tmp_path / "out" / "sunamganj_2022"
    names = {p.name for p in dest.iterdir()}
    assert {"metadata.json", "villages.json", "status.json", "flooded_roads.geojson", "routes.geojson",
            "shelters.geojson", "flood"} <= names
    assert len(list((dest / "flood").glob("*.png"))) == 3
    index = json.loads((tmp_path / "out" / "index.json").read_text(encoding="utf-8"))
    assert index["floods"][0]["id"] == "sunamganj_2022"
    # the download list names every file of the flood, itself included, so the area works offline
    listed = json.loads((dest / "files.json").read_text(encoding="utf-8"))
    on_disk = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert sorted(listed["files"]) == on_disk and "flood/20220516.png" in listed["files"] and listed["bytes"] > 0


def test_three_times_stay_apart(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    meta = json.loads((tmp_path / "out" / "sunamganj_2022" / "metadata.json").read_text(encoding="utf-8"))
    assert meta["observed_through"] == "2022-05-25"            # the latest radar image
    assert meta["published_at"] and meta["last_checked"] is None   # no automation yet: never invented
    assert meta["default_supply_days"] == 7 and meta["demonstration"] is False
    assert meta["languages"] == ["en", "bn"] and meta["emergency_contacts"]
    assert meta["sources"][DATES[1]] is None                       # NaN in the package becomes null


def test_villages_keep_observed_dates_and_drop_safe_wording(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    v = {x["id"]: x for x in json.loads((tmp_path / "out" / "sunamganj_2022" / "villages.json").read_text(encoding="utf-8"))}
    assert v["v1"]["last_connected"] == "2022-05-16" and v["v1"]["first_isolated"] == "2022-05-23"
    assert v["v1"]["isolated_from_earliest"] == "2022-05-17"     # supply days count from here, in the app
    assert v["v1"]["name_local"] == "দোলকোটব" and v["v2"]["population"] is None
    assert v["v1"]["urgency_rank"] == 1 and isinstance(v["v1"]["urgency_rank"], int)
    assert not any("safe" in k for rec in v.values() for k in rec)
    assert "aid_deadline" not in v["v1"]                           # the app computes it from the chosen supply days


def test_status_has_one_code_per_date_and_unknown_when_missing(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    s = json.loads((tmp_path / "out" / "sunamganj_2022" / "status.json").read_text(encoding="utf-8"))
    assert s["dates"] == DATES and s["codes"]["i"] == "isolated"
    assert s["villages"] == {"v1": "cii", "v2": "cuu"}            # v2 has no row on the last date: uncertain


def test_each_flooded_road_is_written_once_with_its_dates(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    roads = json.loads((tmp_path / "out" / "sunamganj_2022" / "flooded_roads.geojson").read_text(encoding="utf-8"))
    assert sorted(f["properties"]["d"] for f in roads["features"]) == [[1, 2], [2]]
    assert all(f["properties"]["n"] == 1 and f["geometry"]["type"] == "MultiLineString" for f in roads["features"])
    e1 = next(f for f in roads["features"] if f["properties"]["d"] == [1, 2])["geometry"]["coordinates"][0]
    assert len(e1) == 2                                            # a 1 m wiggle is simplified away
    assert all(len(str(c).split(".")[-1]) <= build_pwa.PRECISION for pt in e1 for c in pt)


def test_roads_flooded_on_the_same_dates_share_one_feature(tmp_path):
    app = package(tmp_path / "data")
    cut = gpd.read_file(app / "cut_roads.geojson")
    extra = gpd.GeoDataFrame({"date": [DATES[2]], "edge_id": ["e3"], "highway": "track"},
                             geometry=[LineString([(91.7, 25.0), (91.71, 25.01)])], crs=WGS84)
    pd.concat([cut, extra]).to_file(app / "cut_roads.geojson", driver="GeoJSON")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    roads = json.loads((tmp_path / "out" / "sunamganj_2022" / "flooded_roads.geojson").read_text(encoding="utf-8"))
    only_last = next(f for f in roads["features"] if f["properties"]["d"] == [2])
    assert only_last["properties"]["n"] == 2 and len(only_last["geometry"]["coordinates"]) == 2


def test_routes_and_shelters_say_they_are_not_checked(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    dest = tmp_path / "out" / "sunamganj_2022"
    route = json.loads((dest / "routes.geojson").read_text(encoding="utf-8"))["features"][0]["properties"]
    shelter = json.loads((dest / "shelters.geojson").read_text(encoding="utf-8"))["features"][0]["properties"]
    assert route["checked_on_ground"] is False and route["shelter_name"] == "School A"
    assert shelter["verified"] is False


def test_the_source_package_is_not_changed(tmp_path):
    app = package(tmp_path / "data")
    before = {p.name: p.read_bytes() for p in app.rglob("*") if p.is_file()}
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    assert {p.name: p.read_bytes() for p in app.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("name", ["live", "sunamganj_2024", "punjab_trimmu_2025", "nepal_terai_2017"])
def test_real_floods_are_small_enough_for_a_phone_and_match_the_source(tmp_path, name):
    app = ROOT / "data" / name / "app"
    if not (app / "meta.json").exists():
        pytest.skip(f"{name} has no built package")
    root = tmp_path / "data"
    shutil.copytree(app, root / name / "app")       # one flood at a time, read from a copy
    floods = build_pwa.build(root, tmp_path / "out")
    f = floods[0]
    assert f["size_mb"] < build_pwa.MAX_FLOOD_MB
    dest = tmp_path / "out" / f["id"]
    meta = json.loads((app / "meta.json").read_text(encoding="utf-8"))
    status = json.loads((dest / "status.json").read_text(encoding="utf-8"))
    assert status["dates"] == meta["dates"]
    # the same isolated villages as the source summary
    src = gpd.read_file(app / "villages.geojson")
    out = json.loads((dest / "villages.json").read_text(encoding="utf-8"))
    assert sorted(v["id"] for v in out if v["outcome"] == "isolated") == sorted(src.loc[src["outcome"] == "isolated", "village_id"])
    # every flooded road on every date survives the de-duplication
    cut = gpd.read_file(app / "cut_roads.geojson")
    roads = json.loads((dest / "flooded_roads.geojson").read_text(encoding="utf-8"))["features"]
    # strict JSON only: a browser's JSON.parse rejects NaN (the source meta.json has NaN sources)
    def no_nan(token):
        raise ValueError(f"{token} in the app's data")
    for f in list(dest.rglob("*.json")) + list(dest.rglob("*.geojson")):
        json.loads(f.read_text(encoding="utf-8"), parse_constant=no_nan)
    assert sum(r["properties"]["n"] for r in roads) == cut["edge_id"].nunique()
    assert sum(r["properties"]["n"] * len(r["properties"]["d"]) for r in roads) == len(cut.drop_duplicates(["edge_id", "date"]))


def test_road_criticality_and_relief_are_exported_when_they_exist(tmp_path):
    app = package(tmp_path / "data")
    res = app.parent / "results"
    res.mkdir()
    line = {"type": "LineString", "coordinates": [[91.4, 25.0], [91.41, 25.01]]}
    props = {"rank": 1, "villages": 1, "population": 1200, "n_segments": 2, "length_m": 350.0, "village_ids": ["v1"]}
    (res / "road_criticality.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": props, "geometry": line}]}))
    (res / "road_criticality_by_date.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {**props, "dates": [DATES[0], DATES[2]]}, "geometry": line}]}))
    pd.DataFrame({"date": [DATES[0]], "village_id": ["v2"]}).to_csv(res / "fragile_villages.csv", index=False)
    (res / "relief_prepositioning.json").write_text(json.dumps(
        {"test_flood": "sunamganj_2022", "sites": [], "best_possible_people": float("nan")}))
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    dest = tmp_path / "out" / "sunamganj_2022"
    roads = json.loads((dest / "critical_roads.geojson").read_text(encoding="utf-8"))["features"]
    assert [f["properties"]["kind"] for f in roads] == ["dry", "date"]
    assert roads[1]["properties"]["d"] == [0, 2] and roads[0]["properties"]["village_ids"] == ["v1"]
    crit = json.loads((dest / "critical.json").read_text(encoding="utf-8"))
    assert crit["fragile"] == {"v1": "000", "v2": "100"} and crit["dry_stretches"] == 1
    assert crit["checked_on_ground"] is False
    relief = json.loads((dest / "relief.json").read_text(encoding="utf-8"))   # strict JSON: NaN became null
    assert relief["best_possible_people"] is None
    listed = json.loads((dest / "files.json").read_text(encoding="utf-8"))["files"]
    assert {"critical_roads.geojson", "critical.json", "relief.json"} <= set(listed)    # offline too


def test_no_analysis_files_without_the_analyses(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    names = {p.name for p in (tmp_path / "out" / "sunamganj_2022").iterdir()}
    assert not names & {"critical_roads.geojson", "critical.json", "relief.json"}


def test_index_says_which_analyses_a_flood_has(tmp_path):
    package(tmp_path / "data")
    floods = build_pwa.build(tmp_path / "data", tmp_path / "out")
    assert floods[0]["analyses"] == {"critical_roads": False, "relief": False, "buildings": False}


def test_daily_watch_is_exported_as_written(tmp_path):
    package(tmp_path / "data")
    mon = tmp_path / "data" / "monitor"
    mon.mkdir()
    (mon / "sunamganj_2026.json").write_text(json.dumps({
        "region": "sunamganj_2026", "name": "Sunamganj 2026", "checked_at": "2026-11-07T19:26:22+00:00",
        "radar_dates": ["2026-11-01", "2026-11-05"], "newest_radar": "2026-11-05", "new_since_last_check": [],
        "rain": {"sunamganj": {"through": "2026-11-06", "1d_mm": 0, "3d_mm": float("nan"), "7d_mm": 0.4}},
        "sends_alerts": False}))
    (mon / "checks.csv").write_text("not read\n")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    out = json.loads((tmp_path / "out" / "monitor.json").read_text(encoding="utf-8"))["regions"]
    assert len(out) == 1 and out[0]["newest_radar"] == "2026-11-05" and out[0]["radar_dates"] == 2
    assert out[0]["rain"]["sunamganj"]["3d_mm"] is None and out[0]["sends_alerts"] is False   # NaN -> null, never guessed


def test_no_daily_watch_file_without_checks(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    assert not (tmp_path / "out" / "monitor.json").exists()


def test_nisar_layers_are_exported_for_the_nisar_page(tmp_path):
    package(tmp_path / "data")
    nis = tmp_path / "data" / "sunamganj_2026" / "results" / "nisar"
    nis.mkdir(parents=True)
    for f in ("20260724_hh.png", "20260724_hh_water.png"):
        (nis / f).write_bytes(b"\x89PNG test")
    (nis / "nisar.json").write_text(json.dumps({
        "region": "sunamganj_2026", "product": "NISAR_L2_GCOV_PROVISIONAL_V1", "bounds": [[24.8, 91.2], [25.2, 91.8]],
        "scenes": [{"date": "2026-07-24", "hh": {"water_km2": 700.0, "status": "otsu", "threshold_db": float("nan")},
                    "layers": {"hh": "20260724_hh.png", "hh_water": "20260724_hh_water.png"}}]}))
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    index = json.loads((tmp_path / "out" / "nisar" / "index.json").read_text(encoding="utf-8"))
    reg = index["regions"][0]
    assert reg["id"] == "sunamganj_2026" and reg["scenes"][0]["hh"]["threshold_db"] is None    # strict JSON
    assert (tmp_path / "out" / "nisar" / "sunamganj_2026" / "20260724_hh_water.png").exists()
    # the flood packages are not touched by it
    assert not (tmp_path / "out" / "sunamganj_2022" / "nisar").exists()


def test_no_nisar_folder_without_nisar_layers(tmp_path):
    package(tmp_path / "data")
    build_pwa.build(tmp_path / "data", tmp_path / "out")
    assert not (tmp_path / "out" / "nisar").exists()


def test_buildings_are_exported_packed_and_flagged(tmp_path):
    app = package(tmp_path / "data")
    res = app.parent / "results"
    res.mkdir()
    (res / "buildings_summary.json").write_text(json.dumps({"source": "Google Open Buildings v3", "buildings": 3,
                                                            "dates": DATES, "totals": []}))
    pd.DataFrame({"cx": [0, 1], "cy": [0, 0], "n": [2, 1], "far": [0, 1], "i": ["[0, 2, 1]", "[0, 0, 0]"],
                  "u": ["[1, 0, 0]", "[0, 0, 0]"], "w": ["[0, 0, 0]", "[0, 0, 0]"], "lat": [25.0, 25.0],
                  "lon": [91.4, 91.41]}).to_csv(res / "buildings_cells.csv", index=False)
    pd.DataFrame({"rank": [1], "buildings": [2], "max_isolated": [2], "dates_isolated": [2], "first_isolated": [DATES[1]],
                  "score": [3], "lat": [25.0], "lon": [91.4], "nearest_village_id": ["v1"],
                  "nearest_village_km": [0.4]}).to_csv(res / "buildings_clusters.csv", index=False)
    floods = build_pwa.build(tmp_path / "data", tmp_path / "out")
    b = json.loads((tmp_path / "out" / "sunamganj_2022" / "buildings.json").read_text(encoding="utf-8"))
    assert b["cells"][0] == [25.0, 91.4, 2, 0, "0.2.1", "1.0.0", None]           # base 36; an all-zero list is null
    assert build_pwa._b36(437) == "c5" and build_pwa._b36(0) == "0"
    assert b["cells"][1][4:] == [None, None, None]
    assert b["clusters"][0]["nearest_village_id"] == "v1" and b["checked_on_ground"] is False
    assert floods[0]["analyses"]["buildings"] is True


def test_built_app_downloads_stay_under_the_phone_limit():
    """The app's actual offline download per flood, analyses included (the data build_pwa.py last wrote)."""
    built = sorted(build_pwa.DEFAULT_OUT.glob("*/files.json"))
    if not built:
        pytest.skip("no app data built yet (run scripts/build_pwa.py)")
    for f in built:
        mb = json.loads(f.read_text(encoding="utf-8"))["bytes"] / 1e6
        assert mb < build_pwa.MAX_FLOOD_MB, f"{f.parent.name}: {mb:.2f} MB"
