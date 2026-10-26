"""Add the offline vector base map (roads.geojson, study_area.geojson) to built app packages.

    python scripts/add_offline_basemap.py                # every data/*/app that has processed road data
    python scripts/add_offline_basemap.py live punjab_trimmu_2025

New floods get these files from pipeline/08_build_app_data.py automatically. This script is for packages
that were built before that step existed. It only adds two files; nothing else in the package changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import offline_basemap  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return
    wanted = sys.argv[1:]
    folders = sorted(p.parent.parent for p in DATA.glob("*/app/meta.json"))
    if wanted:
        folders = [f for f in folders if f.name in wanted]
    if not folders:
        sys.exit("no built app packages found")
    for folder in folders:
        written = offline_basemap.build(folder / "processed", folder / "app")
        if not written:
            print(f"{folder.name}: no processed road data, skipped")
            continue
        print(f"{folder.name}: " + ", ".join(f"{name} {size / 1e6:.2f} MB" for name, size in written.items()))


if __name__ == "__main__":
    main()
