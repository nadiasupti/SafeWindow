"""The automated watch: our own satellite measurement, free river/rain APIs, an optional AI reader, a cautious decision,
and drafts only: nothing reaches a phone without the admin's approval."""
import json
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from safewindow import alerts, watch  # noqa: E402

FLOOD = "sunamganj_2024"
AS_OF = date(2024, 6, 17)
TODAY = date(2026, 11, 13)


def fake_get(river=(100.0, 250.0), rain_local=120.0, rain_up=0.0, fail=False):
    """Stands in for Open-Meteo: a river that goes from river[0] today to river[1] later, and 3 days of rain."""
    def get(url, timeout=30):
        if fail:
            raise OSError("offline")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        days = [(AS_OF + timedelta(days=k)).isoformat() for k in range(-3, 9)]
        if "flood-api" in url:
            n = len(q["latitude"][0].split(","))
            dis = [river[0]] * 4 + [river[1]] * 8
            payload = [{"daily": {"time": days, "river_discharge": dis}} for _ in range(n)]
            return payload if n > 1 else payload[0]
        lat = float(q["latitude"][0])
        total = rain_up if lat > 25.2 else rain_local            # the upstream point is at 25.27
        mm = [0.0] * 4 + [total / 3] * 8
        return {"daily": {"time": days, "precipitation_sum": mm}}
    return get


def fake_post(risk="critical", confidence=0.8, markers=16, record=None):
    def post(url, headers, body, timeout=90):
        if record is not None:
            record.append((url, headers, body))
        answer = {"overall_trend": "rising", "summary": "Water is spreading on the right-hand image.", "confidence": confidence,
                  "limits": "Cannot give a river height.",
                  "villages": [{"marker": i, "risk": risk, "reason": "more water nearby"} for i in range(1, markers + 1)]}
        if "generativelanguage" in url:
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}
        return {"choices": [{"message": {"content": json.dumps(answer)}}]}
    return post


GEMINI = {"kind": "gemini", "key": "test-key-123", "model": "gemini-test"}


# --- our own measurement -----------------------------------------------------------------------------------

def test_water_share_around_a_point_is_measured_from_the_mask():
    water = np.zeros((100, 100), bool)
    water[:, :50] = True                                            # the west half is water
    unknown = np.zeros_like(water)
    bounds = [[24.0, 91.0], [25.0, 92.0]]
    west, _ = watch.share_around(water, unknown, bounds, 24.5, 91.2, radius_km=5)
    east, _ = watch.share_around(water, unknown, bounds, 24.5, 91.8, radius_km=5)
    assert west == 1.0 and east == 0.0
    assert watch.share_around(water, unknown, bounds, 30.0, 91.5)[0] is None        # outside the map


def test_unknown_pixels_are_not_counted_as_dry():
    water = np.zeros((100, 100), bool)
    unknown = np.zeros_like(water)
    unknown[:, :] = True
    share, unk = watch.share_around(water, unknown, [[24.0, 91.0], [25.0, 92.0]], 24.5, 91.5, radius_km=5)
    assert share is None and unk == 1.0
    assert watch.vote_satellite(None, 0.1, 1.0) == "none"
    assert watch.vote_satellite(0.5, 0.1, 0.9) == "none"             # too much unknown: no vote


def test_satellite_vote_needs_both_a_high_share_and_a_rise():
    assert watch.vote_satellite(0.50, 0.30, 0.0) == "critical"
    assert watch.vote_satellite(0.30, 0.20, 0.0) == "warning"
    assert watch.vote_satellite(0.12, 0.05, 0.0) == "watch"
    assert watch.vote_satellite(0.60, 0.60, 0.0) == "none"           # lots of water but not rising
    assert watch.vote_satellite(0.02, 0.0, 0.0) == "none"


