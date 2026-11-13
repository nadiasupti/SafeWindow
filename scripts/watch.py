"""Run the automated flood watch: satellite water maps + free river/rain APIs (+ an optional AI image reader).

    python scripts/watch.py --flood sunamganj_2024                       # measure and print, save the report
    python scripts/watch.py --flood sunamganj_2024 --as-of 2024-06-17    # replay a past day (hindcast)
    python scripts/watch.py --flood sunamganj_2024 --drafts --by "Name"  # also put draft alerts in front of the admin
    python scripts/watch.py --flood sunamganj_2024 --every-hours 6       # keep watching
    python scripts/watch.py --flood sunamganj_2024 --data-url https://safewindow-3b759.web.app/data --drafts --by "Name"
                                                    # read the flood maps from the published app (GitHub Actions does this)

    python scripts/watch.py --check-ai                                   # only test the AI key and model
The AI reader is optional and uses a free API. Set the key in your own environment, never in a file:
    $env:GEMINI_API_KEY="..."              (Google Gemini, free tier; optional GEMINI_MODEL)
    $env:AI_API_KEY="..."; $env:AI_BASE_URL="https://openrouter.ai/api/v1"; $env:AI_MODEL="..."   (any OpenAI-compatible API)

Nothing is sent to phones from here. --drafts saves PENDING alerts (needs GOOGLE_APPLICATION_CREDENTIALS, the Firebase
Admin key); the admin approves them in the admin panel, and only then is that village notified. They are SIMULATION
(test phones only) unless the two live switches described in README.md ("Automated watch and river forecasts") are set.

When new alerts wait for approval, the admins' phones get a notification (no village does). Register a phone once with
    python scripts/send_alert.py --add-admin-device <id>     # the id shown in the app: Settings > test number
--no-notify skips that.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
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


def make_drafts(report: dict, by: str, data_dir: Path = alerts.APP_DATA, notify: bool = True) -> list[dict]:
    """Save pending alerts for the flagged villages that do not have one yet, then tell the admins' phones."""
    db = alerts.firestore_client()
    fresh = watch.villages_to_draft(report, alerts.load_alerts(db))
    drafts = watch.draft_alerts(report, by, villages=fresh, data_dir=data_dir)
    for rec in drafts:
        alerts.save(db, alerts.submit(rec, by))
    if drafts and notify:
        admin_ids = alerts.load_admin_ids(db)
        if not admin_ids:
            print("No admin phone is registered, so nobody was told. Add one: python scripts/send_alert.py --add-admin-device <id>")
        else:
            sent, failed = alerts.notify_admins(drafts, alerts.load_subscriptions(db), admin_ids, alerts.fcm_sender(db))
            print(f"admin phones told: {sent} sent, {failed} failed"
                  + ("" if sent + failed else " (switch alerts on in the app on the admin phone first)"))
    return drafts


def summary(report: dict, drafts: list[dict] | None) -> None:
    """A short table on the GitHub Actions run page (only when running there)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [f"### {report.get('name', report.get('flood'))}", ""]
    if not report.get("ok"):
        lines.append(f"Could not run: {report.get('why')}")
    else:
        ai = report["ai"].get("provider") if report["ai"].get("ok") else report["ai"].get("why")
        lines += [f"Satellite date {report['issue_date']} ({report['mode']}). AI: {ai}", ""]
        flagged = [r for r in report["villages"] if r["level"] != "none"]
        if flagged:
            lines += ["| Village | Level | Votes |", "|---|---|---|"]
            lines += [f"| {r['name_en']} | {r['level']} | {r['votes']} |" for r in sorted(flagged, key=lambda r: -watch.LEVEL_NUM[r['level']])]
        else:
            lines.append("No village flagged.")
        if drafts is not None:
            lines += ["", f"**{len(drafts)} new alert(s) wait for the admin's approval.** Nothing was sent to any village."]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")


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
    ap.add_argument("--flood", help="flood id from pwa/public/data/index.json (several: comma-separated)")
    ap.add_argument("--check-ai", action="store_true", help="only check the AI key and model with one tiny request")
    ap.add_argument("--as-of", help="replay a past day (YYYY-MM-DD): satellite passes up to it, river/rain from the archive")
    ap.add_argument("--no-ai", action="store_true", help="do not use the AI reader")
    ap.add_argument("--min-signals", type=int, default=watch.MIN_SIGNALS, help="signals that must agree (default 2)")
    ap.add_argument("--drafts", action="store_true", help="save pending alerts for the admin to approve")
    ap.add_argument("--by", help="your name (required with --drafts; it is logged)")
    ap.add_argument("--every-hours", type=float, help="repeat forever with this pause")
    ap.add_argument("--data-url", help="read the app data from the published app at this address instead of pwa/public/data")
    ap.add_argument("--no-notify", action="store_true", help="do not tell the admins' phones about new pending alerts")
    args = ap.parse_args()
    if args.check_ai:
        return check_ai()
    if not args.flood:
        ap.error("--flood is required (or use --check-ai)")
    if args.drafts and not (args.by or "").strip():
        ap.error("--drafts needs --by NAME: every action is logged")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    floods = [f.strip() for f in args.flood.split(",") if f.strip()]
    while True:
        data_dir = alerts.APP_DATA
        if args.data_url:
            data_dir = watch.mirror_app_data(args.data_url, floods, Path(tempfile.mkdtemp(prefix="safewindow-data-")))
        for flood in floods:
            report = watch.run(flood, as_of=date.fromisoformat(args.as_of) if args.as_of else None,
                               use_ai=not args.no_ai, min_signals=args.min_signals, data_dir=data_dir)
            if report.get("ok"):
                print("report saved:", watch.save_report(report))
            show(report)
            drafts = None
            if args.drafts and report.get("ok"):
                drafts = make_drafts(report, args.by, data_dir, notify=not args.no_notify)
                print(f"{len(drafts)} new pending alert(s) are waiting for the admin's approval. Nothing was sent to any village.")
            summary(report, drafts)
        if not args.every_hours:
            return 0
        time.sleep(args.every_hours * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
