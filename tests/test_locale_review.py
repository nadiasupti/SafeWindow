import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from safewindow import locale_tools as lt

ROOT = Path(__file__).resolve().parent.parent
EN = {"title": "SafeWindow", "found": "Nearest village: {name} ({km} km away).", "bag_items": ["Water", "Food for {n} days"],
      "sms_template": "Alert {name} {when} {route}", "digits": None, "draft": False, "dir": "ltr"}
LOC = {"title": "X", "found": "Y {name} {km}", "bag_items": ["W", "F {n}"], "sms_template": "A {name} {when} {route} {shelter}",
       "digits": "0123456789", "draft": True, "dir": "rtl"}


def test_export_flattens_lists_and_skips_settings():
    rows = lt.export_rows(EN, LOC)
    assert [r["key"] for r in rows] == ["title", "found", "bag_items[0]", "bag_items[1]", "sms_template"]
    assert rows[3]["english"] == "Food for {n} days" and rows[3]["current"] == "F {n}" and rows[3]["corrected"] == ""


def test_a_correction_is_applied_and_the_reviewer_recorded_but_the_draft_stays():
    rows = lt.export_rows(EN, LOC)
    rows[1]["corrected"] = "Qareeb: {name} ({km})"
    rows[3]["corrected"] = "Khana {n} din"
    new, problems, n = lt.apply_corrections(LOC, EN, rows, "ur", "A. Reviewer", "Disaster Office", today="2026-11-01")
    assert problems == [] and n == 2
    assert new["found"] == "Qareeb: {name} ({km})" and new["bag_items"] == ["W", "Khana {n} din"]
    assert new["review"] == {"reviewer": "A. Reviewer", "affiliation": "Disaster Office", "date": "2026-11-01",
                             "corrections": 2, "approved": False}
    assert new["draft"] is True and LOC["bag_items"][1] == "F {n}"                       # the original is untouched


def test_approval_removes_the_draft_label_only_with_a_named_reviewer():
    new, problems, _ = lt.apply_corrections(LOC, EN, [], "ur", "A. Reviewer", "Disaster Office", approve=True)
    assert problems == [] and new["draft"] is False and new["review"]["approved"] is True
    _, problems, _ = lt.apply_corrections(LOC, EN, [], "ur", "", "", approve=True)
    assert problems and "reviewer" in problems[0]


def test_a_correction_that_changes_placeholders_is_refused_and_nothing_is_applied():
    rows = lt.export_rows(EN, LOC)
    rows[0]["corrected"] = "Fine title"
    rows[1]["corrected"] = "Missing the distance: {name}"
    rows[3]["corrected"] = "Extra {n} {oops}"
    new, problems, n = lt.apply_corrections(LOC, EN, rows, "ur", "A", "B")
    assert n == 0 and new == LOC and len(problems) == 2
    assert any("found" in p for p in problems) and any("bag_items[1]" in p for p in problems)


def test_sms_text_may_name_the_shelter_in_other_languages_but_not_in_english():
    assert lt.check("sms_template", "A {name} {when} {route} {shelter}", EN, "ur") is None
    assert lt.check("sms_template", "A {name} {when} {route} {shelter}", EN, "en") is not None
    assert lt.check("nope", "x", EN, "ur") == "nope: not a reviewable key"


def test_the_command_line_round_trip_with_real_urdu(tmp_path):
    sheet = tmp_path / "ur.csv"
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "scripts" / "locale_review.py"), *a], capture_output=True,
                                    text=True, encoding="utf-8", cwd=tmp_path)
    r = run("export", "ur", "--out", str(sheet))
    assert r.returncode == 0 and "texts to review" in r.stdout
    rows = list(csv.DictReader(sheet.open(encoding="utf-8-sig")))
    title = next(r_ for r_ in rows if r_["key"] == "title")
    assert title["english"] == "SafeWindow" and title["current"] == "سیف ونڈو"
    # a broken correction is refused, and the real locale file is not touched
    before = (ROOT / "locales" / "ur.json").read_text(encoding="utf-8")
    bad = next(i for i, r_ in enumerate(rows) if r_["key"] == "found")
    rows[bad]["corrected"] = "بغیر نام"
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    r = run("apply", "ur", str(sheet), "--reviewer", "T", "--affiliation", "T")
    assert r.returncode == 1 and "Nothing was changed" in r.stdout
    assert (ROOT / "locales" / "ur.json").read_text(encoding="utf-8") == before


def test_every_unreviewed_locale_is_a_draft_and_reviewed_ones_say_who_reviewed_them():
    for path in sorted((ROOT / "locales").glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        if path.stem in ("en", "bn"):                          # the project's own two languages
            continue
        if d.get("draft") is False:
            review = d.get("review") or {}
            assert review.get("reviewer") and review.get("affiliation") and review.get("date"), f"{path.name} has no reviewer"
        else:
            assert d.get("draft") is True and d.get("draft_notice")


def test_the_phone_check_page_covers_every_real_device_risk_and_needs_no_network():
    import re
    from safewindow import phone_check
    page = phone_check.build()
    for hook in ("navigator.geolocation", "href='sms:?&body=", "maxTouchPoints", "isSecureContext", "download=", "prefers-color-scheme",
                 "سیف ونڈو", "সেফউইন্ডো", "सेफविन्डो", "dir=\"rtl\""):
        assert hook in page, hook
    assert re.findall(r"(?:src|href)=['\"]https?://|url\(|@import|<link", page) == []        # works from a saved file, offline
    assert len(re.findall(r"<h2>\d\.", page)) == 7