def test_the_real_flood_maps_give_a_measurement_for_every_village():
    vs = alerts.villages(FLOOD)
    sat = watch.satellite_signal(FLOOD, vs)
    assert sat["ok"] and set(sat["villages"]) == {v["id"] for v in vs}
    assert sat["previous"] < sat["latest"]
    png, markers = watch.render_image(FLOOD, vs)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(markers) == len(vs)


# --- the decision ------------------------------------------------------------------------------------------

def test_one_signal_never_raises_an_alert_and_two_agreeing_ones_give_the_cautious_level():
    assert watch.decide({"ai": "critical"}) == "none"
    assert watch.decide({"ai": "critical", "satellite": "none", "river": "none", "rain": "none"}) == "none"
    assert watch.decide({"river": "watch", "rain": "critical"}) == "watch"             # second-highest
    assert watch.decide({"river": "warning", "rain": "critical", "satellite": "watch"}) == "warning"
    assert watch.decide({"ai": "critical"}, min_signals=1) == "critical"


# --- free APIs ---------------------------------------------------------------------------------------------

def test_river_discharge_rise_becomes_a_vote_and_an_api_failure_does_not_stop_the_watch():
    vs = alerts.villages(FLOOD)
    r = watch.river_signal(vs, AS_OF, TODAY, fake_get(river=(100.0, 250.0)))
    assert r["ok"] and r["mode"] == "hindcast"
    assert {v["vote"] for v in r["villages"].values()} == {"critical"}                  # 2.5x
    calm = watch.river_signal(vs, AS_OF, TODAY, fake_get(river=(100.0, 105.0)))
    assert {v["vote"] for v in calm["villages"].values()} == {"none"}
    down = watch.river_signal(vs, AS_OF, TODAY, fake_get(fail=True))
    assert down["ok"] is False and "unavailable" in down["why"]


def test_rain_forecast_here_and_upstream():
    r = watch.rain_signal(FLOOD, (25.0, 91.5), AS_OF, TODAY, fake_get(rain_local=20.0, rain_up=210.0))
    assert r["ok"] and r["local_3d_mm"] == 20.0 and r["upstream_3d_mm"] == 210.0 and r["vote"] == "warning"
    assert watch.rain_signal(FLOOD, (25.0, 91.5), AS_OF, TODAY, fake_get(fail=True))["ok"] is False


def test_a_recent_day_uses_the_forecast_endpoints_and_an_old_day_the_archive():
    urls = []

    def spy(url, timeout=30):
        urls.append(url)
        return fake_get()(url)
    vs = alerts.villages(FLOOD)[:2]
    watch.river_signal(vs, TODAY, TODAY, spy)
    watch.river_signal(vs, AS_OF, TODAY, spy)
    assert "past_days" in urls[0] and "start_date" in urls[1]


# --- the optional AI reader --------------------------------------------------------------------------------

def test_the_ai_is_chosen_from_environment_variables_only():
    assert watch.ai_provider({}) is None
    assert watch.ai_provider({"GEMINI_API_KEY": "k"})["kind"] == "gemini"
    p = watch.ai_provider({"AI_API_KEY": "k", "AI_BASE_URL": "https://x.test/v1/", "AI_MODEL": "m"})
    assert p["kind"] == "openai" and p["base"] == "https://x.test/v1"
    assert watch.ai_provider({"AI_API_KEY": "k"}) is None


def test_the_prompt_has_only_dates_places_and_numbers_and_admits_the_limit():
    prompt = watch.build_prompt("Sunamganj, Bangladesh", {1: {"before": 0.1, "now": 0.3}}, 1)
    assert "@" not in prompt and "http" not in prompt
    assert "cannot read a river's height" in prompt and "0.1 -> 0.3" in prompt


