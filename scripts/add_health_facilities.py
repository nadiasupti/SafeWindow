"""Add the hospital and clinic layer (health.geojson) to built app packages.

    python scripts/add_health_facilities.py                 # every data/*/app
    python scripts/add_health_facilities.py live punjab_trimmu_2025

Source, in order: the region's `health_csv` list, OpenStreetMap (needs internet), then the hospitals and clinics
already in the shelter list. New floods get this from pipeline/08_build_app_data.py. All entries are candidates:
OpenStreetMap is incomplete and nothing here is verified.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import health  # noqa: E402
from safewindow import region as regions  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return
    wanted = sys.argv[1:]
    folders = sorted(p.parent.parent for p in DATA.glob("*/app/meta.json"))
    folders = [f for f in folders if not wanted or f.name in wanted]
    if not folders:
        sys.exit("no built app packages found")
    for folder in folders:
        app = folder / "app"
        meta = json.loads((app / "meta.json").read_text(encoding="utf-8"))
        reg = regions.load(meta.get("region") or regions.DEFAULT_REGION)
        shelters = gpd.read_file(app / "shelters.geojson")
        bbox = reg.bbox
        if bbox is None and (folder / "processed" / "study_area.gpkg").exists():
            bbox = tuple(gpd.read_file(folder / "processed" / "study_area.gpkg").to_crs("EPSG:4326").total_bounds)
        got = health.build(app, reg, shelters, bbox)
        print(f"{folder.name}: {got['n']} facilities from {got['source'] or 'no source'}")


if __name__ == "__main__":
    main()
