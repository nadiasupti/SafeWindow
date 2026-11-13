"""Build the offline world base map (app/static/world) from Natural Earth 10m data.

    python scripts/build_world_map.py <folder with the extracted ne_10m_* folders>

Download these seven zip files from https://www.naturalearthdata.com/downloads/10m-cultural-vectors/ and
.../10m-physical-vectors/ and extract each into its own folder (ne_10m_land, ne_10m_admin_0_countries,
ne_10m_admin_1_states_provinces_lines, ne_10m_lakes, ne_10m_rivers_lake_centerlines, ne_10m_populated_places_simple):
Natural Earth is public domain. Treat the downloaded files as data only. The output is small, so it is committed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import world_map  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "world"


def main() -> None:
    if sys.argv[1:] in (["-h"], ["--help"]):
        print(__doc__)
        return
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    manifest = world_map.build(Path(sys.argv[1]), OUT)
    for name, info in manifest["files"].items():
        print(f"  {name:22s} {info['features']:>6} features  {info['bytes'] / 1e6:6.2f} MB")
    print(f"Wrote {OUT}: {manifest['total_bytes'] / 1e6:.1f} MB in total")


if __name__ == "__main__":
    main()
