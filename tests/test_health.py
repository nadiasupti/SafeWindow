import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from safewindow import config, health
from safewindow.region import parse

ELEMENTS = [
    {"type": "node", "lat": 26.9, "lon": 85.2, "tags": {"amenity": "hospital", "name": "Gaur Hospital"}},
    {"type": "way", "center": {"lat": 26.95, "lon": 85.3}, "tags": {"healthcare": "health_post"}},
    {"type": "node", "lat": 27.0, "lon": 85.4, "tags": {"amenity": "clinic", "name:en": "Village Clinic", "name": "x"}},
    {"type": "relation", "tags": {"amenity": "hospital"}},                      # no coordinates: skipped
]


class Reply:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload or {}

    def json(self):
        return self._payload


def test_osm_elements_become_named_facilities():
    items = health.from_osm(ELEMENTS)
    assert [i["name"] for i in items] == ["Gaur Hospital", "Health Post (unnamed)", "Village Clinic"]   # English name preferred
    assert items[1]["lat"] == 26.95 and items[1]["type"] == "health_post"                              # way centre used


def test_overpass_waits_out_an_overloaded_server_and_tries_the_next_mirror():
    calls, waits = [], []

    def post(url, data, timeout):
        calls.append(url)
        return Reply(503) if len(calls) == 1 else Reply(200, {"elements": ELEMENTS})

    items = health.fetch_osm((85.0, 26.8, 85.5, 27.2), post=post, sleep=waits.append)
    assert len(items) == 3 and calls[0] != calls[1]
    assert health.query((85.0, 26.8, 85.5, 27.2)).count("(26.8,85.0,27.2,85.5)") == 2          # south,west,north,east order


def test_overpass_gives_up_politely_and_does_not_retry_a_bad_query():
    waits = []
    with pytest.raises(RuntimeError, match="did not answer"):
        health.fetch_osm((0, 0, 1, 1), post=lambda url, data, timeout: Reply(502), sleep=waits.append)
    assert waits == [20, 60, 120]                                                              # three patient rounds
    waits.clear()
    with pytest.raises(RuntimeError, match="rejected"):
        health.fetch_osm((0, 0, 1, 1), post=lambda url, data, timeout: Reply(400), sleep=waits.append)
    assert waits == []                                                                         # no pointless waiting


def region(tmp_path, csv=None):
    raw = {"id": "x", "area": {"admin_names": ["a"]}, "crs": "EPSG:32645",
           "dates": {"flood": ["2017-08-01", "2017-08-30"], "dry_reference": ["2017-02-01", "2017-03-01"]}}
    if csv:
        raw["health_csv"] = csv
    return parse(raw, tmp_path / "x.yaml")


def shelters():
    return gpd.GeoDataFrame({"name": ["School A", "District Hospital"], "type": ["school", "hospital"]},
                            geometry=[Point(85.2, 26.9), Point(85.3, 26.95)], crs="EPSG:4326")


def test_build_prefers_a_local_list_then_openstreetmap_then_the_shelter_list(tmp_path):
    pd.DataFrame({"name": ["Local Clinic"], "lat": [26.91], "lon": [85.21]}).to_csv(tmp_path / "h.csv", index=False)
    app = tmp_path / "app"; app.mkdir()
    got = health.build(app, region(tmp_path, "h.csv"), shelters(), (85, 26.8, 85.5, 27.2), fetch=lambda b: pytest.fail("not needed"))
    assert got == {"source": "local list", "n": 1} and health.read(app)[0][0] == "Local Clinic"
    got = health.build(app, region(tmp_path), shelters(), (85, 26.8, 85.5, 27.2), fetch=lambda b: health.from_osm(ELEMENTS))
    assert got == {"source": "osm", "n": 3}
    def down(bbox):
        raise RuntimeError("Overpass did not answer")
    got = health.build(app, region(tmp_path), shelters(), (85, 26.8, 85.5, 27.2), fetch=down)
    assert got == {"source": "shelter list", "n": 1} and health.read(app)[0][0] == "District Hospital"


def test_build_writes_nothing_when_there_is_no_data(tmp_path):
    app = tmp_path / "app"; app.mkdir()
    empty = gpd.GeoDataFrame({"name": ["School"], "type": ["school"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    assert health.build(app, region(tmp_path), empty, None) == {"source": None, "n": 0}
    assert not (app / "health.geojson").exists() and health.read(app) == []


def test_a_card_always_says_something_about_health_care():
    from app.streamlit_app import build_card, load, route_for_date, texts
    app = config.get_paths().app
    if not (app / "meta.json").exists():
        pytest.skip("no built app data")
    meta, villages, _s, shel, routes, _c, _o = load(str(app))
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(7, unit="D")
    v = villages.iloc[0]
    r = route_for_date(routes, v["village_id"], pd.Timestamp(meta["app_end"]))
    t = texts("en", config.REGION)
    none = build_card(v, r, shel, config.REGION, "en", t, 7, health=[])              # a region with no facilities at all
    assert none["health"] == t["health_none"] and "emergency number" in none["health"]
    near = build_card(v, r, shel, config.REGION, "en", t, 7, health=[("Terai Clinic", v.geometry.y + 0.01, v.geometry.x)])
    assert near["health"].startswith("Terai Clinic: about 1.1 km")
    assert "\u2191" in near["health"]                                                 # due north
