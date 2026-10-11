"""Step 3 (bridges) - road bridges from OpenStreetMap.

    python pipeline/03c_bridges.py

Radar sees the water under a bridge, so without this step every bridge over a
flooded river looks like a flooded road and cuts the route. Writes
data/processed/bridges.gpkg: road ways tagged bridge=* (except bridge=no), as
lines in the project CRS. Step 5 then ignores flood pixels at check-points
that lie on a bridge; pixels with no radar data stay unknown.
"""
import argparse
import os
import time

import geopandas as gpd
import osmnx as ox
import requests

from safewindow import config
from safewindow.places import load_study_area


def download(poly_wgs84, attempts: int) -> gpd.GeoDataFrame:
    for attempt in range(1, attempts + 1):
        try:
            return ox.features_from_polygon(poly_wgs84, tags={"bridge": True})
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == attempts:
                raise
            time.sleep(2 * 2 ** (attempt - 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--buffer-m", type=float, default=1000, help="same buffer as step 3 uses for roads")
    ap.add_argument("--osm-attempts", type=int, default=4)
    args = ap.parse_args()
    ox.settings.overpass_url = os.environ.get("SAFEWINDOW_OSM_OVERPASS_URL", ox.settings.overpass_url)

    paths = config.get_paths().ensure()
    poly = load_study_area(paths).buffer(args.buffer_m).to_crs(config.CRS_WGS84).union_all()
    f = download(poly, args.osm_attempts).reset_index()
    if "highway" not in f:
        raise SystemExit("No road bridges found in OpenStreetMap for this area.")
    # A low-water crossing is built to go under water, so it is not an elevated bridge.
    lines = f[f.geometry.geom_type.isin(["LineString", "MultiLineString"])
              & f["highway"].notna() & ~f["bridge"].astype(str).isin(["no", "low_water_crossing"])]
    out = gpd.GeoDataFrame({
        "osm_id": lines["id"].astype(str),
        "highway": lines["highway"].astype(str),
        "bridge": lines["bridge"].astype(str),
        "name": lines["name"] if "name" in lines else None,
    }, geometry=lines.geometry.to_numpy(), crs=config.CRS_WGS84).to_crs(config.CRS)
    out.to_file(paths.bridges, driver="GPKG")
    print(f"{len(out)} road bridges, {out.length.sum() / 1000:.1f} km, saved to {paths.bridges}")
    print("  bridge types:", out["bridge"].value_counts().head(6).to_dict())


if __name__ == "__main__":
    main()
