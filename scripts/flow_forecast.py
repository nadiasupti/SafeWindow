"""Today's river-flow forecast (1, 3 and 7 days) from the Random Forest that won the benchmark, using the free Open-Meteo APIs.

    python scripts/flow_forecast.py                       # every river with a model, as of today
    python scripts/flow_forecast.py --site sunamganj_bd --as-of 2024-06-17      # a past day (hindcast, archive data)

Prints discharge in m3/s (modelled by GloFAS, not a gauge) and the level each forecast reaches against the river's own
historical quantiles. Only the 1- and 3-day values vote in the automated watch; the 7-day value is for information.
Sends nothing and needs no key. Models: data/forecast/flow/ (train again with scripts/train_flow_models.py).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import flowforecast as ff  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", help="one of: " + ", ".join(ff.SITE_POINTS))
    ap.add_argument("--as-of", help="YYYY-MM-DD (default today)")
    args = ap.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    for site in ([args.site] if args.site else list(ff.SITE_POINTS)):
        r = ff.forecast_site(site, as_of=as_of)
        if not r["ok"]:
            print(f"{site}: {r['why']}")
            continue
        p, lv, th = r["predicted_m3s"], r["levels"], r["thresholds_m3s"]
        print(f"{site}  as of {r['origin']}: today {r['today_m3s']:.0f} m3/s | +1 day {p['1']:.0f} ({lv['1']}) | +3 days {p['3']:.0f} ({lv['3']}) | "
              f"+7 days {p['7']:.0f} ({lv['7']}, no vote) | watch level {th['watch']:.0f} | vote: {r['vote']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