def test_gemini_request_has_the_image_the_schema_and_the_key_only_in_a_header():
    sent = []
    png, markers = watch.render_image(FLOOD, alerts.villages(FLOOD))
    out = watch.ai_read(GEMINI, png, "prompt", fake_post(record=sent))
    url, headers, body = sent[0]
    assert "gemini-test:generateContent" in url and "test-key-123" not in url
    assert headers == {"x-goog-api-key": "test-key-123"}
    part = body["contents"][0]["parts"]
    assert part[1]["inline_data"]["mime_type"] == "image/png" and body["generationConfig"]["responseMimeType"] == "application/json"
    assert out["overall_trend"] == "rising"


def test_an_openai_compatible_free_api_works_the_same_way():
    sent = []
    provider = {"kind": "openai", "key": "k", "base": "https://free.test/v1", "model": "vision-free"}
    out = watch.ai_read(provider, b"\x89PNG", "prompt", fake_post(record=sent))
    url, headers, body = sent[0]
    assert url == "https://free.test/v1/chat/completions" and headers["Authorization"] == "Bearer k"
    assert body["messages"][0]["content"][1]["type"] == "image_url"
    assert out["villages"][0]["risk"] == "critical"


def test_what_the_ai_invents_is_dropped_and_low_confidence_gives_no_vote():
    markers = {1: "v1", 2: "v2"}
    raw = {"confidence": 0.9, "overall_trend": "rising", "summary": "s", "limits": "l", "villages": [
        {"marker": 1, "risk": "critical", "reason": "r"}, {"marker": 99, "risk": "critical", "reason": "invented"},
        {"marker": 2, "risk": "apocalypse", "reason": "bad level"}, {"risk": "watch"}, "junk"]}
    ok = watch.parse_ai(raw, markers)
    assert set(ok["villages"]) == {"v1"} and ok["villages"]["v1"]["vote"] == "critical"
    shaky = watch.parse_ai({**raw, "confidence": 0.2}, markers)
    assert shaky["villages"]["v1"]["vote"] == "none"
    assert watch.parse_ai({"villages": "nonsense", "confidence": "x"}, markers)["ok"] is False


# --- the whole watch ---------------------------------------------------------------------------------------

def test_two_agreeing_signals_flag_the_villages_and_the_report_says_where_each_vote_came_from():
    rep = watch.run(FLOOD, as_of=AS_OF, today=TODAY, use_ai=False, get=fake_get(river=(100.0, 250.0), rain_local=130.0))
    assert rep["ok"] and rep["mode"].startswith("replay")
    assert all(v["level"] != "none" for v in rep["villages"])
    assert all({"satellite", "river", "rain"} <= set(v["votes"]) for v in rep["villages"])
    assert rep["ai"]["ok"] is False


def test_the_ai_alone_can_never_raise_an_alert():
    rep = watch.run(FLOOD, as_of=AS_OF, today=TODAY, get=fake_get(fail=True), post=fake_post("critical"), provider=GEMINI)
    assert rep["ai"]["ok"]                                                           # the AI said critical everywhere ...
    assert all(v["level"] == "none" for v in rep["villages"])                         # ... and nothing was flagged


def test_the_ai_adds_a_vote_when_the_others_are_present_and_a_failing_ai_does_not_stop_the_watch():
    rep = watch.run(FLOOD, as_of=AS_OF, today=TODAY, get=fake_get(river=(100.0, 100.0), rain_local=0.0),
                    post=fake_post("warning"), provider=GEMINI)
    assert all("ai" in v["votes"] for v in rep["villages"])
    assert all(v["level"] == "none" for v in rep["villages"])                         # AI alone again

    def broken(url, headers, body, timeout=90):
        raise OSError("quota")
    rep = watch.run(FLOOD, as_of=AS_OF, today=TODAY, get=fake_get(river=(100.0, 250.0), rain_local=130.0), post=broken, provider=GEMINI)
    assert rep["ok"] and "failed" in rep["ai"]["why"] and any(v["level"] != "none" for v in rep["villages"])


