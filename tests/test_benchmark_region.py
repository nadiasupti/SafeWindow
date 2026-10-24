"""Tests for the region benchmark: unions of maps, date gaps and excluded (cloud) areas."""

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from safewindow import config
from safewindow.flood import Grid, write_flood_map
from scripts.benchmark_region import gap_days, prediction, reference_mask

F, D, U = config.FLOODED, config.DRY, config.UNKNOWN


class FakePaths:
    def __init__(self, flood_dir):
        self.flood_dir = flood_dir


def test_union_prediction_is_flooded_if_flooded_on_any_date(tmp_path):
    grid = Grid(0.0, 60.0, 3, 1, 20.0)
    write_flood_map(np.array([[F, D, U]], "uint8"), grid, tmp_path / "sentinel1_20240619.tif")
    write_flood_map(np.array([[D, F, U]], "uint8"), grid, tmp_path / "sentinel1_20240622.tif")

    union, files = prediction(FakePaths(tmp_path), "2024-06-19+2024-06-22")
    single, _ = prediction(FakePaths(tmp_path), "2024-06-19")

    assert union.tolist() == [[F, F, U]]
    assert single.tolist() == [[F, D, U]]
    assert [f.name for f in files] == ["sentinel1_20240619.tif", "sentinel1_20240622.tif"]


def test_gap_days_sign_and_unions():
    assert gap_days("2024-06-26", "2024-06-24") == -2       # our map two days earlier
    assert gap_days("2024-06-26", "2024-06-29") == 3
    assert gap_days("2024-06-19+2024-06-22", "2024-06-19+2024-06-22") == 3
    assert gap_days("2024-06-19+2024-06-22", "2024-06-19") == -3


def test_excluded_cloud_is_left_out_of_the_reference(tmp_path):
    # three 20 m cells near Sunamganj; UNOSAT shapefiles come in lon/lat, like these
    x0, y0 = 600000.0, 2770000.0
    grid = Grid(x0, y0 + 20, 3, 1, 20.0)

    def save(geom, name):
        gpd.GeoDataFrame(geometry=[geom], crs=config.CRS).to_crs(config.CRS_WGS84).to_file(tmp_path / f"{name}.shp")

    save(box(x0, y0, x0 + 60, y0 + 20), "analysis")
    save(box(x0, y0, x0 + 20, y0 + 20), "flood")
    save(box(x0 + 40, y0, x0 + 60, y0 + 20), "cloud")
    study = gpd.GeoDataFrame({"upazila": ["x"]}, geometry=[box(x0, y0, x0 + 60, y0 + 20)], crs=config.CRS)
    ref = {"flood": "flood", "analysis": "analysis", "exclude": "cloud"}

    assert reference_mask(tmp_path, ref, grid, study).tolist() == [[F, D, U]]

    # exclude_where keeps only matching features: the 'Image Footprint' row must not blank the image
    footprint = gpd.GeoDataFrame({"obj_type": ["Image Footprint", "Not Analysed - No data"]},
                                 geometry=[box(x0, y0, x0 + 60, y0 + 20), box(x0 + 40, y0, x0 + 60, y0 + 20)],
                                 crs=config.CRS)
    footprint.to_crs(config.CRS_WGS84).to_file(tmp_path / "footprint.shp")
    ref = {"flood": "flood", "analysis": "analysis", "exclude": "footprint",
           "exclude_where": {"obj_type": "Not Analysed - No data"}}
    assert reference_mask(tmp_path, ref, grid, study).tolist() == [[F, D, U]]
