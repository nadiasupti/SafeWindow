"""Run the automated flood watch: satellite water maps + free river/rain APIs (+ an optional AI image reader).

    python scripts/watch.py --flood sunamganj_2024                       # measure and print, save the report
    python scripts/watch.py --flood sunamganj_2024 --as-of 2024-06-17    # replay a past day (hindcast)
    python scripts/watch.py --flood sunamganj_2024 --drafts --by "Name"  # also put draft alerts in front of the admin
    python scripts/watch.py --flood sunamganj_2024 --every-hours 6       # keep watching

    python scripts/watch.py --check-ai                                   # only test the AI key and model
The AI reader is optional and uses a free API. Set the key in your own environment, never in a file:
    $env:GEMINI_API_KEY="..."              (Google Gemini, free tier; optional GEMINI_MODEL)
    $env:AI_API_KEY="..."; $env:AI_BASE_URL="https://openrouter.ai/api/v1"; $env:AI_MODEL="..."   (any OpenAI-compatible API)

Nothing is sent to phones from here. --drafts saves PENDING alerts (needs GOOGLE_APPLICATION_CREDENTIALS, the Firebase
Admin key); the admin approves them in the admin panel, and only then is that village notified. They are SIMULATION
(test phones only) unless the two live switches described in README.md ("Automated watch and river forecasts") are set.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import alerts, watch  # noqa: E402


def show(report: dict) -> None:
    if not report.get("ok"):
        print("Could not run:", report.get("why"))
        return
    print(f"{report['name']} | {report['mode']} | satellite {report['satellite']['previous']} -> {report['satellite']['latest']}")
    print("river:", "ok" if report["river"].get("ok") else report["river"].get("why"),
          "| rain:", report["rain"].get("local_3d_mm"), "mm here,", report["rain"].get("upstream_3d_mm"), "mm upstream",
          "| AI:", report["ai"].get("provider") if report["ai"].get("ok") else report["ai"].get("why"))
    for r in sorted(report["villages"], key=lambda r: -watch.LEVEL_NUM[r["level"]]):
        print(f"  {r['level']:9} {r['name_en'][:28]:28} {r['votes']}")
    n = sum(r["level"] != "none" for r in report["villages"])
    print(f"{n} village(s) flagged" if n else "no village flagged")


def make_drafts(report: dict, by: str) -> int:
    db = alerts.firestore_client()
    existing = {(a["flood"], a["village"], a.get("date")) for a in alerts.load_alerts(db) if a["status"] in ("draft", "pending")}
    fresh = {r["village"] for r in report["villages"] if r["level"] != "none"
             and (report["flood"], r["village"], report["issue_date"]) not in existing}
    drafts = watch.draft_alerts(report, by, villages=fresh)
    for rec in drafts:
        alerts.save(db, alerts.submit(rec, by))
    return len(drafts)


def check_ai() -> int:
    """One tiny request with the configured AI key: says whether it works, and if not, why. Never prints the key."""
    provider = watch.ai_provider()
    if not provider:
        print("No AI key found in this terminal. Set GEMINI_API_KEY (or AI_API_KEY + AI_BASE_URL + AI_MODEL), "
              "then open a new terminal.")
        return 1
    print(f"Checking {provider['kind']}: {', '.join(provider.get('models') or [provider['model']])} (in this order) ...")
    try:
        answer = watch.ai_ping(provider)
        print(f"OK, {provider['model']} answered: {answer}")
        return 0
    except Exception as exc:  # noqa: BLE001 - the reason is the point
        print("Not working:", watch.ai_error_text(exc, provider))
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flood", help="flood id from pwa/public/data/index.json")
    ap.add_argument("--check-ai", action="store_true", help="only check the AI key and model with one tiny request")
    ap.add_argument("--as-of", help="replay a past day (YYYY-MM-DD): satellite passes up to it, river/rain from the archive")
    ap.add_argument("--no-ai", action="store_true", help="do not use the AI reader")
    ap.add_argument("--min-signals", type=int, default=watch.MIN_SIGNALS, help="signals that must agree (default 2)")
    ap.add_argument("--drafts", action="store_true", help="save pending alerts for the admin to approve")
    ap.add_argument("--by", help="your name (required with --drafts; it is logged)")
    ap.add_argument("--every-hours", type=float, help="repeat forever with this pause")
    args = ap.parse_args()
    if args.check_ai:
        return check_ai()
    if not args.flood:
        ap.error("--flood is required (or use --check-ai)")
    if args.drafts and not (args.by or "").strip():
        ap.error("--drafts needs --by NAME: every action is logged")
    while True:
        report = watch.run(args.flood, as_of=date.fromisoformat(args.as_of) if args.as_of else None,
                           use_ai=not args.no_ai, min_signals=args.min_signals)
        if report.get("ok"):
            print("report saved:", watch.save_report(report))
        show(report)
        if args.drafts and report.get("ok"):
            print(f"{make_drafts(report, args.by)} pending alert(s) are waiting for the admin's approval. Nothing was sent.")
        if not args.every_hours:
            return 0
        time.sleep(args.every_hours * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
