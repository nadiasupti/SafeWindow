"""Mapped buildings in each flood: road access to a shelter, nearness to mapped water, and where to check first.

    python scripts/building_exposure.py fetch data/live               # Google Open Buildings, needs Earth Engine
    python scripts/building_exposure.py fetch data/sunamganj_2024 --copy-from data/live   # same study area
    python scripts/building_exposure.py run                           # every package that has buildings

fetch: Google Open Buildings v3 footprints with confidence >= 0.75 inside the study area, as centroids, into
       <package>/raw/open_buildings_centroids.csv (lon, lat, confidence, area_in_meters).
run:   per radar date, each building gets the village rule (connected / isolated / uncertain, or far from roads),
       and whether mapped flood water lies within 50 m (safewindow/buildings.py). Writes <package>/results/:
         buildings_cells.csv         buildings summed per 500 m cell (CELL_M), per date
         buildings_clusters.csv      neighbouring cells with buildings seen isolated, ranked for field verification
         buildings_summary.json      totals per date and the method, for the app

Reads only the pipeline's own outputs (roads, shelters, road status, flood maps). Limits: a mapped building is not
a count of people; "near mapped water" is not "flooded inside" (radar often misses water between buildings);
shelters are unverified candidates. A ranking of where to check first, not a rescue list.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MIN_CONFIDENCE = 0.75
SOURCE = "Google Open Buildings v3 (confidence >= 0.75)"


def use_package(pkg: Path) -> dict:
    meta = json.loads((pkg / "app" / "meta.json").read_text(encoding="utf-8"))
    os.environ["SAFEWINDOW_REGION"] = meta.get("region") or pkg.name
    os.environ["SAFEWINDOW_DATA_DIR"] = str(pkg)
    return meta


def fetch(pkg: Path) -> None:
    use_package(pkg)
    from safewindow import config, gee
    paths = config.get_paths()
    ee = gee.init()
    aoi = gee.study_area_geometry(paths)
    fc = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
          .filterBounds(aoi).filter(ee.Filter.gte("confidence", MIN_CONFIDENCE))
          .map(lambda f: ee.Feature(None, {"lon": f.geometry().centroid(1).coordinates().get(0),
                                           "lat": f.geometry().centroid(1).coordinates().get(1),
                                           "confidence": f.get("confidence"), "area_in_meters": f.get("area_in_meters")})))
    df = pd.read_csv(fc.getDownloadURL(filetype="csv", selectors=["lon", "lat", "confidence", "area_in_meters"]))
    paths.raw.mkdir(parents=True, exist_ok=True)
    df.to_csv(paths.raw / "open_buildings_centroids.csv", index=False)
    print(f"{pkg.name}: {len(df):,} buildings")


def load_buildings(pkg: Path, crs) -> np.ndarray | None:
    """Building centroids (x, y) in the network's projection, or None if the package has no building file."""
    import geopandas as gpd
    f = pkg / "raw" / "open_buildings_centroids.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    df = df[df["confidence"] >= MIN_CONFIDENCE] if "confidence" in df else df
    pts = gpd.GeoSeries(gpd.points_from_xy(df["lon"], df["lat"]), crs=4326).to_crs(crs)
    return np.column_stack([pts.x, pts.y])


