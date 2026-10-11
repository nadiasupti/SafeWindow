"""Tests for shelter-candidate cleaning."""

import geopandas as gpd
from shapely.geometry import Point

from safewindow import config
from safewindow.places import clean_candidates


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
