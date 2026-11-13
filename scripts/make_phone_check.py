"""Write phone_check.html: a page to open on a REAL phone to test GPS, SMS, taps, fonts, saving and offline use.

    python scripts/make_phone_check.py [--out phone_check.html]

Get it onto the phone (email it, copy it by USB, or put it in a shared drive) and open it from the phone's files:
a saved file works offline, and GPS needs either a saved file or https. A page served over plain http on your
Wi-Fi (http://192.168.x.x) is NOT a secure context, so the browser will block GPS there: the check page says so.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import phone_check  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("phone_check.html"))
    a = ap.parse_args()
    a.out.write_text(phone_check.build(), encoding="utf-8", newline="\n")
    print(f"Wrote {a.out}. Open it on a real phone, tap through the 7 checks, and send back the summary at the bottom.")


if __name__ == "__main__":
    main()