def test_the_report_never_contains_the_api_key(tmp_path):
    rep = watch.run(FLOOD, as_of=AS_OF, today=TODAY, get=fake_get(), post=fake_post(), provider=GEMINI)
    path = watch.save_report(rep, tmp_path)
    assert "test-key-123" not in path.read_text(encoding="utf-8")
    assert watch.load_report(FLOOD, tmp_path)["flood"] == FLOOD


# --- drafts and approval -----------------------------------------------------------------------------------

@pytest.fixture()
def report():
    return watch.run(FLOOD, as_of=AS_OF, today=TODAY, use_ai=False, get=fake_get(river=(100.0, 250.0), rain_local=130.0))


def test_drafts_are_alerts_waiting_for_the_admin_and_nothing_is_sent(report):
    drafts = watch.draft_alerts(report, "Tester")
    assert len(drafts) == len(report["villages"])
    for r in drafts:
        assert r["status"] == "draft" and r["reason"] == "ai_watch" and r["simulation"] is True
        assert "published_at" not in r and r["forecast"]["validated_on_real_data"] is False
    en = drafts[0]["preview"]["en"]["body"]
    assert "Automated early warning" in en and "not validated" in en and "may rise" in en and "Follow official alerts" in en
    assert "will flood" not in en.lower()
    assert "স্বয়ংক্রিয়" in drafts[0]["preview"]["bn"]["body"]


def test_only_the_approved_alert_reaches_that_villages_subscribers(report, monkeypatch):
    monkeypatch.delenv("SAFEWINDOW_ALLOW_LIVE", raising=False)
    rec = watch.draft_alerts(report, "Tester")[0]
    village = rec["village"]
    subs = [{"uid": "t1", "flood": FLOOD, "village": village}, {"uid": "x", "flood": FLOOD, "village": "elsewhere"}]
    got = []

    def send(chosen, data, ttl):
        got.append([s["uid"] for s in chosen])
        return len(chosen), 0
    with pytest.raises(ValueError, match="waiting for approval"):
        alerts.publish(rec, "Admin", subs, {"t1"}, send, verified=True)
    alerts.submit(rec, "Tester")
    alerts.publish(rec, "Admin", subs, {"t1"}, send, verified=True)
    assert got == [["t1"]] and rec["status"] == "published"


def test_the_automated_watch_cannot_reach_real_phones_without_both_switches(monkeypatch):
    vs = alerts.villages(FLOOD)
    monkeypatch.delenv("SAFEWINDOW_ALLOW_LIVE", raising=False)
    monkeypatch.delenv("SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST", raising=False)
    with pytest.raises(ValueError, match="not been validated"):
        alerts.new_alert(FLOOD, vs[0]["id"], "warning", "ai_watch", "Tester", date="2024-06-17", simulation=False)
    monkeypatch.setenv("SAFEWINDOW_ALLOW_LIVE", "1")
    with pytest.raises(ValueError, match="not been validated"):
        alerts.new_alert(FLOOD, vs[0]["id"], "warning", "ai_watch", "Tester", date="2024-06-17", simulation=False)
    monkeypatch.setenv("SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST", "1")
    assert alerts.new_alert(FLOOD, vs[0]["id"], "warning", "ai_watch", "Tester", date="2024-06-17", simulation=False)["simulation"] is False


def test_the_admin_tab_creates_pending_alerts_and_sends_nothing(report):
    from streamlit.testing.v1 import AppTest
    script = f'''
import json, sys
from pathlib import Path
root = Path(r"{ROOT}")
sys.path.insert(0, str(root / "app"))
sys.path.insert(0, str(root))
import streamlit as st
import admin_app
from safewindow import watch

REPORT = json.loads({json.dumps(json.dumps(report))})
watch.load_report = lambda flood, *a, **k: REPORT if flood == REPORT["flood"] else None

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
admin_app.tab_watch("Tester", [])
'''
    at = AppTest.from_string(script, default_timeout=90).run()
    assert not at.exception
    flood_box = at.selectbox(key="w_flood")
    index = next(i for i, o in enumerate(flood_box.options) if "2024" in o and "Sunamganj" in o)
    flood_box.select_index(index).run()
    assert not at.exception
    at.button(key="w_make").click().run()
    assert not at.exception
    saved = at.session_state["saved"]
    assert saved and all(r["status"] == "pending" and r["reason"] == "ai_watch" and r["simulation"] for r in saved)
    assert not any("published_at" in r for r in saved)


