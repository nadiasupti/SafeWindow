"""Create a region file for a new flood anywhere on Earth.

A region is data, not code: this writes regions/<id>.yaml plus a rectangular
study-area polygon, checks the result with the normal region loader, and
returns the commands to run next. It does not download anything.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import region as regions

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
DEFAULT_AGENCY = "local disaster-management authorities"
DRY_DEFAULT_DAYS = 90      # same default as pipeline/10_build_live_data.py

PIPELINE_STEPS = [
    "pipeline/01_study_area.py", "pipeline/02a_sentinel1_gee.py",
    "pipeline/02e_merge_flood.py --sources sentinel1", "pipeline/03_osm_roads_places.py",
    "pipeline/03b_population.py --worldpop-gee", "pipeline/03c_bridges.py", "pipeline/04_rainfall_gpm.py",
    "pipeline/05_cut_roads.py", "pipeline/06_isolation.py", "pipeline/07_timeline.py",
    "pipeline/08_build_app_data.py",
]


def available_languages() -> list[str]:
    return sorted(p.stem for p in LOCALES_DIR.glob("*.json"))


def _check(region_id: str, bbox, iso3: str, languages: list[str], flood: tuple[date, date]) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", region_id):
        raise ValueError(f"id {region_id!r} must be lowercase letters, digits and underscores, e.g. lagos_2026")
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"bbox {bbox} must be west south east north in degrees, with west < east and south < north")
    if len(iso3) != 3 or not iso3.isalpha():
        raise ValueError(f"iso3 {iso3!r} must be a 3-letter country code such as NGA (WorldPop uses it)")
    unknown = [lang for lang in languages if lang not in available_languages()]
    if unknown:
        raise ValueError(f"no locale file for {unknown}; available: {available_languages()}")
    if flood[0] > flood[1]:
        raise ValueError("flood start is after flood end")


def build(region_id: str, name: str, bbox: tuple[float, float, float, float], iso3: str, country: str,
          flood_start: date, flood_end: date, dry_start: date | None = None, dry_end: date | None = None,
          languages: list[str] | None = None, agencies: list[str] | None = None,
          contacts: list[tuple[str, str]] | None = None, out_dir: Path = regions.REGIONS_DIR) -> dict:
    """Write the region file and AOI polygon. Returns the paths, warnings and next commands."""
    languages = languages or ["en"]
    _check(region_id, bbox, iso3.upper(), languages, (flood_start, flood_end))
    warnings = []
    if dry_start is None or dry_end is None:
        dry_end = flood_start - timedelta(days=1)
        dry_start = dry_end - timedelta(days=DRY_DEFAULT_DAYS - 1)
        warnings.append(f"dry reference defaulted to {dry_start} to {dry_end}. It must be a dry, unflooded season "
                        "for the area: set --dry-start and --dry-end if it is not.")
    out_dir = Path(out_dir)
    yaml_path, aoi_path = out_dir / f"{region_id}.yaml", out_dir / f"{region_id}_aoi.geojson"
    if yaml_path.exists() or aoi_path.exists():
        raise FileExistsError(f"{yaml_path.name} or {aoi_path.name} already exists; pick another id")
    west, south, east, north = bbox
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    aoi = {"type": "FeatureCollection", "name": f"{region_id}_aoi",
           "features": [{"type": "Feature", "properties": {"name": name, "source": "rectangle from bbox"},
                         "geometry": {"type": "Polygon", "coordinates": [ring]}}]}
    agencies = agencies or [DEFAULT_AGENCY]
    contact_lines = "".join(f"  - {{name: {json.dumps(n, ensure_ascii=False)}, number: {json.dumps(num)}}}\n"
                            for n, num in contacts or [])
    text = f"""# SafeWindow region for {name}. Created by scripts/new_region.py.
# Method thresholds are not here: every region is analysed with the same rules (safewindow/config.py).

id: {region_id}
name: {json.dumps(name, ensure_ascii=False)}

area:
  boundary_file: {aoi_path.name}     # a rectangle from the bbox; replace with the real outline if you have one
  country: {json.dumps(country, ensure_ascii=False)}
  iso3: {iso3.upper()}               # WorldPop country code
  bbox: [{west}, {south}, {east}, {north}]   # lon/lat: west, south, east, north

crs: auto                            # UTM zone of the bbox centre; set an EPSG code by hand if it warns

dates:
  flood: ["{flood_start}", "{flood_end}"]
  dry_reference: ["{dry_start}", "{dry_end}"]   # a dry, unflooded season for this area
  app: ["{flood_start}", "{flood_end}"]

rain_boxes:
  area: [{west}, {south}, {east}, {north}]   # add an upstream box where rain far away drives the flood
rain_labels:
  area: {{en: "Study area"}}

settlements: osm
shelters_csv: null                   # a local list (name, lat, lon) is better than OSM candidates

supply_days: {{default: 7, min: 2, max: 14}}   # ASSUMPTION, not a measurement

languages: {json.dumps(languages)}
agencies: {json.dumps(agencies, ensure_ascii=False)}

# Numbers printed on the evacuation card. Without any, the card shows the international number 112.
# Check every number with local partners before use.
emergency_contacts:
{contact_lines if contact_lines else "  []"}
"""
    # validate with the real loader before anything is kept
    region = regions.parse(yaml.safe_load(text), yaml_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(text, encoding="utf-8", newline="\n")
    aoi_path.write_text(json.dumps(aoi, indent=1), encoding="utf-8", newline="\n")
    data_dir = f"data/{region_id}"
    commands = [f'$env:SAFEWINDOW_REGION="{region_id}"; $env:SAFEWINDOW_DATA_DIR="{data_dir}"; $env:EE_PROJECT="<your-project>"']
    commands += [f"python {step}" for step in PIPELINE_STEPS]
    commands.append("python -m streamlit run app/streamlit_app.py")
    return {"region": region, "yaml": yaml_path, "aoi": aoi_path, "warnings": warnings, "commands": commands,
            "data_dir": data_dir}
