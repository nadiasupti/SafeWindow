"""The early-warning demo: synthetic data -> model -> draft alerts -> admin approval -> that village's phones."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from safewindow import alerts, forecast  # noqa: E402

FLOOD = "sunamganj_2022"


@pytest.fixture(scope="module")
def trained():
    return forecast.train()


def test_synthetic_data_is_reproducible_and_labelled_by_the_invented_rule():
    a, b = forecast.synthetic_data(500, seed=1), forecast.synthetic_data(500, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert set(a["flood_next_3d"]) == {0, 1}
    assert (a[forecast.RAIN_COLS] >= 0).all().all()
    assert 0.05 < a["flood_next_3d"].mean() < 0.40


def test_the_model_learns_the_synthetic_rule_on_a_separate_sample(trained):
    model, metrics = trained
    assert metrics["auc"] > 0.75
    assert metrics["brier"] < 0.15
    assert not model.validated
    assert "synthetic" in model.meta["trained_on"]
    assert model.meta["validated_on_real_data"] is False


def test_more_rain_upstream_never_lowers_the_chance(trained):
    model, _ = trained
    base = dict(rain_1d=5.0, rain_3d=15.0, rain_7d=30.0, upstream_3d=0.0, upstream_7d=0.0, susceptibility=0.5)
    probs = []
    for up in (0, 20, 60, 120, 250):
        row = pd.DataFrame([{**base, "upstream_3d": up, "upstream_7d": up * 1.6}])
        probs.append(float(model.predict_proba(row)[0]))
    assert probs == sorted(probs) and probs[-1] > probs[0] + 0.2


def test_a_village_cut_off_before_is_more_at_risk(trained):
    model, _ = trained
    vs = alerts.villages(FLOOD)
    iso = next(v for v in vs if v["outcome"] == "isolated")
    safe = next(v for v in vs if v["outcome"] != "isolated" and forecast.susceptibility(v) < forecast.susceptibility(iso))
    table = forecast.forecast_villages(model, [iso, safe], forecast.SCENARIOS["rising"]).set_index("village")
    assert table.loc[iso["id"], "probability"] > table.loc[safe["id"], "probability"]


def test_scenarios_calm_gives_no_alert_and_heavy_rain_gives_alerts(trained):
    model, _ = trained
    vs = alerts.villages(FLOOD)
    calm = forecast.forecast_villages(model, vs, forecast.SCENARIOS["calm"])
    heavy = forecast.forecast_villages(model, vs, forecast.SCENARIOS["heavy_upstream"])
    assert (calm["level"] == "none").all()
    assert (heavy["level"] != "none").any()
    assert heavy["probability"].is_monotonic_decreasing                 # most likely first


def test_levels_follow_the_cuts():
    assert forecast.level_for(0.1) is None
    assert forecast.level_for(0.30) == "watch"
    assert forecast.level_for(0.55) == "warning"
    assert forecast.level_for(0.9) == "critical"


def test_the_daily_checks_rain_numbers_become_model_inputs_and_missing_numbers_do_not():
    rec = json.loads((ROOT / "data" / "monitor" / "sunamganj_2026.json").read_text(encoding="utf-8"))
    rain = forecast.rain_from_monitor(rec)
    assert set(rain) == set(forecast.RAIN_COLS)
    broken = {"rain": {"sunamganj": {"1d_mm": None, "3d_mm": 1, "7d_mm": 1}, "meghalaya_upstream": {"3d_mm": 1, "7d_mm": 1}}}
    assert forecast.rain_from_monitor(broken) is None
    assert forecast.rain_from_monitor({"rain": {}}) is None


def test_model_round_trips_through_json(trained):
    model, _ = trained
    again = forecast.Model.from_json(model.to_json())
    df = forecast.synthetic_data(50, seed=3)
    np.testing.assert_allclose(model.predict_proba(df), again.predict_proba(df))


# --- the alert path ----------------------------------------------------------------------------------------

def fake_sender(log):
    def send(chosen, data_by_lang, ttl):
        log.append(([s["uid"] for s in chosen], data_by_lang))
        return len(chosen), 0
    return send


@pytest.fixture()
def drafts(trained):
    model, _ = trained
    vs = alerts.villages(FLOOD)
    rain = forecast.SCENARIOS["heavy_upstream"]
    table = forecast.forecast_villages(model, vs, rain)
    return model, table, rain, forecast.draft_alerts(model, table, FLOOD, rain, "demo scenario: heavy_upstream", "Tester",
                                                     issue_date="2026-11-13")


def test_drafts_exist_only_for_villages_that_reach_a_level_and_nothing_is_sent(drafts):
    model, table, rain, recs = drafts
    assert len(recs) == int((table["level"] != "none").sum()) > 0
    for r in recs:
        assert r["status"] == "draft" and r["reason"] == "forecast" and r["simulation"] is True
        assert r["forecast"]["validated_on_real_data"] is False
        assert "published_at" not in r


def test_the_message_says_it_is_a_model_estimate_in_both_languages_and_makes_no_promise(drafts):
    rec = drafts[3][0]
    en, bn = rec["preview"]["en"]["body"], rec["preview"]["bn"]["body"]
    assert "Model estimate" in en and "synthetic" in en and "not validated" in en and "may become possible" in en
    assert "মডেলের অনুমান" in bn and "কৃত্রিম" in bn
    assert "will flood" not in en.lower() and "safe" not in en.lower()
    assert "Follow official alerts" in en


def test_a_forecast_alert_needs_its_forecast_date():
    with pytest.raises(ValueError, match="date"):
        alerts.new_alert(FLOOD, alerts.villages(FLOOD)[0]["id"], "watch", "forecast", "Tester")


def test_only_after_approval_the_villages_subscribers_are_notified(drafts, monkeypatch):
    monkeypatch.delenv("SAFEWINDOW_ALLOW_LIVE", raising=False)
    rec = drafts[3][0]
    village = rec["village"]
    subs = [{"uid": "test1", "flood": FLOOD, "village": village}, {"uid": "real1", "flood": FLOOD, "village": village},
            {"uid": "other", "flood": FLOOD, "village": "some-other-village"}]
    sent = []
    with pytest.raises(ValueError, match="waiting for approval"):                     # a draft cannot be sent
        alerts.publish(rec, "Admin", subs, {"test1"}, fake_sender(sent), verified=True)
    alerts.submit(rec, "Tester")
    with pytest.raises(ValueError, match="source and the date"):                      # approval needs the checkbox
        alerts.publish(rec, "Admin", subs, {"test1"}, fake_sender(sent), verified=False)
    assert sent == []
    alerts.publish(rec, "Admin", subs, {"test1"}, fake_sender(sent), verified=True)
    assert sent[0][0] == ["test1"]                                                      # simulation: test phones only
    assert sent[0][1]["en"]["village"] == village
    assert rec["status"] == "published" and rec["approved_by"] == "Admin"


def test_a_model_trained_on_synthetic_data_cannot_reach_real_phones(trained, monkeypatch):
    model, _ = trained
    vs = alerts.villages(FLOOD)
    for env in ({}, {"SAFEWINDOW_ALLOW_LIVE": "1"}):
        monkeypatch.delenv("SAFEWINDOW_ALLOW_LIVE", raising=False)
        monkeypatch.delenv("SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST", raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        with pytest.raises(ValueError, match="synthetic data"):
            alerts.new_alert(FLOOD, vs[0]["id"], "warning", "forecast", "Tester", date="2026-11-13", simulation=False)
    # a built draft cannot be turned real afterwards either
    rec = alerts.new_alert(FLOOD, vs[0]["id"], "warning", "forecast", "Tester", date="2026-11-13")
    rec["simulation"] = False
    alerts.submit(rec, "Tester")
    monkeypatch.setenv("SAFEWINDOW_ALLOW_LIVE", "1")
    with pytest.raises(ValueError, match="synthetic data"):
        alerts.publish(rec, "Admin", [], set(), fake_sender([]), verified=True)


def test_both_switches_together_are_the_only_way_to_send_an_unvalidated_forecast_live(monkeypatch):
    monkeypatch.setenv("SAFEWINDOW_ALLOW_LIVE", "1")
    monkeypatch.delenv("SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST", raising=False)
    assert not alerts.forecast_live_allowed()
    monkeypatch.setenv("SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST", "1")
    assert alerts.forecast_live_allowed()
    monkeypatch.delenv("SAFEWINDOW_ALLOW_LIVE")
    assert not alerts.forecast_live_allowed()


def test_the_admin_tab_creates_pending_alerts_and_sends_nothing(monkeypatch):
    from streamlit.testing.v1 import AppTest

    script = f'''
import sys
from pathlib import Path
root = Path(r"{ROOT}")
sys.path.insert(0, str(root / "app"))
sys.path.insert(0, str(root))
import streamlit as st
import admin_app

class Doc:
    def __init__(self, store):
        self.store = store
    def set(self, rec):
        self.store.append(rec)

class Coll:
    def __init__(self, store):
        self.store = store
    def document(self, key):
        return Doc(self.store)

class Db:
    def __init__(self, store):
        self.store = store
    def collection(self, name):
        return Coll(self.store)

store = st.session_state.setdefault("saved", [])
admin_app.db = lambda: Db(store)
admin_app.tab_forecast("Tester", [])
'''
    at = AppTest.from_string(script, default_timeout=60).run()
    assert not at.exception
    at.selectbox(key="fc_scenario").select("heavy_upstream").run()
    assert not at.exception
    at.button(key="fc_make").click().run()
    assert not at.exception
    saved = at.session_state["saved"]
    assert saved and all(r["status"] == "pending" and r["reason"] == "forecast" and r["simulation"] for r in saved)
    assert not any("published_at" in r for r in saved)
