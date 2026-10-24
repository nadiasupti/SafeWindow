"""Villages, shelters and the study area (Step 3)."""
from __future__ import annotations

import warnings

import geopandas as gpd
import pandas as pd

from . import config

SHELTER_COLS = ["shelter_id", "name", "type", "lat", "lon", "source", "verified", "notes"]


def load_study_area(paths=None) -> gpd.GeoDataFrame:
    paths = paths or config.get_paths()
    return gpd.read_file(paths.study_area).to_crs(config.CRS)


def load_villages(paths=None) -> gpd.GeoDataFrame:
    paths = paths or config.get_paths()
    v = gpd.read_file(paths.villages).to_crs(config.CRS)
    v["village_id"] = v["village_id"].astype(str)
    if "population" not in v:
        v["population"] = pd.NA
    return v


def shelters_from_csv(path) -> gpd.GeoDataFrame:
    df = pd.read_csv(path, dtype={"shelter_id": str})
    missing = set(["shelter_id", "name", "lat", "lon"]) - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing columns {sorted(missing)}")
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=config.CRS_WGS84)
    return gdf.to_crs(config.CRS)


def shelters_from_local_list(path) -> gpd.GeoDataFrame:
    """A shelter list supplied with the region (e.g. from a disaster-management
    office): name, lat, lon, optional type, capacity and verified_by."""
    df = pd.read_csv(path)
    missing = {"name", "lat", "lon"} - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing columns {sorted(missing)}")
    if "shelter_id" not in df:
        df["shelter_id"] = [f"local{i + 1:04d}" for i in range(len(df))]
    df["shelter_id"] = df["shelter_id"].astype(str)
    df["type"] = df["type"] if "type" in df else "shelter"
    df["source"] = df["source"] if "source" in df else f"local list ({path.name})"
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=config.CRS_WGS84)
    return gdf.to_crs(config.CRS)


def load_shelters(paths=None) -> gpd.GeoDataFrame:
    """In order: the region's local shelter list (regions/*.yaml shelters_csv),
    the hand-checked list (only rows with verified == yes), otherwise the raw
    OpenStreetMap candidates with a warning."""
    paths = paths or config.get_paths()
    local = config.REGION.shelters_csv
    if local is not None:
        if not local.exists():
            raise FileNotFoundError(f"shelters_csv {local} from region {config.REGION.id!r} not found")
        return shelters_from_local_list(local)
    if paths.shelters_verified.exists():
        s = shelters_from_csv(paths.shelters_verified)
        if "verified" in s:
            s = s[s["verified"].astype(str).str.lower().isin(["yes", "y", "true", "1"])]
        if s.empty:
            raise ValueError(f"No rows marked verified=yes in {paths.shelters_verified}")
        return s
    warnings.warn(f"{paths.shelters_verified.name} not found - using unverified OSM candidates. "
                  "Hand-check them in shelter_checklist.csv (scripts/shelter_checklist.py).")
    return drop_rejected(clean_candidates(shelters_from_csv(paths.shelter_candidates)), paths.shelter_checklist)


def drop_rejected(s: gpd.GeoDataFrame, checklist_path) -> gpd.GeoDataFrame:
    """Leave out candidates the shelter checklist marks as not existing or not
    flood-safe. Unchecked candidates stay in until the checklist is applied."""
    if not checklist_path.exists():
        return s
    c = pd.read_csv(checklist_path, dtype=str, encoding="utf-8-sig").fillna("")
    no = {"no", "n", "false", "0"}
    rejected = c.loc[c["exists"].str.strip().str.lower().isin(no)
                     | c["flood_safe"].str.strip().str.lower().isin(no), "shelter_id"]
    return s[~s["shelter_id"].isin(set(rejected))]


def clean_candidates(s: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop OSM candidate types nobody can shelter in (shops), and give
    unnamed sites a readable label such as 'Unnamed school'."""
    if "type" not in s:
        return s
    s = s[~s["type"].isin(config.SHELTER_EXCLUDE_TYPES)].copy()
    unnamed = s["name"].isna() | (s["name"] == "(unnamed)")
    s.loc[unnamed, "name"] = "Unnamed " + s.loc[unnamed, "type"].fillna("facility").str.replace("_", " ")
    return s
