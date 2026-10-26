"""A vector base map for the app, so the map is useful with no internet.

Satellite and street tiles need a network. The road network the engine already uses does not, so this
writes it into the app package as two small files:

    roads.geojson        every road, merged into four classes (1 major ... 4 tracks and paths)
    study_area.geojson   the outline of the study area

Both are optional: the app draws them when it runs offline or in low-data mode.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiLineString

WGS84 = "EPSG:4326"
ROAD_SIMPLIFY_M = 25       # a road is drawn within about this distance of its true line
ROAD_PRECISION = 4         # decimal places of a degree: about 11 m, finer than the map can show
AREA_SIMPLIFY_M = 100

MAJOR = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
MEDIUM = {"secondary", "tertiary", "secondary_link", "tertiary_link"}
MINOR = {"residential", "unclassified", "service", "living_street", "road"}


def road_class(highway) -> int:
    """1 major, 2 medium, 3 minor, 4 tracks and paths. OSM sometimes lists several tags: the first counts."""
    tag = str(highway).strip("[]'\" ").split(",")[0].strip("'\" ")
    return 1 if tag in MAJOR else 2 if tag in MEDIUM else 3 if tag in MINOR else 4


def _lines(geom):
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]


def build_roads(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One feature per road class, each a MultiLineString in WGS84."""
    g = edges.copy()
    g["c"] = g["highway"].map(road_class)
    g["geometry"] = g.geometry.simplify(ROAD_SIMPLIFY_M)
    rows = []
    for c, part in g.groupby("c"):
        lines = [ln for geom in part.geometry if geom is not None and not geom.is_empty for ln in _lines(geom)]
        rows.append({"c": int(c), "geometry": MultiLineString(lines)})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=edges.crs).to_crs(WGS84).sort_values("c")


def build(processed: Path, app: Path) -> dict:
    """Write roads.geojson and study_area.geojson into `app` from a flood's processed folder."""
    processed, app = Path(processed), Path(app)
    written = {}
    edges_path = processed / "road_edges.gpkg"
    if edges_path.exists():
        roads = build_roads(gpd.read_file(edges_path))
        roads.to_file(app / "roads.geojson", driver="GeoJSON", COORDINATE_PRECISION=ROAD_PRECISION)
        written["roads.geojson"] = (app / "roads.geojson").stat().st_size
    area_path = processed / "study_area.gpkg"
    if area_path.exists():
        area = gpd.read_file(area_path)
        outline = area.dissolve().geometry.simplify(AREA_SIMPLIFY_M)
        gpd.GeoDataFrame(geometry=outline, crs=area.crs).to_crs(WGS84).to_file(
            app / "study_area.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
        written["study_area.geojson"] = (app / "study_area.geojson").stat().st_size
    return written


def read_json_bounds(path: Path) -> list[float] | None:
    """[west, south, east, north] of a GeoJSON file, or None if it is empty."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)

    for f in data.get("features", []):
        walk(f["geometry"]["coordinates"])
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None
