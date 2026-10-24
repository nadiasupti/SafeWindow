"""Study regions: everything that changes from one flood to the next.

A region is a YAML file in regions/ (see regions/sunamganj_2022.yaml). Pick one
with the environment variable SAFEWINDOW_REGION, either a file name in regions/
without ".yaml" or a path to a YAML file. The method settings (thresholds,
distances) are not part of a region: they stay in config.py so that every
region is analysed with the same rules.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REGIONS_DIR = Path(__file__).resolve().parent.parent / "regions"
DEFAULT_REGION = "sunamganj_2022"

# Where village points come from: OSM place nodes, or clusters of Google Open
# Buildings (candidate settlements, not official villages).
SETTLEMENT_SOURCES = ("osm", "open_buildings")

# Above this east-west extent a single UTM zone distorts distances noticeably.
MAX_AUTO_CRS_WIDTH_DEG = 6.0


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    admin_names: list[str]
    admin_unit: str
    parent: str
    parent_unit: str
    country: str
    iso3: str
    bbox: tuple[float, float, float, float] | None
    boundary_file: Path | None
    crs: str
    flood_start: date
    flood_end: date
    dry_start: str
    dry_end: str
    app_start: date
    app_end: date
    rain_boxes: dict[str, tuple[float, float, float, float]]
    rain_labels: dict[str, dict[str, str]]
    settlements: str
    shelters_csv: Path | None
    default_supply_days: int
    supply_days_range: tuple[int, int]
    languages: list[str]
    agencies: list[str]
    references: dict
    road_reports: list[dict]
    source: Path


def utm_epsg(lon: float, lat: float) -> str:
    """EPSG code of the WGS84 UTM zone that contains a point."""
    zone = min(int(math.floor((lon + 180) / 6)) + 1, 60)
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def auto_crs(bbox: tuple[float, float, float, float]) -> str:
    """UTM zone of the bbox centre; warns when the area is too wide for one zone."""
    west, south, east, north = bbox
    if utm_epsg(west, south) != utm_epsg(east, south):
        warnings.warn(f"bbox {bbox} spans more than one UTM zone; set 'crs' in the region file by hand.")
    if east - west > MAX_AUTO_CRS_WIDTH_DEG:
        warnings.warn(f"bbox {bbox} is wider than {MAX_AUTO_CRS_WIDTH_DEG} degrees; "
                      "choose a projection for this area by hand.")
    return utm_epsg((west + east) / 2, (south + north) / 2)


def resolve_path(name: str) -> Path:
    path = Path(name)
    if path.suffix in (".yaml", ".yml"):
        return path if path.is_absolute() else Path.cwd() / path
    return REGIONS_DIR / f"{name}.yaml"


def _day(value, field: str) -> date:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field}: {value!r} is not a YYYY-MM-DD date") from exc


def _pair(raw: dict, field: str) -> tuple[date, date]:
    value = raw.get(field)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"dates.{field} must be [start, end]")
    start, end = _day(value[0], f"dates.{field}"), _day(value[1], f"dates.{field}")
    if start > end:
        raise ValueError(f"dates.{field}: start {start} is after end {end}")
    return start, end


def _box(value, field: str) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{field} must be [west, south, east, north]")
    west, south, east, north = (float(v) for v in value)
    if not (west < east and south < north):
        raise ValueError(f"{field} must have west < east and south < north, got {value}")
    return west, south, east, north


def parse(raw: dict, source: Path) -> Region:
    """Build a Region from a parsed YAML mapping, with clear errors for missing fields."""
    for key in ("id", "area", "crs", "dates"):
        if key not in raw:
            raise ValueError(f"{source}: missing '{key}'")
    area = raw["area"]
    boundary = Path(area["boundary_file"]) if area.get("boundary_file") else None
    if boundary is not None and not boundary.is_absolute():
        boundary = source.parent / boundary
    if not area.get("admin_names") and boundary is None:
        raise ValueError(f"{source}: area needs admin_names (admin units) or boundary_file (a polygon file)")
    bbox = _box(area["bbox"], "area.bbox") if area.get("bbox") is not None else None

    crs = str(raw["crs"])
    if crs.lower() == "auto":
        if bbox is None:
            raise ValueError(f"{source}: crs 'auto' needs area.bbox")
        crs = auto_crs(bbox)

    dates = raw["dates"]
    flood_start, flood_end = _pair(dates, "flood")
    dry_start, dry_end = _pair(dates, "dry_reference")
    app_start, app_end = _pair(dates, "app") if "app" in dates else (flood_start, flood_end)

    supply = raw.get("supply_days", {})
    lo, hi, default = int(supply.get("min", 2)), int(supply.get("max", 14)), int(supply.get("default", 7))
    if not lo <= default <= hi:
        raise ValueError(f"{source}: supply_days default {default} is outside [{lo}, {hi}]")

    settlements = str(raw.get("settlements", "osm"))
    if settlements not in SETTLEMENT_SOURCES:
        raise ValueError(f"{source}: settlements must be one of {SETTLEMENT_SOURCES}, got {settlements!r}")
    iso3 = str(area.get("iso3", "")).upper()
    if iso3 and len(iso3) != 3:
        raise ValueError(f"{source}: area.iso3 must be a 3-letter country code such as BGD, got {iso3!r}")
    reports = []
    for i, rep in enumerate(raw.get("road_reports") or []):
        missing = {"id", "route", "event_date", "source", "url", "quote"} - set(rep)
        if missing:
            raise ValueError(f"{source}: road_reports[{i}] is missing {sorted(missing)}")
        entry = {**{k: str(v) for k, v in rep.items() if k not in ("from", "to")},
                 "event_date": _day(rep["event_date"], f"road_reports[{i}].event_date").isoformat()}
        if rep["route"] == "points":
            # a route between any two places, as lon/lat
            for end in ("from", "to"):
                xy = rep.get(end)
                if not isinstance(xy, (list, tuple)) or len(xy) != 2:
                    raise ValueError(f"{source}: road_reports[{i}] with route 'points' needs {end}: [lon, lat]")
                entry[end] = (float(xy[0]), float(xy[1]))
        reports.append(entry)
    # a local shelter list, relative to the region file
    shelters_csv = Path(raw["shelters_csv"]) if raw.get("shelters_csv") else None
    if shelters_csv is not None and not shelters_csv.is_absolute():
        shelters_csv = source.parent / shelters_csv

    return Region(
        id=str(raw["id"]),
        name=str(raw.get("name", raw["id"])),
        admin_names=[str(n) for n in area.get("admin_names") or []],
        admin_unit=str(area.get("admin_unit", "")),
        parent=str(area.get("parent", "")),
        parent_unit=str(area.get("parent_unit", "")),
        country=str(area.get("country", "")),
        iso3=iso3,
        bbox=bbox,
        boundary_file=boundary,
        crs=crs,
        flood_start=flood_start, flood_end=flood_end,
        dry_start=dry_start.isoformat(), dry_end=dry_end.isoformat(),
        app_start=app_start, app_end=app_end,
        rain_boxes={str(k): _box(v, f"rain_boxes.{k}") for k, v in (raw.get("rain_boxes") or {}).items()},
        rain_labels={str(k): {str(lang): str(text) for lang, text in v.items()}
                     for k, v in (raw.get("rain_labels") or {}).items()},
        settlements=settlements,
        shelters_csv=shelters_csv,
        default_supply_days=default,
        supply_days_range=(lo, hi),
        languages=list(raw.get("languages", ["en"])),
        agencies=list(raw.get("agencies", [])),
        references=dict(raw.get("references") or {}),
        road_reports=reports,
        source=source,
    )


def rain_label(r: Region, box: str, lang: str) -> str:
    """Display name of a rainfall box in a language, falling back to English, then the box name."""
    labels = r.rain_labels.get(box, {})
    return labels.get(lang) or labels.get("en") or box


def load(name: str = DEFAULT_REGION) -> Region:
    """Load a region by name (regions/<name>.yaml) or by path to a YAML file."""
    import yaml

    path = resolve_path(name)
    if not path.exists():
        available = sorted(p.stem for p in REGIONS_DIR.glob("*.yaml"))
        raise FileNotFoundError(f"Region {name!r} not found at {path}. Available: {available}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse(raw, path)