def test_watch_reports_do_not_go_where_the_daily_check_reader_looks():
    from safewindow import monitor
    assert watch.REPORT_DIR != monitor.MONITOR_DIR


def test_ai_error_says_why_and_never_shows_the_key():
    import io
    import urllib.error
    body = b'{"error": {"code": 403, "message": "The Gemini API free tier is not available for this project. key=SECRET123"}}'
    exc = urllib.error.HTTPError("https://example.org", 403, "Forbidden", {}, io.BytesIO(body))
    text = watch.ai_error_text(exc, {"key": "SECRET123"})
    assert text.startswith("HTTP 403: The Gemini API free tier is not available") and "SECRET123" not in text
    assert watch.ai_error_text(ValueError("x")) == "ValueError"


def test_gemini_answer_in_several_parts_is_joined_and_blocks_are_explained():
    reply = {"candidates": [{"content": {"parts": [{"text": '{"a": '}, {"text": "1}"}]}}]}
    assert watch.gemini_text(reply) == '{"a": 1}'
    with_thought = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": "{}"}]}}]}
    assert watch.gemini_text(with_thought) == "{}"
    import pytest
    with pytest.raises(watch.AIRefused, match=r"blocked the request \(SAFETY\)"):
        watch.gemini_text({"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(watch.AIRefused, match=r"no text \(finishReason MAX_TOKENS\)"):
        watch.gemini_text({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]})
    assert watch.ai_error_text(watch.AIRefused("Gemini returned no answer")) == "Gemini returned no answer"


def test_json_wrapped_in_fences_or_words_is_read():
    assert watch.parse_json_text('```json\n{"x": 2}\n```') == {"x": 2}
    assert watch.parse_json_text('Here is the result: {"x": 3} Hope it helps.') == {"x": 3}
    assert watch.parse_json_text('{"x": 4}') == {"x": 4}


def test_ai_ping_checks_a_key_with_one_small_request():
    seen = {}
    def post(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}
    assert watch.ai_ping({"kind": "gemini", "key": "k", "model": "gemini-3.5-flash"}, post) == "OK"
    assert seen["url"].endswith("gemini-3.5-flash:generateContent") and seen["headers"] == {"x-goog-api-key": "k"}
    assert "inline_data" not in str(seen["body"])                     # no image: cheap


def test_gemini_moves_on_from_a_busy_or_retired_model():
    import io
    import urllib.error
    tried = []
    def post(url, headers, body):
        model = url.split("/models/")[1].split(":")[0]
        tried.append(model)
        if model == "gemini-3.8-flash":
            raise urllib.error.HTTPError(url, 503, "busy", {}, io.BytesIO(b'{"error": {"message": "high demand"}}'))
        if model == "gemini-flash-latest":
            raise TimeoutError("no answer")
        return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}
    provider = watch.ai_provider({"GEMINI_API_KEY": "k"})
    assert provider["models"] == list(watch.GEMINI_MODELS)
    assert watch.ai_ping(provider, post) == "OK"
    assert tried == ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"] and provider["model"] == "gemini-3.5-flash"
    # a chosen model is the only one tried; a wrong key (401) is not retried with other models
    only = watch.ai_provider({"GEMINI_API_KEY": "k", "GEMINI_MODEL": "gemini-x"})
    assert only["models"] == ["gemini-x"]
    def bad_key(url, headers, body):
        raise urllib.error.HTTPError(url, 401, "bad", {}, io.BytesIO(b"{}"))
    import pytest
    with pytest.raises(urllib.error.HTTPError):
        watch.ai_ping(watch.ai_provider({"GEMINI_API_KEY": "k"}), bad_key)