def run(pkg: Path) -> dict | None:
    import geopandas as gpd
    import rasterio
    from rasterio.transform import rowcol

    meta = use_package(pkg)
    from safewindow import config
    from safewindow.buildings import (CELL_M, NEAR_WATER_M, cells, dry_reach, near_water, priority_clusters,
                                      snap_buildings, status_codes)
    from safewindow.flood import Grid, merged_path
    from safewindow.roads import load_network
    paths = config.get_paths()
    nodes, edges = load_network(paths)
    xy = load_buildings(pkg, nodes.crs)
    if xy is None:
        print(f"{pkg.name}: no buildings (run `fetch` first)")
        return None
    grid = Grid.load(paths.grid)
    b = snap_buildings(xy, nodes)
    shelters = pd.read_csv(pkg / "results" / "shelters_snapped.csv", dtype={"node_id": str})
    shelter_nodes = shelters.loc[shelters["road_reachable"].astype(bool), "node_id"].tolist()
    status = pd.read_csv(pkg / "results" / "road_status.csv", dtype={"edge_id": str})
    status["date"] = pd.to_datetime(status["date"]).dt.strftime("%Y-%m-%d")
    col = f"status_{round(meta.get('cut_threshold', 0.2) * 100)}"
    dates = list(meta["dates"])
    # buildings in the grid's projection, for the flood maps
    gx = gpd.GeoSeries(gpd.points_from_xy(b["x"], b["y"]), crs=nodes.crs).to_crs(grid.crs)
    rows, cols = rowcol(grid.transform, gx.x.to_numpy(), gx.y.to_numpy())
    rows, cols = np.asarray(rows), np.asarray(cols)

    linked = dry_reach(edges, shelter_nodes)
    codes, near, unseen = [], [], []
    for day in dates:
        rs = status[status["date"] == day].set_index("edge_id")[col]
        codes.append(status_codes(edges, rs, b, shelter_nodes, linked))
        with rasterio.open(merged_path(day, paths)) as src:
            flood = src.read(1)
        n, u = near_water(flood, rows, cols)
        near.append(n)
        unseen.append(u)

    cell_df = cells(b, codes, near)
    cl = priority_clusters(cell_df, dates)
    to_ll = lambda x, y: gpd.GeoSeries(gpd.points_from_xy(x, y), crs=nodes.crs).to_crs(4326)  # noqa: E731
    ll = to_ll(cell_df["x"], cell_df["y"])
    cell_df["lat"], cell_df["lon"] = ll.y.round(5), ll.x.round(5)
    if len(cl):
        ll = to_ll(cl["x"], cl["y"])
        cl["lat"], cl["lon"] = ll.y.round(5), ll.x.round(5)
        # the nearest village, to name each cluster
        v = gpd.read_file(pkg / "app" / "villages.geojson").to_crs(nodes.crs)
        cpts = gpd.GeoSeries(gpd.points_from_xy(cl["x"], cl["y"]), crs=nodes.crs)
        d = np.array([[p.distance(q) for q in v.geometry] for p in cpts])
        cl["nearest_village_id"] = v["village_id"].astype(str).to_numpy()[d.argmin(1)]
        cl["nearest_village_km"] = (d.min(1) / 1000).round(1)

    totals = []
    for k, day in enumerate(dates):
        c = codes[k]
        totals.append({"date": day, "isolated": int((c == "i").sum()), "uncertain": int((c == "u").sum()),
                       "connected": int((c == "c").sum()), "far_from_roads": int((c == "b").sum()),
                       "no_road_link": int((c == "n").sum()),
                       "near_water": int(near[k].sum()), "not_seen": int(unseen[k].sum())})
    out = pkg / "results"
    cell_df.drop(columns=["x", "y"]).to_csv(out / "buildings_cells.csv", index=False)
    cl.drop(columns=["x", "y"], errors="ignore").to_csv(out / "buildings_clusters.csv", index=False)
    summary = {"source": SOURCE, "buildings": int(len(b)), "far_from_roads": int(b["far"].sum()),
               "no_road_link": int((codes[0] == "n").sum()) if codes else 0,
               "cell_m": CELL_M, "near_water_m": NEAR_WATER_M, "cut_threshold": meta.get("cut_threshold"),
               "dates": dates, "totals": totals, "clusters": int(len(cl)),
               "score": "building-dates seen isolated: the sum over radar dates of the buildings seen isolated"}
    (out / "buildings_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    worst = max(totals, key=lambda t: t["isolated"])
    print(f"{pkg.name}: {len(b):,} buildings ({int(b['far'].sum()):,} far from roads); most isolated on "
          f"{worst['date']}: {worst['isolated']:,}; {len(cl)} clusters to check")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["fetch", "run"])
    ap.add_argument("packages", nargs="*", type=Path)
    ap.add_argument("--copy-from", type=Path, help="fetch: copy the building file of a package with the same study area")
    a = ap.parse_args()
    pkgs = a.packages or sorted(p.parent for p in (ROOT / "data").glob("*/app") if (p / "meta.json").exists())
    for pkg in pkgs:
        if a.action == "fetch":
            if a.copy_from:
                (pkg / "raw").mkdir(parents=True, exist_ok=True)
                shutil.copy2(a.copy_from / "raw" / "open_buildings_centroids.csv", pkg / "raw" / "open_buildings_centroids.csv")
                print(f"{pkg.name}: copied from {a.copy_from.name}")
            else:
                fetch(pkg)
        else:
            run(pkg)


if __name__ == "__main__":
    main()
