"""Hindcast a simple early-warning rule on a later flood, learning it from an earlier one.

    python scripts/early_warning_hindcast.py --train data/live data/live/processed/rainfall_daily.csv \
        --test data/sunamganj_2024 data/sunamganj_2024/processed/rainfall_daily.csv \
        --box meghalaya_upstream_mm --window 3 --lag 0

The rule, learned only from the training flood:
  - vulnerable villages: those isolated at least once in the training flood;
  - rain trigger R: the smallest rain total (over `window` days, ending `lag`
    days before the radar date) on the radar date just before a vulnerable
    village was first observed isolated. This is the rain a forecaster had
    when the warning was due, the same quantity the test uses. A village
    already isolated on the first radar date has no observed onset and does
    not set R.
On each radar date D of the test flood, a vulnerable village that is not
isolated on D gets a warning for the next radar date if the rain total up to
D reaches R. Only rain up to D is used. Warnings are scored against the
village status observed on the next radar date (20% threshold), and compared
with persistence ("the next date looks like today"), which never warns of a
new isolation.

Details are written to <test data dir>/results/early_warning_hindcast.csv,
or to --out. The script refuses to write into a folder that holds submission
evidence (data/live).

This is a hindcast on a handful of dates and villages: it shows whether the
idea works, not a validated warning system.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def statuses(data_dir: Path) -> pd.DataFrame:
    vs = pd.read_csv(data_dir / "results" / "village_status.csv", dtype={"village_id": str})
    if "threshold" in vs:
        vs = vs[vs["threshold"] == 0.2]
    vs["date"] = pd.to_datetime(vs["date"])
    return vs.pivot_table(index="date", columns="village_id", values="status", aggfunc="first")


def rain_total(rain: pd.Series, day: pd.Timestamp, window: int, lag: int) -> float:
    end = day - pd.Timedelta(days=lag)
    part = rain[(rain.index > end - pd.Timedelta(days=window)) & (rain.index <= end)]
    return float(part.sum()) if len(part) == window else float("nan")


def learn(status: pd.DataFrame, rain: pd.Series, window: int, lag: int) -> tuple[list[str], float]:
    isolated = status.eq("isolated")
    vulnerable = [v for v in status.columns if isolated[v].any()]
    dates = list(status.index)
    triggers = []
    for v in vulnerable:
        i = dates.index(isolated[v].idxmax())                    # first date seen isolated
        if i == 0:
            continue                                             # isolated from the start: no observed onset
        r = rain_total(rain, dates[i - 1], window, lag)         # rain known on the radar date before
        if r == r:
            triggers.append(r)
        else:
            print(f"  {v}: no complete rain record before {dates[i - 1].date()}, onset not used")
    return vulnerable, (min(triggers) if triggers else float("nan"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", nargs=2, type=Path, required=True, metavar=("DATA_DIR", "RAIN_CSV"))
    ap.add_argument("--test", nargs=2, type=Path, required=True, metavar=("DATA_DIR", "RAIN_CSV"))
    ap.add_argument("--box", required=True, help="rainfall column, e.g. meghalaya_upstream_mm")
    ap.add_argument("--window", type=int, default=3)
    ap.add_argument("--lag", type=int, default=0)
    ap.add_argument("--vulnerable-only", action="store_true",
                    help="comparison rule: warn every vulnerable village on every date, ignoring rain")
    ap.add_argument("--out", type=Path, help="CSV for the details (default <test data dir>/results/)")
    args = ap.parse_args()

    out = args.out or args.test[0] / "results" / "early_warning_hindcast.csv"
    if (out.parent / "submission_evidence.json").exists() or (out.parent.parent / "submission_evidence.json").exists():
        raise SystemExit(f"{out.parent} holds submission evidence; pass --out to write the details elsewhere")

    train_rain = pd.read_csv(args.train[1], parse_dates=["date"]).set_index("date")[args.box]
    vulnerable, trigger = learn(statuses(args.train[0]), train_rain, args.window, args.lag)
    if args.vulnerable_only:
        print(f"learned from {args.train[0]}: {len(vulnerable)} vulnerable villages (rain ignored)")
    elif trigger != trigger:
        raise SystemExit("no onset with a complete rain record in the training flood: no trigger can be learned")
    else:
        print(f"learned from {args.train[0]}: {len(vulnerable)} vulnerable villages, "
              f"rain trigger {trigger:.0f} mm over {args.window} days (lag {args.lag})")

    test = statuses(args.test[0])
    rain = pd.read_csv(args.test[1], parse_dates=["date"]).set_index("date")[args.box]
    dates = list(test.index)
    rows = []
    for today, nxt in zip(dates[:-1], dates[1:]):
        r = rain_total(rain, today, args.window, args.lag)
        for v in test.columns:
            now, later = test.at[today, v], test.at[nxt, v]
            if now == "isolated" or later not in ("isolated", "connected"):
                continue                     # only villages not yet cut off, with a known outcome
            warned = v in vulnerable and (args.vulnerable_only or r >= trigger)
            rows.append({"date": today.date(), "next_date": nxt.date(), "lead_days": (nxt - today).days,
                         "village_id": v, "rain_mm": round(r, 1), "warned": warned,
                         "became_isolated": later == "isolated"})
    if not rows:
        raise SystemExit(f"{args.test[0]}: no village-date pair with a known next status to score")
    ev = pd.DataFrame(rows)
    hits = int((ev.warned & ev.became_isolated).sum())
    misses = int((~ev.warned & ev.became_isolated).sum())
    false_alarms = int((ev.warned & ~ev.became_isolated).sum())
    quiet = int((~ev.warned & ~ev.became_isolated).sum())
    print(f"tested on {args.test[0]}: {len(ev)} village-date pairs, {ev.became_isolated.sum()} new isolations")
    print(f"  rule:        hits {hits}, misses {misses}, false alarms {false_alarms}, correct quiet {quiet}")
    print(f"  persistence: hits 0, misses {hits + misses}, false alarms 0 (it never warns of a new isolation)")
    if hits + misses:
        print(f"  hit rate {hits / (hits + misses):.2f}; false-alarm ratio "
              f"{false_alarms / max(hits + false_alarms, 1):.2f}; lead time {ev[ev.warned & ev.became_isolated].lead_days.tolist()} days")
    out.parent.mkdir(parents=True, exist_ok=True)
    ev.to_csv(out, index=False)
    print(f"  details: {out}")


if __name__ == "__main__":
    main()
