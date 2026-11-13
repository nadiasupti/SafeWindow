import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import admin_app  # noqa: E402

DOL = {"id": "osm6123937356", "isolated_from_earliest": "2022-05-17"}
DATES = ["2022-05-16", "2022-05-18", "2022-05-23", "2022-05-25"]


def test_demo_suggests_only_what_the_radar_showed_that_day():
    codes = "cuii"
    assert admin_app.suggestion(codes, DATES, 0, DOL) is None            # connected: no claim
    assert admin_app.suggestion(codes, DATES, 1, DOL) is None            # uncertain: no claim, even before isolation
    # Dholkotob: supplies may run out on 24 May (17 May + 7 days), so on 23 May one day is left -> Critical
    assert admin_app.suggestion(codes, DATES, 2, DOL) == ("critical", "isolated")
    assert admin_app.suggestion(codes, DATES, 3, DOL) == ("critical", "isolated")


def test_demo_warning_first_then_critical_as_supplies_run_low():
    later = {"isolated_from_earliest": "2022-05-22"}                    # supplies may run out on 29 May
    dates = ["2022-05-16", "2022-05-23", "2022-05-28"]
    assert admin_app.suggestion("cii", dates, 1, later) == ("warning", "isolated")
    assert admin_app.suggestion("cii", dates, 2, later) == ("critical", "isolated")
    assert admin_app.suggestion("cii", dates, 2, later, supply_days=14) == ("warning", "isolated")


def test_bangla_and_english_have_the_same_texts():
    import re

    import admin_text
    bn, en = admin_text.TEXT["bn"], admin_text.TEXT["en"]
    assert set(bn) == set(en)
    for key in bn:
        assert set(re.findall(r"\{(\w+)\}", bn[key])) == set(re.findall(r"\{(\w+)\}", en[key])), key
    assert admin_text.text("en", "tab_approve", n=2) == "✅ Approval (2)"
    assert admin_text.text("xx", "tab_log") == "📜 Log"                       # unknown language: Bangla
    for code in "ciub":                                                       # every status code has a label
        assert bn[f"code_{code}"] and en[f"code_{code}"]
    for word in ("safe route", "road cut", "relief deadline"):
        assert all(word not in v.lower() for v in en.values()), word


def test_panel_refuses_to_open_from_another_address():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "admin_app.py"), default_timeout=30).run()
    assert at.error and "only on the admin's own computer" in at.error[0].value
    assert not at.tabs                                                   # nothing else is shown


def test_panel_needs_the_admin_key(monkeypatch):
    monkeypatch.setattr(admin_app.st, "context", type("C", (), {"headers": {"Host": "localhost:8502"}})())
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    stopped = []
    monkeypatch.setattr(admin_app.st, "error", lambda msg: stopped.append(msg))
    monkeypatch.setattr(admin_app.st, "stop", lambda: (_ for _ in ()).throw(SystemExit))
    with pytest.raises(SystemExit):
        admin_app.guard()
    assert "Admin key" in stopped[0]
