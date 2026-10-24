"""Hand-check the shelter candidates, then use only the confirmed ones.

    python scripts/shelter_checklist.py make     # writes <data>/shelter_checklist.csv
    python scripts/shelter_checklist.py apply    # writes <data>/processed/shelters_verified.csv

1. `make` lists the OSM shelter candidates the pipeline uses (pharmacies left
   out), each with a map link, and blank columns to fill in. It never
   overwrites a checklist that already exists.
2. For each row, find out (local contacts, upazila office, school or clinic
   staff, a site visit) and fill in:
     exists       yes / no   the building is really there
     flood_safe   yes / no   people can shelter there in a flood
     source       who or what confirmed it (name, phone call, document)
     checked_by   your name
     date_checked YYYY-MM-DD
3. `apply` copies rows with exists=yes and flood_safe=yes into
   processed/shelters_verified.csv with verified=yes. From then on the pipeline
   uses only those shelters. Rerun steps 06, 07 and 08 to update the results.

Before `apply`, the pipeline already leaves out any candidate answered "no"
(safewindow.places.drop_rejected) and keeps the unchecked ones.
"""
from __future__ import annotations

import argparse

import pandas as pd

from safewindow import config
from safewindow.places import SHELTER_COLS, clean_candidates, shelters_from_csv

CHECK_COLS = ["exists", "flood_safe", "source", "checked_by", "date_checked", "notes"]
YES = {"yes", "y", "true", "1"}


def make(paths) -> None:
    out = paths.shelter_checklist
    if out.exists():
        raise SystemExit(f"{out} already exists - not overwriting your answers.")
    s = clean_candidates(shelters_from_csv(paths.shelter_candidates))
    df = pd.DataFrame({
        "shelter_id": s["shelter_id"], "name": s["name"], "type": s["type"],
        "lat": s["lat"], "lon": s["lon"],
        "map_link": [f"https://www.openstreetmap.org/?mlat={la}&mlon={lo}#map=18/{la}/{lo}"
                     for la, lo in zip(s["lat"], s["lon"])],
        **{c: "" for c in CHECK_COLS},
    })
    df.to_csv(out, index=False, encoding="utf-8-sig")   # BOM so Excel shows Bengali names
    print(f"wrote {len(df)} shelters to {out}")


def confirmed(checklist: pd.DataFrame) -> pd.DataFrame:
    """Rows where both exists and flood_safe are answered yes."""
    yes = lambda c: checklist[c].fillna("").astype(str).str.strip().str.lower().isin(YES)   # noqa: E731
    return checklist[yes("exists") & yes("flood_safe")]


def apply(paths) -> None:
    src = paths.shelter_checklist
    if not src.exists():
        raise SystemExit(f"{src} not found - run `make` first.")
    checklist = pd.read_csv(src, dtype=str, encoding="utf-8-sig")
    ok = confirmed(checklist)
    if ok.empty:
        raise SystemExit("No shelters confirmed yet (exists=yes and flood_safe=yes). Nothing written.")
    out = pd.DataFrame({
        "shelter_id": ok["shelter_id"], "name": ok["name"], "type": ok["type"],
        "lat": ok["lat"], "lon": ok["lon"],
        "source": ok["source"].fillna("") + " (checked by " + ok["checked_by"].fillna("?") + ", "
                  + ok["date_checked"].fillna("?") + ")",
        "verified": "yes", "notes": ok["notes"].fillna(""),
    })[SHELTER_COLS]
    out.to_csv(paths.shelters_verified, index=False, encoding="utf-8")
    print(f"{len(out)} of {len(checklist)} shelters confirmed -> {paths.shelters_verified}")
    print("Now rerun: python pipeline/06_isolation.py, python pipeline/07_timeline.py, "
          "python scripts/road_reports_check.py, python pipeline/08_build_app_data.py")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["make", "apply"])
    args = ap.parse_args()
    config.utf8_console()
    paths = config.get_paths()
    make(paths) if args.action == "make" else apply(paths)


if __name__ == "__main__":
    main()
