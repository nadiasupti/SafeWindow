"""Create a region file for a new flood, anywhere on Earth.

    python scripts/new_region.py --id lagos_2026 --name "Lagos, Nigeria: 2026 flood" \\
        --bbox 3.20 6.40 3.70 6.70 --iso3 NGA --country Nigeria \\
        --flood-start 2026-07-01 --flood-end 2026-08-15 \\
        --dry-start 2026-01-10 --dry-end 2026-02-20 --languages en,fr \\
        --agencies "NEMA,NIHSA" --contact "Emergency=112"

It writes regions/<id>.yaml and regions/<id>_aoi.geojson and prints the commands to build the data.
Nothing is downloaded. Building the data needs Google Earth Engine (see README, Running SafeWindow on a new flood).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import scaffold  # noqa: E402

LIMITS = """Before you trust the result, check where SafeWindow works:
  - Sentinel-1 radar must cover the area on enough dates (a gap of 6-12 days is normal; fast floods can be missed).
  - Dense cities, forest and flooded crops are hard for C-band radar: expect missed or false flood there.
  - Roads, villages and shelters come from OpenStreetMap: check they exist in your area.
  - The method is validated against independent maps only in Bangladesh and Pakistan. Elsewhere it is unvalidated.
  - Output is a research estimate, never an official warning."""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="short name, lowercase, e.g. lagos_2026")
    ap.add_argument("--name", required=True, help="display name shown in the app")
    ap.add_argument("--bbox", required=True, nargs=4, type=float, metavar=("W", "S", "E", "N"), help="lon/lat degrees")
    ap.add_argument("--iso3", required=True, help="3-letter country code for WorldPop, e.g. NGA")
    ap.add_argument("--country", required=True)
    ap.add_argument("--flood-start", required=True, type=date.fromisoformat)
    ap.add_argument("--flood-end", required=True, type=date.fromisoformat)
    ap.add_argument("--dry-start", type=date.fromisoformat)
    ap.add_argument("--dry-end", type=date.fromisoformat)
    ap.add_argument("--languages", default="en", help=f"comma list from {scaffold.available_languages()}")
    ap.add_argument("--agencies", default="", help="comma list of official warning agencies")
    ap.add_argument("--contact", action="append", default=[], metavar="NAME=NUMBER", help="emergency number, repeatable")
    a = ap.parse_args()
    try:
        contacts = [tuple(c.split("=", 1)) for c in a.contact]
        if any(len(c) != 2 for c in contacts):
            raise ValueError("--contact must look like NAME=NUMBER")
        result = scaffold.build(
            a.id, a.name, tuple(a.bbox), a.iso3, a.country, a.flood_start, a.flood_end, a.dry_start, a.dry_end,
            languages=[x.strip() for x in a.languages.split(",") if x.strip()],
            agencies=[x.strip() for x in a.agencies.split(",") if x.strip()] or None, contacts=contacts)
    except (ValueError, FileExistsError) as exc:
        sys.exit(f"error: {exc}")
    print(f"Wrote {result['yaml']}\nWrote {result['aoi']}")
    for w in result["warnings"]:
        print(f"WARNING: {w}")
    print("\nNext, in PowerShell from the repository root (steps marked by the README need Earth Engine):")
    for c in result["commands"]:
        print("  " + c)
    print("\n" + LIMITS)


if __name__ == "__main__":
    main()
