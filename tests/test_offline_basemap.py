import json

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from safewindow import config, offline_basemap
from safewindow.validation import validate_app_dataset

CRS = "EPSG:32646"          # UTM 46N, as the Sunamganj engine uses


def edges():
    rows = [("primary", 0), ("residential", 1), ("residential", 2), ("track", 3), ("secondary", 4), ("['service', 'track']", 5)]
    return gpd.GeoDataFrame(
        {"edge_id": [str(i) for _, i in rows], "highway": [h for h, _ in rows],
         "geometry": [LineString([(350000 + i * 400, 2750000), (350000 + i * 400 + 300, 2750000 + 200)]) for _, i in rows]},
        geometry="geometry", crs=CRS)


def test_road_classes():
    cls = offline_basemap.road_class
    assert [cls("motorway"), cls("primary_link"), cls("secondary"), cls("tertiary")] == [1, 1, 2, 2]
    assert [cls("residential"), cls("unclassified"), cls("service")] == [3, 3, 3]
    assert [cls("track"), cls("path"), cls("footway"), cls(None)] == [4, 4, 4, 4]
    assert cls("['service', 'track']") == 3 and cls("['primary', 'track']") == 1      # the first OSM tag counts


def test_roads_are_merged_by_class_in_lat_lon_and_keep_every_segment():
    roads = offline_basemap.build_roads(edges())
    assert list(roads["c"]) == [1, 2, 3, 4] and str(roads.crs) == offline_basemap.WGS84
    parts = {int(r.c): len(r.geometry.geoms) for r in roads.itertuples()}
    assert parts == {1: 1, 2: 1, 3: 3, 4: 1}                                       # 6 roads, none dropped
    west, south, east, north = roads.total_bounds
    assert 88 < west < 92 and 24 < south < 26                                     # really lon/lat


def test_build_writes_both_files_and_survives_missing_inputs(tmp_path):
    processed, app = tmp_path / "processed", tmp_path / "app"
    processed.mkdir(); app.mkdir()
    assert offline_basemap.build(processed, app) == {}                             # nothing to draw from: nothing written
    edges().to_file(processed / "road_edges.gpkg", driver="GPKG")
    gpd.GeoDataFrame(geometry=[Polygon([(349000, 2749000), (353000, 2749000), (353000, 2752000)])], crs=CRS
                     ).to_file(processed / "study_area.gpkg", driver="GPKG")
    written = offline_basemap.build(processed, app)
    assert set(written) == {"roads.geojson", "study_area.geojson"} and all(v > 0 for v in written.values())
    data = json.loads((app / "roads.geojson").read_text())
    assert [f["properties"]["c"] for f in data["features"]] == [1, 2, 3, 4]
    assert offline_basemap.read_json_bounds(app / "roads.geojson")[0] < 92


def test_the_map_draws_the_base_map_without_the_network():
    import folium
    from app.streamlit_app import add_vector_basemap, ROAD_STYLE
    roads = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"c": c}, "geometry": {"type": "MultiLineString",
                                                                   "coordinates": [[[91.0, 24.9], [91.1, 24.95]]]}}
        for c in (1, 2, 3, 4)]}
    area = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
        "type": "Polygon", "coordinates": [[[91, 24.8], [91.3, 24.8], [91.3, 25], [91, 24.8]]]}}]}
    m = folium.Map(location=[24.9, 91.1], tiles=None)
    add_vector_basemap(m, {"roads": [(f["properties"]["c"], json.dumps(f)) for f in roads["features"]],
                           "area": json.dumps(area)})
    html = m.get_root().render()
    for colour, _ in ROAD_STYLE.values():
        assert colour in html
    layers = [line for line in html.splitlines() if "L.geoJson(" in line]
    assert len(layers) == 5 and not any("http" in line for line in layers)           # 4 road classes + the outline, all inline
    add_vector_basemap(m, {"roads": [], "area": None})                            # a package without the files still works


def test_real_packages_with_a_base_map_still_validate_and_load():
    from app.streamlit_app import load_basemap
    app = config.get_paths().app
    if not (app / "roads.geojson").exists():
        pytest.skip("this package has no offline base map yet (run scripts/add_offline_basemap.py)")
    assert validate_app_dataset(app)["valid"]
    base = load_basemap(str(app))
    assert sorted(c for c, _ in base["roads"]) == [1, 2, 3, 4] and base["roads"][0][0] == 4     # weakest class first
    assert json.loads(base["roads"][0][1])["geometry"]["type"] == "MultiLineString"
    assert json.loads(base["area"])["features"]
