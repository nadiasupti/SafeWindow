import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import send_alert  # noqa: E402

from safewindow import alerts  # noqa: E402

DOL = {"id": "osm6123937356", "name": "Dholkotob village", "name_local": "দোলকোটব"}
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
SUBS = [
    {"uid": "a", "flood": "f", "village": "osm6123937356", "token": "t1", "lang": "bn"},
    {"uid": "b", "flood": "f", "village": "osm6123937356", "token": "t2", "lang": "en"},
    {"uid": "c", "flood": "f", "village": "other", "token": "t3"},
]


@pytest.fixture
def data(tmp_path):
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "villages.json").write_text(json.dumps([DOL]), encoding="utf-8")
    return tmp_path


class Sender:
    """Records what would be sent instead of calling Firebase."""
    def __init__(self):
        self.calls = []

    def __call__(self, chosen, data_by_lang, ttl):
        self.calls.append(([s["uid"] for s in chosen], data_by_lang, ttl))
        return len(chosen), 0


def test_simulation_alert_in_bangla_uses_the_plan_wording():
    title, body = alerts.compose(DOL, "bn", "warning", "roads", True, "2022-05-23")
    assert title.startswith("SIMULATION · ") and "সতর্কতা" in title and "দোলকোটব" in title
    assert "সম্ভাব্য প্লাবন" in body and "২৩ মে" in body
    assert body.endswith("অফিসিয়াল সতর্কবার্তা মেনে চলুন।")
    for word in ("রাস্তা কাটা", "নিরাপদ পথ", "ত্রাণ পৌঁছানোর"):
        assert word not in title + body


def test_official_text_is_passed_on_word_for_word():
    title, body = alerts.compose(DOL, "en", "critical", "official", True, official_text="FFWC: danger level.")
    assert "Critical" in title and body == "FFWC: danger level. Follow official alerts."


@pytest.mark.parametrize("reason,date", [("roads", "2022-05-23"), ("isolated", "2022-05-23"), ("rain", "2022-05-20")])
def test_every_alert_ends_with_follow_official_alerts(reason, date):
    for lang, end in (("bn", "অফিসিয়াল সতর্কবার্তা মেনে চলুন।"), ("en", "Follow official alerts.")):
        assert alerts.compose(DOL, lang, "watch", reason, False, date)[1].endswith(end)


def test_rules_refuse_bad_alerts(data):
    with pytest.raises(ValueError, match="date"):
        alerts.new_alert("f", DOL["id"], "warning", "roads", "Nadia", data_dir=data)
    with pytest.raises(ValueError, match="exact words"):
        alerts.new_alert("f", DOL["id"], "critical", "official", "Nadia", texts={"bn": "x", "en": ""}, data_dir=data)
    with pytest.raises(ValueError, match="hours"):
        alerts.new_alert("f", DOL["id"], "watch", "rain", "Nadia", date="2022-05-20", hours=100, data_dir=data)
    with pytest.raises(ValueError, match="name"):
        alerts.new_alert("f", DOL["id"], "watch", "rain", " ", date="2022-05-20", data_dir=data)


def test_lifecycle_draft_pending_published_with_a_logged_history(data):
    rec = alerts.new_alert("f", DOL["id"], "warning", "roads", "Nadia", date="2022-05-23", hours=6, now=NOW, data_dir=data)
    assert rec["status"] == "draft" and rec["simulation"] is True
    with pytest.raises(ValueError, match="approval"):
        alerts.publish(rec, "Nadia", SUBS, {"a"}, Sender(), verified=True, now=NOW)       # not yet submitted
    alerts.submit(rec, "Nadia", NOW)
    with pytest.raises(ValueError, match="checked"):
        alerts.publish(rec, "Nadia", SUBS, {"a"}, Sender(), verified=False, now=NOW)      # approver must confirm
    send = Sender()
    alerts.publish(rec, "Nadia", SUBS, {"a"}, send, verified=True, now=NOW)
    assert rec["status"] == "published" and rec["sent"] == 1 and rec["expires_at"] == "2026-11-07T18:00:00+00:00"
    assert send.calls[0][0] == ["a"]                       # a SIMULATION reaches test phones only, never b
    assert [h["action"] for h in rec["history"]] == ["created", "submitted", "approved and published"]
    assert alerts.status_now(rec, NOW + timedelta(hours=7)) == "expired"


