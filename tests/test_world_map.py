import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from safewindow import world_map

WORLD = Path(__file__).resolve().parent.parent / "app" / "static" / "world"


def test_features_are_merged_into_one_shape_per_zoom_level():
    lines = gpd.GeoDataFrame({"z": [3, 3, 5]}, geometry=[LineString([(0, 0), (1, 1)]), LineString([(2, 2), (3, 3)]),
                                                         LineString([(5, 5), (6, 6)])], crs="EPSG:4326")
    merged = world_map.merge_by_zoom(lines)
    assert list(merged["z"]) == [3, 5] and [len(g.geoms) for g in merged.geometry] == [2, 1]
    polys = gpd.GeoDataFrame({"z": [1, 1]}, geometry=[Polygon([(0, 0), (1, 0), (1, 1)]), Polygon([(5, 5), (6, 5), (6, 6)])], crs="EPSG:4326")
    assert merged.crs == lines.crs and len(world_map.merge_by_zoom(polys).geometry.iloc[0].geoms) == 2


def test_the_shipped_world_files_match_their_manifest_and_stay_small():
    manifest = json.loads((WORLD / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "public domain" and manifest["version"] == world_map.VERSION
    total = 0
    for name, info in manifest["files"].items():
        data = (WORLD / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info["sha256"], f"{name} changed after it was built"
        total += len(data)
    assert total < 20e6, "the offline world map should stay under 20 MB"
    credit = (WORLD / "NATURAL_EARTH.txt").read_text(encoding="utf-8")
    assert "public domain" in credit and world_map.VERSION in credit and "naturalearthdata.com" in credit


def test_every_layer_is_valid_geojson_with_zoom_levels_and_country_names_in_our_languages():
    for name in ("land", "countries", "admin1_lines", "lakes", "rivers", "places"):
        feats = json.loads((WORLD / f"{name}.geojson").read_text(encoding="utf-8"))["features"]
        assert feats and all("z" in f["properties"] and f["geometry"] for f in feats), name
    countries = {f["properties"]["name"]: f["properties"] for f in json.loads((WORLD / "countries.geojson").read_text(encoding="utf-8"))["features"]}
    assert countries["Bangladesh"]["name_bn"] == "বাংলাদেশ" and countries["Pakistan"]["name_ur"] == "پاکستان"
    assert countries["Nepal"]["name_hi"] and countries["Brazil"]["name_pt"] == "Brasil" and countries["Spain"]["name_es"] == "España"
    places = json.loads((WORLD / "places.geojson").read_text(encoding="utf-8"))["features"]
    assert {"Dhaka", "Kathmandu", "Islamabad", "Lagos"} <= {f["properties"]["name"] for f in places}


def test_the_map_loads_the_world_from_this_app_never_from_the_internet():
    import folium
    from app.streamlit_app import WORLD_URL, add_world_map
    m = folium.Map(location=[24.9, 91.3], tiles=None)
    add_world_map(m, "bn")
    html = m.get_root().render()
    for pane in ("sw_sea", "sw_land", "sw_lines", "sw_labels"):
        assert pane in html
    script = html[html.index("BASE = "):html.index("BASE = ") + 120]
    assert WORLD_URL in script and "'bn'" in script
    world_js = html[html.index("window.__swMap"):html.index("})();", html.index("window.__swMap"))]
    assert "http" not in world_js.replace("https://www.naturalearthdata", "")      # no outside address in the layer's code
    assert "maxBounds".lower() in world_js.lower()


def test_cut_roads_are_one_shape_not_thousands():
    from app.streamlit_app import cut_roads_geojson, load
    from safewindow import config
    app = config.get_paths().app
    if not (app / "meta.json").exists():
        pytest.skip("no built app data")
    meta, _v, _s, _sh, _r, cut, _o = load(str(app))
    day = max(cut["date"].unique(), key=lambda d: (cut["date"] == d).sum())
    out = cut_roads_geojson(str(app), str(day))
    feature = json.loads(out["json"])
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "MultiLineString"
    assert out["n"] == (cut["date"] == day).sum() >= 1 and len(feature["geometry"]["coordinates"]) >= 1
    assert cut_roads_geojson(str(app), "1999-01-01")["n"] == 0
