"""Tests for shelter-candidate cleaning, local shelter lists and candidate settlements."""

import dataclasses
import importlib.util
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from safewindow import config
from safewindow.places import clean_candidates, load_shelters

POP_PATH = Path(__file__).parents[1] / "pipeline" / "03b_population.py"
SPEC = importlib.util.spec_from_file_location("population_pipeline", POP_PATH)
population_pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(population_pipeline)


def test_clean_candidates_drops_shops_and_labels_unnamed_sites():
    s = gpd.GeoDataFrame({
        "shelter_id": ["a", "b", "c", "d"],
        "name": ["High School", "(unnamed)", "Pharma Shop", None],
        "type": ["school", "hospital", "pharmacy", "community_centre"],
    }, geometry=[Point(0, i) for i in range(4)], crs=config.CRS)

    out = clean_candidates(s).set_index("shelter_id")

    assert "c" not in out.index
    assert out.loc["a", "name"] == "High School"
    assert out.loc["b", "name"] == "Unnamed hospital"
    assert out.loc["d", "name"] == "Unnamed community centre"


def test_shelter_checklist_keeps_only_confirmed_rows():
    import pandas as pd

    from scripts.shelter_checklist import confirmed

    checklist = pd.DataFrame({
        "shelter_id": ["a", "b", "c", "d"],
        "exists": ["yes", "Yes ", "no", ""],
        "flood_safe": ["yes", "no", "yes", "yes"],
    })
    assert confirmed(checklist)["shelter_id"].tolist() == ["a"]


def test_region_shelter_list_replaces_osm_candidates(tmp_path, monkeypatch):
    csv = tmp_path / "shelters.csv"
    pd.DataFrame({"name": ["Cyclone shelter 1", "School 2"], "lat": [25.0, 25.1], "lon": [91.4, 91.5],
                  "capacity": [500, 300], "verified_by": ["UNO office", "UNO office"]}).to_csv(csv, index=False)
    monkeypatch.setattr(config, "REGION", dataclasses.replace(config.REGION, shelters_csv=csv))

    s = load_shelters()

    assert s["shelter_id"].tolist() == ["local0001", "local0002"]
    assert s["type"].tolist() == ["shelter", "shelter"]
    assert s["capacity"].tolist() == [500, 300]
    assert s.crs == config.CRS


def test_missing_region_shelter_list_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REGION", dataclasses.replace(config.REGION, shelters_csv=tmp_path / "nope.csv"))
    with pytest.raises(FileNotFoundError, match="nope.csv"):
        load_shelters()


def test_building_clusters_are_labelled_candidate_settlements():
    # two dense blobs of 15 buildings, one next to an OSM village; plus scattered noise
    rng = np.random.default_rng(0)
    origin = gpd.GeoSeries([Point(91.40, 25.00)], crs=config.CRS_WGS84).to_crs(config.CRS).iloc[0]
    blobs = [(origin.x, origin.y), (origin.x + 5000, origin.y)]
    xy = np.vstack([np.column_stack([rng.normal(x, 15, 15), rng.normal(y, 15, 15)]) for x, y in blobs]
                   + [np.array([[origin.x + 2500, origin.y + 3000]])])
    pts = gpd.GeoSeries(gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=config.CRS).to_crs(config.CRS_WGS84)
    buildings = pd.DataFrame({"lon": pts.x, "lat": pts.y})
    osm = gpd.GeoDataFrame({"name": ["Dholkotob", "Far away"], "name_bn": [None, None]},
                           geometry=[Point(origin.x + 200, origin.y), Point(origin.x, origin.y + 20000)],
                           crs=config.CRS)

    clusters = population_pipeline.cluster_buildings(buildings, osm).sort_values("n_buildings")
    check = population_pipeline.settlement_check(clusters, osm)

    assert len(clusters) == 2
    assert (clusters["place"] == "candidate_settlement").all()
    names = sorted(clusters["name"])
    assert names[0].startswith("Candidate settlement ") and names[1] == "Candidate settlement near Dholkotob"
    assert check["candidate_settlements"] == 2
    assert check["osm_villages_with_a_cluster"] == 1 and check["osm_village_match_rate"] == 0.5
    assert check["clusters_near_an_osm_village"] == 1
