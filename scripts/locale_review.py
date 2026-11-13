"""Review a draft translation with a native speaker.

    python scripts/locale_review.py export ur                 # writes ur_review.csv: English | current | corrected
    python scripts/locale_review.py apply ur ur_review.csv --reviewer "Name" --affiliation "Organisation"
    python scripts/locale_review.py apply ur ur_review.csv --reviewer "Name" --affiliation "Organisation" --approve

The reviewer fills the `corrected` column (leave it empty where the text is fine) and may add a `comment`.
`apply` refuses any correction whose {placeholders} differ from English, records who reviewed and when, and removes
the "draft" label only with --approve. Open the CSV in Excel or Google Sheets (UTF-8).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import locale_tools  # noqa: E402

LOCALES = Path(__file__).resolve().parent.parent / "locales"


def load(lang: str) -> dict:
    path = LOCALES / f"{lang}.json"
    if not path.exists():
        sys.exit(f"no locale file {path.name}; available: {sorted(p.stem for p in LOCALES.glob('*.json'))}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("lang")
    ex.add_argument("--out", type=Path)
    ap_ = sub.add_parser("apply")
    ap_.add_argument("lang")
    ap_.add_argument("sheet", type=Path)
    ap_.add_argument("--reviewer", default="")
    ap_.add_argument("--affiliation", default="")
    ap_.add_argument("--approve", action="store_true")
    a = ap.parse_args()
    english, current = load("en"), load(a.lang)
    if a.cmd == "export":
        rows = locale_tools.export_rows(english, current)
        out = a.out or Path(f"{a.lang}_review.csv")
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["key", "english", "current", "corrected", "comment"])
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {out}: {len(rows)} texts to review. Fill the 'corrected' column where a text is wrong.")
        return
    with a.sheet.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    new, problems, n = locale_tools.apply_corrections(current, english, rows, a.lang, a.reviewer, a.affiliation, a.approve)
    if problems:
        print("Nothing was changed. Fix these first:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    path = LOCALES / f"{a.lang}.json"
    raw = path.read_text(encoding="utf-8")
    path.write_text(json.dumps(new, indent=1, ensure_ascii=False) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8", newline="")
    print(f"Applied {n} corrections to {path.name}." + (" Draft label removed." if a.approve else " Still marked as a draft."))


if __name__ == "__main__":
    main()