# --- running on its own: no repeats, the admin is told, the maps come from the published app ---------------

def test_a_village_is_not_drafted_again_for_the_same_satellite_date_unless_the_level_rises(report):
    flagged = {r["village"]: r["level"] for r in report["villages"] if r["level"] != "none"}
    assert flagged
    village, level = next(iter(flagged.items()))
    assert watch.villages_to_draft(report, []) == set(flagged)
    same = {"reason": "ai_watch", "flood": FLOOD, "village": village, "date": report["issue_date"], "level": level}
    for status in ("pending", "cancelled", "published"):               # rejected or already sent: still not again
        assert village not in watch.villages_to_draft(report, [{**same, "status": status}])
    assert village in watch.villages_to_draft(report, [{**same, "date": "2024-06-12"}])          # a newer pass
    assert village in watch.villages_to_draft(report, [{**same, "reason": "roads"}])             # a hand-made alert
    if level != "watch":
        assert village in watch.villages_to_draft(report, [{**same, "level": "watch"}])          # the level rose


def test_the_admins_phones_are_told_what_waits_and_no_village_is(report):
    drafts = watch.draft_alerts(report, "Tester")
    subs = [{"uid": "admin1", "flood": FLOOD, "village": drafts[0]["village"], "token": "t", "lang": "bn"},
            {"uid": "villager", "flood": FLOOD, "village": drafts[0]["village"], "token": "u", "lang": "bn"}]
    got = []

    def send(chosen, data, ttl):
        got.append(([s["uid"] for s in chosen], data))
        return len(chosen), 0
    assert alerts.notify_admins(drafts, subs, {"admin1"}, send) == (1, 0)
    (uids, data), = got
    assert uids == ["admin1"]
    for lang in ("bn", "en"):
        d = data[lang]
        assert d["kind"] == "admin" and d["village"] == "" and d["id"].startswith("admin-")
        assert all(isinstance(v, str) for v in d.values())
    assert f"{len(drafts)} alert(s) waiting" in data["en"]["title"] and "approve or reject" in data["en"]["body"]
    assert "replay" in data["en"]["body"]                               # an old flood day is not called live
    assert "অনুমোদনের অপেক্ষায়" in data["bn"]["title"]
    assert alerts.notify_admins([], subs, {"admin1"}, send) == (0, 0)  # nothing new: nobody is woken up
    assert alerts.notify_admins(drafts, subs, set(), send) == (0, 0)   # no admin phone registered
    assert len(got) == 1


def test_the_flood_maps_are_copied_from_the_published_app_and_the_apps_page_is_not_taken_for_a_map(tmp_path):
    src = alerts.APP_DATA
    page = b"<!doctype html><html>SafeWindow</html>"                  # what the hosting answers for a missing file
    missing = {"20240617"}

    def get_bytes(url):
        rel = url.split("/data/", 1)[1]
        if any(day in rel for day in missing):
            return page
        path = src / rel
        return path.read_bytes() if path.exists() else page
    out = watch.mirror_app_data("https://example.test/data/", [FLOOD], tmp_path / "copy", get_bytes)
    assert (out / "index.json").exists() and (out / FLOOD / "villages.json").exists()
    assert not (out / FLOOD / "flood" / "20240617.png").exists()
    assert (out / FLOOD / "flood" / "20240612.png").read_bytes() == (src / FLOOD / "flood" / "20240612.png").read_bytes()
    assert "2024-06-17" not in watch.usable_dates(FLOOD, out)
    with pytest.raises(FileNotFoundError, match="not in the published app"):
        watch.mirror_app_data("https://example.test/data", ["no_such_flood"], tmp_path / "x", get_bytes)
