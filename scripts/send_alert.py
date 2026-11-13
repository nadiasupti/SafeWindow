"""Send a SIMULATION village alert from the command line, and manage the test phones.

The usual way is the local admin panel (python -m streamlit run app/admin_app.py). This script does the same steps
in one go (draft, approval, publish) and logs them in Firestore like the panel does. Real alerts are only possible
from the admin panel.

    $env:GOOGLE_APPLICATION_CREDENTIALS="E:\\keys\\safewindow-admin.json"   # Firebase Admin key, never in the repo

    python scripts/send_alert.py --add-test-device <id>      # the id shown in the app: Settings > test number
    python scripts/send_alert.py --list-test-devices
    python scripts/send_alert.py --remove-test-device <id>

    python scripts/send_alert.py --simulation --flood sunamganj_2022 --village osm6123937356 \\
        --level warning --reason roads --radar-date 2022-05-23 --by "Nadia"
    python scripts/send_alert.py ... --dry-run               # show the message and the recipients, send nothing

Reasons: roads / isolated (need --radar-date), rain (needs --rain-date), official (needs --text-bn and --text-en).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import alerts  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add-test-device")
    ap.add_argument("--remove-test-device")
    ap.add_argument("--list-test-devices", action="store_true")
    ap.add_argument("--simulation", action="store_true", help="a test alert, to registered test phones only")
    ap.add_argument("--flood")
    ap.add_argument("--village")
    ap.add_argument("--level", choices=alerts.LEVELS)
    ap.add_argument("--reason", choices=alerts.REASONS)
    ap.add_argument("--radar-date", help="YYYY-MM-DD, for roads and isolated")
    ap.add_argument("--rain-date", help="YYYY-MM-DD, for rain")
    ap.add_argument("--text-bn")
    ap.add_argument("--text-en")
    ap.add_argument("--hours", type=int, default=24, help="how long the alert stays valid")
    ap.add_argument("--by", default="command line", help="your name, for the log")
    ap.add_argument("--dry-run", action="store_true", help="print the message and the recipients, send nothing")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if a.add_test_device or a.remove_test_device or a.list_test_devices:
        db = alerts.firestore_client().collection("test_devices")
        if a.add_test_device:
            db.document(a.add_test_device).set({"added": datetime.now(timezone.utc)})
            print(f"added test phone {a.add_test_device}")
        if a.remove_test_device:
            db.document(a.remove_test_device).delete()
            print(f"removed test phone {a.remove_test_device}")
        if a.list_test_devices:
            print("\n".join(d.id for d in db.stream()) or "(no test phones)")
        return

    if not a.simulation:
        raise SystemExit("Only --simulation alerts can be sent from here. Real alerts need the admin panel's approval step.")
    for need in ("flood", "village", "level", "reason"):
        if not getattr(a, need):
            raise SystemExit(f"--{need} is required")
    date = a.radar_date if a.reason in ("roads", "isolated") else a.rain_date if a.reason == "rain" else None
    texts = {"bn": a.text_bn or "", "en": a.text_en or ""} if a.reason == "official" else None
    try:
        rec = alerts.new_alert(a.flood, a.village, a.level, a.reason, a.by, date=date, texts=texts, hours=a.hours)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise SystemExit(str(exc))
    for lang in ("bn", "en"):
        print(f"[{lang}] {rec['preview'][lang]['title']}\n     {rec['preview'][lang]['body']}")

    db = alerts.firestore_client()
    subs, test_ids = alerts.load_subscriptions(db), alerts.load_test_ids(db)
    chosen = alerts.recipients(subs, a.flood, a.village, test_ids)
    print(f"{len(chosen)} test phone(s) subscribed to this village ({len(test_ids)} test phones registered)")
    if a.dry_run:
        print("nothing sent (dry run)")
        return
    alerts.submit(rec, a.by)
    alerts.publish(rec, a.by, subs, test_ids, alerts.fcm_sender(db), verified=True)
    alerts.save(db, rec)
    print(f"sent {rec['sent']}, failed {rec['failed']} (logged as alert {rec['id']})")


if __name__ == "__main__":
    main()
