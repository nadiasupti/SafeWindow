"""Daily check: new Sentinel-1 images and recent NASA GPM rain over the monitored regions (app plan, step 4).

    $env:EE_SERVICE_ACCOUNT_KEY="E:\\keys\\safewindow-ee.json"     # the automation account; or your own login
    $env:EE_PROJECT="safewindow-2026"
    python scripts/daily_check.py                       # every monitored region (safewindow/monitor.py)
    python scripts/daily_check.py --regions sunamganj_2026

Writes data/monitor/<region>.json and appends to data/monitor/checks.csv. It only records: it does not run the
flood pipeline and never sends an alert. The admin panel's monitoring tab shows the result.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import gee, monitor  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", nargs="+", default=list(monitor.MONITORED))
    ap.add_argument("--days", type=int, default=30, help="look back this many days for radar images")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ee = gee.init()
    failed = 0
    for rid in a.regions:
        try:
            r = monitor.check_region(rid, days=a.days, ee=ee)
        except Exception as exc:  # noqa: BLE001 - one region's failure must not stop the others
            print(f"{rid}: FAILED {exc}")
            failed += 1
            continue
        rain = ", ".join(f"{box} 3 days {v['3d_mm'] if v['3d_mm'] is not None else 'n/a'} mm" for box, v in r["rain"].items())
        new = f", new: {' '.join(r['new_since_last_check'])}" if r["new_since_last_check"] else ""
        print(f"{rid}: newest radar {r['newest_radar'] or 'none'}{new}; {rain}")
    if failed:
        raise SystemExit(f"{failed} region(s) failed")


if __name__ == "__main__":
    main()
