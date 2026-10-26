"""A world base map that works with no internet, built from Natural Earth (public domain).

Natural Earth is cartographic data: coastlines, countries, borders, lakes, rivers and cities. It is enough to place any
flood on the globe and zoom from the whole world down to a region. Streets come from each flood's own package
(roads.geojson), never from here.

Each output feature carries `z`, the lowest web-map zoom at which Natural Earth recommends showing it, so the app draws
only what a given zoom level can use.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

VERSION = "5.1.1"
LANGS = ("bn", "hi", "ur", "es", "fr", "pt")          # languages the app has, where Natural Earth names exist
PRECISION = 3                                         # decimal places of a degree: about 110 m
SIMPLIFY_DEG = {"land": 0.012, "countries": 0.012, "admin1_lines": 0.012, "lakes": 0.006, "rivers": 0.01}
CREDIT = ("Natural Earth (public domain). All versions of Natural Earth vector map data are in the public domain: "
          "https://www.naturalearthdata.com/about/terms-of-use/. Version {version}. Made with Natural Earth.")


def _zoom(series: pd.Series, default: float = 0.0) -> pd.Series:
    return series.astype(float).fillna(default).clip(lower=0).round().astype(int)


def _read(ne_dir: Path, name: str) -> gpd.GeoDataFrame:
    path = Path(ne_dir) / name / f"{name}.shp"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: extract the Natural Earth 10m zip files first")
    return gpd.read_file(path).to_crs("EPSG:4326")


def _lower(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = g.copy()
    g.columns = [c.lower() if c != "geometry" else c for c in g.columns]
    return g


def _simplified(g: gpd.GeoDataFrame, layer: str) -> gpd.GeoDataFrame:
    g = g.copy()
    g["geometry"] = g.geometry.simplify(SIMPLIFY_DEG[layer], preserve_topology=True)
    return g[~g.geometry.is_empty & g.geometry.notna()]


def merge_by_zoom(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One multi-part shape per zoom level. A browser draws thousands of separate SVG paths slowly, a handful of
    multi-part shapes quickly, and these layers have no per-feature data to keep."""
    from shapely.geometry import MultiLineString, MultiPolygon

    def parts(geom):
        return list(geom.geoms) if hasattr(geom, "geoms") else [geom]

    rows = []
    for z, part in g.groupby("z"):
        pieces = [p for geom in part.geometry for p in parts(geom)]
        lines = [p for p in pieces if p.geom_type == "LineString"]
        polys = [p for p in pieces if p.geom_type == "Polygon"]
        rows.append({"z": int(z), "geometry": MultiLineString(lines) if lines else MultiPolygon(polys)})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=g.crs)


def layers(ne_dir: Path) -> dict[str, gpd.GeoDataFrame]:
    """The six layers, trimmed to the fields the app uses."""
    land = _lower(_read(ne_dir, "ne_10m_land"))
    land["z"] = 0

    c = _lower(_read(ne_dir, "ne_10m_admin_0_countries"))
    names = {f"name_{lang}": f"name_{lang}" for lang in LANGS if f"name_{lang}" in c.columns}
    countries = c[["name", "geometry", *names, "label_x", "label_y", "min_label", "max_label"]].copy()
    countries["z"] = 0
    countries["min_label"] = countries["min_label"].astype(float).round(1)
    countries["max_label"] = countries["max_label"].astype(float).round(1)

    a1 = _lower(_read(ne_dir, "ne_10m_admin_1_states_provinces_lines"))
    admin1 = a1[["geometry"]].copy()
    admin1["z"] = _zoom(a1["min_zoom"], 3)

    lk = _lower(_read(ne_dir, "ne_10m_lakes"))
    lakes = lk[["geometry"]].copy()
    lakes["z"] = _zoom(lk["min_zoom"], 1)

    rv = _lower(_read(ne_dir, "ne_10m_rivers_lake_centerlines"))
    rivers = rv[["geometry"]].copy()
    rivers["z"] = _zoom(rv["min_zoom"], 3)

    pl = _lower(_read(ne_dir, "ne_10m_populated_places_simple"))
    places = pl[["name", "adm0name", "pop_max", "geometry"]].copy()
    places["z"] = _zoom(pl["min_zoom"], 5)
    places["capital"] = pl["featurecla"].astype(str).str.contains("capital", case=False).astype(int)
    places["pop_max"] = places["pop_max"].fillna(0).astype(int)
    places = places.rename(columns={"adm0name": "country"})

    return {"land": _simplified(land[["z", "geometry"]], "land"), "countries": _simplified(countries, "countries"),
            "admin1_lines": merge_by_zoom(_simplified(admin1, "admin1_lines")), "lakes": merge_by_zoom(_simplified(lakes, "lakes")),
            "rivers": merge_by_zoom(_simplified(rivers, "rivers")), "places": places}


def build(ne_dir: Path, out_dir: Path) -> dict:
    """Write the layers, a credit file and a manifest (sizes and SHA-256) into out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"source": "Natural Earth", "version": VERSION, "license": "public domain", "files": {}}
    for name, gdf in layers(ne_dir).items():
        path = out_dir / f"{name}.geojson"
        gdf.to_file(path, driver="GeoJSON", COORDINATE_PRECISION=PRECISION)
        data = path.read_bytes()
        manifest["files"][path.name] = {"bytes": len(data), "features": len(gdf), "sha256": hashlib.sha256(data).hexdigest()}
    (out_dir / "NATURAL_EARTH.txt").write_text(CREDIT.format(version=VERSION) + "\n", encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    manifest["total_bytes"] = sum(f["bytes"] for f in manifest["files"].values())
    return manifest
