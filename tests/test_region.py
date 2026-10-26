from datetime import date

import pytest

from safewindow import config, region


def test_sunamganj_2022_reproduces_the_published_settings():
    # These literals are the values config.py held before regions existed;
    # data/live was built with them.
    r = region.load("sunamganj_2022")
    assert r.admin_names == ["Sunamganj Sadar", "Chhatak", "Dowarabazar"]
    assert (r.parent, r.country) == ("Sunamganj", "Bangladesh")
    assert r.crs == "EPSG:32646"
    assert (r.dry_start, r.dry_end) == ("2022-02-01", "2022-03-31")
    assert (r.flood_start, r.flood_end) == (date(2022, 5, 15), date(2022, 7, 15))
    assert (r.app_start, r.app_end) == (date(2022, 5, 20), date(2022, 6, 30))
    assert r.rain_boxes == {
        "sunamganj": (90.95, 24.85, 91.75, 25.25),
        "meghalaya_upstream": (91.30, 25.15, 92.10, 25.45),
    }
    assert (r.default_supply_days, r.supply_days_range) == (7, (2, 14))
    assert (r.iso3, r.settlements, r.shelters_csv) == ("BGD", "osm", None)


def test_settlement_source_and_iso3_are_checked(tmp_path):
    with pytest.raises(ValueError, match="settlements must be one of"):
        region.parse(minimal(settlements="buildings"), tmp_path / "test.yaml")
    with pytest.raises(ValueError, match="iso3"):
        region.parse(minimal(area={"admin_names": ["A"], "bbox": [91, 24, 92, 25], "iso3": "BD"}),
                     tmp_path / "test.yaml")


def test_road_reports_come_from_the_region():
    r = region.load("sunamganj_2022")
    assert [(x["id"], x["route"], x["event_date"]) for x in r.road_reports] == [
        ("chhatak_dowarabazar", "chhatak_dowarabazar", "2022-05-19"),
        ("sunamganj_sylhet_highway", "sunamganj_sylhet_highway", "2022-06-16")]
    assert region.load("sunamganj_2024").road_reports[0]["route"] == "chhatak_dowarabazar"


def test_points_route_keeps_lon_lat(tmp_path):
    rep = {"id": "shorkot", "route": "points", "event_date": "2025-08-30", "source": "s", "url": "u", "quote": "q",
           "from": [72.07, 30.83], "to": [71.9, 30.83]}
    r = region.parse(minimal(road_reports=[rep]), tmp_path / "test.yaml")
    assert r.road_reports[0]["from"] == (72.07, 30.83) and r.road_reports[0]["to"] == (71.9, 30.83)
    with pytest.raises(ValueError, match="needs to: \\[lon, lat\\]"):
        region.parse(minimal(road_reports=[{**rep, "to": None}]), tmp_path / "test.yaml")


def test_road_report_needs_its_fields(tmp_path):
    with pytest.raises(ValueError, match=r"road_reports\[0\] is missing"):
        region.parse(minimal(road_reports=[{"id": "x", "route": "chhatak_dowarabazar"}]), tmp_path / "test.yaml")


def test_sunamganj_2024_differs_from_2022_only_in_dates():
    a, b = region.load("sunamganj_2022"), region.load("sunamganj_2024")
    same = ("admin_names", "parent", "country", "iso3", "bbox", "crs", "rain_boxes", "settlements",
            "default_supply_days", "supply_days_range", "languages", "agencies")
    assert all(getattr(a, f) == getattr(b, f) for f in same)
    assert (b.dry_start, b.flood_start) == ("2024-02-01", date(2024, 5, 1))


def test_boundary_file_region_needs_no_admin_names(tmp_path):
    with pytest.warns(UserWarning, match="more than one UTM zone"):     # this bbox straddles 72E
        r = region.parse(minimal(area={"boundary_file": "aoi.geojson", "bbox": [71.8, 30.7, 72.2, 31.3]}),
                         tmp_path / "test.yaml")
    assert r.boundary_file == tmp_path / "aoi.geojson"
    assert r.admin_names == [] and r.crs == "EPSG:32643"
    with pytest.raises(ValueError, match="admin_names .* or boundary_file"):
        region.parse(minimal(area={"bbox": [71.8, 30.7, 72.2, 31.3]}), tmp_path / "test.yaml")