def test_message_is_strings_only_and_opens_the_village(data):
    rec = alerts.new_alert("f", DOL["id"], "warning", "roads", "Nadia", date="2022-05-23", now=NOW, data_dir=data)
    alerts.submit(rec, "Nadia", NOW)
    send = Sender()
    alerts.publish(rec, "Nadia", SUBS, {"a", "b"}, send, verified=True, now=NOW)
    by_lang = send.calls[0][1]
    assert all(isinstance(v, str) for v in by_lang["bn"].values())          # FCM data values must be strings
    assert by_lang["bn"]["link"] == "/village?flood=f&village=osm6123937356"
    assert "দোলকোটব" in by_lang["bn"]["title"] and "Dholkotob village" in by_lang["en"]["title"]


def test_cancel_sends_a_withdrawal_with_the_same_id(data):
    rec = alerts.new_alert("f", DOL["id"], "critical", "isolated", "Nadia", date="2022-05-23", now=NOW, data_dir=data)
    alerts.submit(rec, "Nadia", NOW)
    alerts.publish(rec, "Nadia", SUBS, {"a"}, Sender(), verified=True, now=NOW)
    send = Sender()
    with pytest.raises(ValueError, match="why"):
        alerts.cancel(rec, "Nadia", " ", SUBS, {"a"}, send, NOW)
    alerts.cancel(rec, "Nadia", "wrong village", SUBS, {"a"}, send, NOW)
    data_bn = send.calls[0][1]["bn"]
    assert rec["status"] == "cancelled" and data_bn["id"] == rec["id"] and data_bn["cancelled"] == "1"
    assert data_bn["title"].startswith("বাতিল") and "ফেরত" in data_bn["body"]
    assert rec["history"][-1]["action"] == "cancelled" and "wrong village" in rec["history"][-1]["note"]


def test_the_same_alert_sent_twice_within_minutes_is_caught(data):
    first = alerts.new_alert("f", DOL["id"], "critical", "isolated", "Nadia", date="2022-05-23", now=NOW, data_dir=data)
    alerts.submit(first, "Nadia", NOW)
    alerts.publish(first, "Nadia", SUBS, {"a"}, Sender(), verified=True, now=NOW)
    again = alerts.new_alert("f", DOL["id"], "critical", "isolated", "Nadia", date="2022-05-23", now=NOW, data_dir=data)
    assert alerts.recent_duplicate(again, [first], now=NOW + timedelta(seconds=2))["id"] == first["id"]   # double click
    assert alerts.recent_duplicate(again, [first], now=NOW + timedelta(minutes=11)) is None               # later: allowed
    other_day = alerts.new_alert("f", DOL["id"], "critical", "isolated", "Nadia", date="2022-05-25", now=NOW, data_dir=data)
    assert alerts.recent_duplicate(other_day, [first], now=NOW) is None                                   # different date
    alerts.cancel(first, "Nadia", "test", SUBS, {"a"}, Sender(), NOW)
    assert alerts.recent_duplicate(again, [first], now=NOW) is None                                       # withdrawn


def test_reject_never_sends(data):
    rec = alerts.new_alert("f", DOL["id"], "watch", "rain", "Nadia", date="2022-05-20", now=NOW, data_dir=data)
    alerts.submit(rec, "Nadia", NOW)
    alerts.reject(rec, "Nadia", "rain data not checked", NOW)
    assert rec["status"] == "cancelled" and "sent" not in rec


def test_real_alerts_need_the_switch_on_this_computer(data, monkeypatch):
    monkeypatch.delenv("SAFEWINDOW_ALLOW_LIVE", raising=False)
    rec = alerts.new_alert("f", DOL["id"], "critical", "isolated", "Nadia", date="2022-05-23", simulation=False,
                           now=NOW, data_dir=data)
    alerts.submit(rec, "Nadia", NOW)
    with pytest.raises(ValueError, match="switched off"):
        alerts.publish(rec, "Nadia", SUBS, {"a"}, Sender(), verified=True, now=NOW)
    monkeypatch.setenv("SAFEWINDOW_ALLOW_LIVE", "1")
    send = Sender()
    alerts.publish(rec, "Nadia", SUBS, set(), send, verified=True, now=NOW)
    assert send.calls[0][0] == ["a", "b"]                  # a real alert reaches every subscriber of the village


def test_command_line_refuses_real_alerts(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["send_alert.py", "--flood", "f", "--village", "v", "--level", "critical",
                                      "--reason", "official", "--text-bn", "x", "--text-en", "x"])
    with pytest.raises(SystemExit, match="Only --simulation"):
        send_alert.main()
