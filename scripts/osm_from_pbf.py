"""Shelter candidates and health facilities from a Geofabrik .osm.pbf extract, with no Overpass server.

    python scripts/osm_from_pbf.py <extract.osm.pbf> <region id>          # shelters_candidates.csv for the region
    python scripts/osm_from_pbf.py <extract.osm.pbf> <region id> --health # also (re)write the package's health.geojson

Download the country file from https://download.geofabrik.de (OpenStreetMap data, ODbL: credit "© OpenStreetMap
contributors"). Needs the pipeline requirements (pyosmium). Output goes to data/<region>/processed/ (or the
folder in SAFEWINDOW_DATA_DIR) and is a candidate list: OpenStreetMap is incomplete and nothing here is verified.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from safewindow import health, osm_pbf  # noqa: E402
from safewindow import region as regions  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if any(a in ("-h", "--help") for a in sys.argv[1:]) or len(args) != 2:
        print(__doc__)
        return
    pbf, rid = Path(args[0]), args[1]
    if not pbf.exists():
        sys.exit(f"{pbf} not found")
    reg = regions.load(rid)
    if reg.bbox is None:
        sys.exit(f"region {rid} has no bbox")
    data = Path(os.environ.get("SAFEWINDOW_DATA_DIR") or ROOT / "data" / rid)
    elems = osm_pbf.elements(pbf, tuple(reg.bbox))
    frame = osm_pbf.shelter_frame(elems)
    out = data / "processed" / "shelters_candidates.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    print(f"{out}: {len(frame)} candidates")
    print(frame["type"].value_counts().head(8).to_string())
    if "--health" in sys.argv:
        app = data / "app"
        got = health.build(app, reg, None, tuple(reg.bbox), fetch=osm_pbf.health_fetch(pbf))
        print(f"{app / 'health.geojson'}: {got['n']} facilities from {got['source'] or 'no source'}")


if __name__ == "__main__":
    main()