def test_punjab_region_loads():
    r = region.load("punjab_trimmu_2025")
    assert (r.iso3, r.crs) == ("PAK", "EPSG:32643")
    assert r.boundary_file.exists()
    assert r.languages == ["en", "ur"]          # Urdu is offered as a draft, with a visible notice


def test_shelters_csv_is_relative_to_the_region_file(tmp_path):
    r = region.parse(minimal(shelters_csv="local/shelters.csv"), tmp_path / "test.yaml")
    assert r.shelters_csv == tmp_path / "local" / "shelters.csv"


def test_config_uses_the_default_region():
    assert config.REGION.id == "sunamganj_2022"
    assert config.CRS == "EPSG:32646"
    assert config.UPAZILAS == ["Sunamganj Sadar", "Chhatak", "Dowarabazar"]
    assert config.FLOOD_START == date(2022, 5, 15)


@pytest.mark.parametrize("lon, lat, epsg", [
    (91.5, 25.0, "EPSG:32646"),     # Sunamganj
    (68.0, 26.5, "EPSG:32642"),     # Sindh, Pakistan
    (-51.2, -30.0, "EPSG:32722"),   # Rio Grande do Sul, Brazil (southern hemisphere)
    (179.9, 10.0, "EPSG:32660"),
])
def test_utm_epsg(lon, lat, epsg):
    assert region.utm_epsg(lon, lat) == epsg


def minimal(**overrides):
    raw = {
        "id": "test",
        "area": {"admin_names": ["A"], "bbox": [91.25, 24.80, 91.75, 25.18]},
        "crs": "auto",
        "dates": {"flood": ["2024-05-01", "2024-07-31"], "dry_reference": ["2024-02-01", "2024-03-31"]},
    }
    raw.update(overrides)
    return raw


def test_auto_crs_from_bbox_and_app_dates_default_to_flood_dates(tmp_path):
    r = region.parse(minimal(), tmp_path / "test.yaml")
    assert r.crs == "EPSG:32646"
    assert (r.app_start, r.app_end) == (date(2024, 5, 1), date(2024, 7, 31))


def test_auto_crs_warns_when_bbox_spans_two_utm_zones(tmp_path):
    raw = minimal(area={"admin_names": ["A"], "bbox": [89.5, 24.0, 90.5, 25.0]})   # zone boundary at 90E
    with pytest.warns(UserWarning, match="more than one UTM zone"):
        region.parse(raw, tmp_path / "test.yaml")


def test_auto_crs_needs_a_bbox(tmp_path):
    with pytest.raises(ValueError, match="needs area.bbox"):
        region.parse(minimal(area={"admin_names": ["A"]}), tmp_path / "test.yaml")


def test_explicit_crs_overrides_auto(tmp_path):
    assert region.parse(minimal(crs="EPSG:3106"), tmp_path / "test.yaml").crs == "EPSG:3106"


@pytest.mark.parametrize("dates, message", [
    ({"flood": ["2024-07-31", "2024-05-01"], "dry_reference": ["2024-02-01", "2024-03-31"]}, "after end"),
    ({"flood": ["2024-05-01"], "dry_reference": ["2024-02-01", "2024-03-31"]}, r"\[start, end\]"),
    ({"flood": ["2024-05-01", "not a date"], "dry_reference": ["2024-02-01", "2024-03-31"]}, "YYYY-MM-DD"),
])
def test_bad_dates_are_rejected(tmp_path, dates, message):
    with pytest.raises(ValueError, match=message):
        region.parse(minimal(dates=dates), tmp_path / "test.yaml")


def test_missing_region_lists_the_available_ones():
    with pytest.raises(FileNotFoundError, match="sunamganj_2022"):
        region.load("no_such_region")


def test_region_can_be_loaded_from_a_path(tmp_path):
    path = tmp_path / "custom.yaml"
    path.write_text("id: custom\narea: {admin_names: [A], bbox: [68, 26, 69, 27]}\ncrs: auto\n"
                    "dates: {flood: [2022-08-01, 2022-09-30], dry_reference: [2022-03-01, 2022-04-30]}\n",
                    encoding="utf-8")
    r = region.load(str(path))
    assert (r.id, r.crs, r.flood_start) == ("custom", "EPSG:32642", date(2022, 8, 1))
