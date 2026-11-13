"""Write data/<region>/results/nisar/village_water.json: around each village, how much more water NISAR's L-band radar
sees than Sentinel-1's C-band ("hidden water", likely water under plants). Uses the files scripts/nisar_polarization.py
already made, so it needs no download and no login.

    python scripts/nisar_village_water.py            # every region that has NISAR results
    python scripts/nisar_village_water.py --region sunamganj_2026
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from safewindow import nisar_villages  # noqa: E402


def villages_of(region_dir: Path) -> list[dict]:
    """Village points from the package's villages.gpkg (the same file the NISAR page maps)."""
    import geopandas as gpd

    path = region_dir.parent.parent / "processed" / "villages.gpkg"
    if not path.exists():
        return []
    v = gpd.read_file(path).to_crs(4326)
    def text(value):                                  # a missing name is NaN in the table: never let that into the JSON
        return value if isinstance(value, str) and value.strip() else None

    return [{"village_id": r.village_id, "name": text(r.name) or str(r.village_id), "name_bn": text(getattr(r, "name_bn", None)),
             "lat": float(r.geometry.y), "lon": float(r.geometry.x)} for r in v.itertuples()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region")
    args = ap.parse_args()
    for nj in sorted((ROOT / "data").glob("*/results/nisar/nisar.json")):
        region_dir = nj.parent
        rid = region_dir.parent.parent.name
        if args.region and rid != args.region:
            continue
        villages = villages_of(region_dir)
        if not villages:
            print(f"{rid}: no villages.gpkg, skipped")
            continue
        summary = nisar_villages.region_summary(region_dir, villages)
        summary["series"] = nisar_villages.time_series(region_dir)
        (region_dir / "village_water.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")   # strict: browsers reject NaN
        for d in summary["dates"]:
            print(f"{rid} {d['date']} NISAR {d['polarization']} vs Sentinel-1: median hidden water {d['median_hidden']}, "
                  f"{d['villages_with_a_gap']} of {len(villages)} villages with a gap of 10 points or more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
