"""Project-wide settings and file locations.

Every pipeline step and the app read paths from here, so the folder layout
lives in one place. Set the environment variable SAFEWINDOW_DATA_DIR to point
the whole project at another data folder (the synthetic demo uses
``data_demo``).

Settings that change from one flood to the next (area, projection, dates,
rainfall boxes, supply days) come from a region file in regions/, chosen with
SAFEWINDOW_REGION (default: sunamganj_2022). Method settings below the region
block are the same for every region.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import region as _region

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = "data/live"

REGION = _region.load(os.environ.get("SAFEWINDOW_REGION", _region.DEFAULT_REGION))

# --- Study area (Step 1) -----------------------------------------------------
# Admin units to analyse. Change them in the region file after checking OSM
# road coverage (pipeline/01_study_area.py --rank).
UPAZILAS = REGION.admin_names
DISTRICT = REGION.parent
COUNTRY = REGION.country

# One projection for everything, units in metres.
CRS = REGION.crs
CRS_WGS84 = "EPSG:4326"

# Common flood-map grid. Every flood source is written onto this grid so that
# sources can be merged pixel by pixel.
GRID_RES_M = 20

# --- Time window --------------------------------------------------------------
DRY_REF_START, DRY_REF_END = REGION.dry_start, REGION.dry_end
FLOOD_START, FLOOD_END = REGION.flood_start, REGION.flood_end
APP_START, APP_END = REGION.app_start, REGION.app_end

# --- Flood raster encoding ---------------------------------------------------
DRY, FLOODED, UNKNOWN = 0, 1, 255

# When several sources exist for one date, pixels are filled in this order:
# a lower-ranked source only fills pixels still unknown after the ones above.
SOURCE_PRIORITY = ["sentinel1", "unosat", "dem_estimate", "modis"]

# --- Road cutting (Step 5) ------------------------------------------------------
SAMPLE_SPACING_M = 20
CUT_THRESHOLD = 0.20                     # main result
SENSITIVITY_THRESHOLDS = [0.10, 0.20, 0.40]
UNKNOWN_MAJORITY = 0.50                  # > this share unknown -> road "unknown"
BRIDGE_TOL_M = 3                         # check-point this close to a mapped bridge lies on it

# --- Isolation (Step 6) ----------------------------------------------------------
BOAT_DEPENDENT_M = 500                   # village farther than this from a road
SHELTER_SNAP_MAX_M = 1000                # shelter farther than this is not road-reachable
# OSM candidate types that are not places people can shelter in
SHELTER_EXCLUDE_TYPES = ("pharmacy",)

# --- Survival Clock (Step 7) --------------------------------------------------------
# ASSUMPTION, not a measurement: days of food/water a household has on hand.
# Replace with a sourced figure (e.g. a household survey from the haor region)
# and cite it in the README and pitch.
DEFAULT_SUPPLY_DAYS = REGION.default_supply_days
SUPPLY_DAYS_RANGE = REGION.supply_days_range

# --- Rainfall boxes (Step 4), lon/lat: (west, south, east, north) ---------------
RAIN_BOXES = REGION.rain_boxes


@dataclass(frozen=True)
class Paths:
    data: Path

    @property
    def raw(self) -> Path: return self.data / "raw"
    @property
    def processed(self) -> Path: return self.data / "processed"
    @property
    def results(self) -> Path: return self.data / "results"
    @property
    def app(self) -> Path: return self.data / "app"

    # processed inputs
    @property
    def study_area(self) -> Path: return self.processed / "study_area.gpkg"
    @property
    def grid(self) -> Path: return self.processed / "grid.json"
    @property
    def flood_dir(self) -> Path: return self.processed / "flood"
    @property
    def flood_manifest(self) -> Path: return self.flood_dir / "manifest.csv"
    @property
    def merged_flood_dir(self) -> Path: return self.processed / "flood_merged"
    @property
    def roads_graph(self) -> Path: return self.processed / "roads.graphml"   # raw osmnx graph
    @property
    def road_nodes(self) -> Path: return self.processed / "road_nodes.gpkg"
    @property
    def road_edges(self) -> Path: return self.processed / "road_edges.gpkg"
    @property
    def bridges(self) -> Path: return self.processed / "bridges.gpkg"
    @property
    def villages(self) -> Path: return self.processed / "villages.gpkg"
    @property
    def shelter_candidates(self) -> Path: return self.processed / "shelters_candidates.csv"
    @property
    def shelters_verified(self) -> Path: return self.processed / "shelters_verified.csv"
    @property
    def rainfall(self) -> Path: return self.processed / "rainfall_daily.csv"
    @property
    def modis_timeline(self) -> Path: return self.processed / "modis_flood_area.csv"

    # results
    @property
    def road_status(self) -> Path: return self.results / "road_status.csv"
    @property
    def village_status(self) -> Path: return self.results / "village_status.csv"
    @property
    def village_summary(self) -> Path: return self.results / "village_summary.csv"
    @property
    def exit_routes(self) -> Path: return self.results / "exit_routes.gpkg"
    @property
    def sensitivity(self) -> Path: return self.results / "sensitivity.csv"
    @property
    def validation_reports(self) -> Path: return self.data / "validation" / "news_reports.csv"
    @property
    def validation_results(self) -> Path: return self.results / "validation.csv"

    def ensure(self) -> "Paths":
        for p in (self.raw, self.processed, self.results, self.app,
                  self.flood_dir, self.merged_flood_dir):
            p.mkdir(parents=True, exist_ok=True)
        return self


def utf8_console() -> None:
    """Let scripts print Bengali village names on a Windows (cp1252) console."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def get_paths() -> Paths:
    data = Path(os.environ.get("SAFEWINDOW_DATA_DIR", ROOT / DEFAULT_DATA_DIR))
    if not data.is_absolute():
        data = ROOT / data
    return Paths(data)
