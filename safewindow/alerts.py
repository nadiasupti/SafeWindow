"""Village alerts for the mobile app: wording, recipients and the alert lifecycle (app plan, sections 7 and step 3).

    Draft -> Pending approval -> Published -> Cancelled, or Expired when its time is over

Used by scripts/send_alert.py (command line) and app/admin_app.py (local admin panel). Every alert, and every
action on it, is kept in Firestore `alerts/{id}` with a history of who did what and when. Phones cannot read that
collection (firestore.rules); only the Admin SDK can.

SIMULATION alerts go only to registered test phones. Real alerts to every subscriber of a village are refused unless
the environment variable SAFEWINDOW_ALLOW_LIVE=1 is set on the admin's computer.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DATA = ROOT / "pwa" / "public" / "data"
LEVELS = ("watch", "warning", "critical")
REASONS = ("roads", "isolated", "rain", "forecast", "ai_watch", "official")
UNVALIDATED_REASONS = ("forecast", "ai_watch")      # automated: never validated on real floods
STATUSES = ("draft", "pending", "published", "cancelled", "expired")
MAX_HOURS = 72

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
BN_MONTHS = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর",
             "নভেম্বর", "ডিসেম্বর"]
EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# The wording follows the plan, section 4: possible flooding, never "road cut", "safe route" or a relief date.
TEXT = {
    "bn": {
        "level": {"watch": "🟡 পর্যবেক্ষণ", "warning": "🟠 সতর্কতা", "critical": "🔴 জরুরি"},
        "roads": "গ্রামের রাস্তায় সম্ভাব্য প্লাবন দেখা গেছে (radar: {d})।",
        "isolated": "গ্রামটা আশ্রয়কেন্দ্র থেকে বিচ্ছিন্ন দেখা গেছে (radar: {d})।",
        "rain": "উজানে ভারী বৃষ্টি (NASA GPM: {d})। পর্যবেক্ষণে রাখুন, প্রস্তুতি নিন।",
        "ai_watch": "স্বয়ংক্রিয় আগাম সতর্কতা (স্যাটেলাইট পানির মানচিত্র ও নদীর তথ্য, যাচাই হয়নি): আগামী কয়েক দিনে এই গ্রামের কাছে পানি বাড়তে পারে (দেখা হয়েছে: {d})। নজরে রাখুন, প্রস্তুতি নিন।",
        "forecast": "মডেলের অনুমান (demo, কৃত্রিম ডেটায় শেখানো, যাচাই হয়নি): আগামী ৩ দিনে এখানে প্লাবন হতে পারে (পূর্বাভাস: {d})। নজরে রাখুন, প্রস্তুতি নিন।",
        "see_app": "সম্ভাব্য পথ ও আশ্রয়কেন্দ্র app-এ দেখুন।",
        "official": "অফিসিয়াল সতর্কবার্তা মেনে চলুন।",
        "simulation": "SIMULATION · ",
        "cancelled_title": "বাতিল",
        "cancelled_body": "আগের এই সতর্কতা ফেরত নেওয়া হয়েছে। অফিসিয়াল সতর্কবার্তা মেনে চলুন।",
    },
    "en": {
        "level": {"watch": "🟡 Watch", "warning": "🟠 Warning", "critical": "🔴 Critical"},
        "roads": "Possible flooding seen on the village's roads (radar: {d}).",
        "isolated": "The village was seen cut off from every shelter (radar: {d}).",
        "rain": "Heavy rain upstream (NASA GPM: {d}). Keep watching and get ready.",
        "ai_watch": "Automated early warning from satellite water maps and river data (not validated): water may rise near this village in the next few days (checked {d}). Keep watching and get ready.",
        "forecast": "Model estimate (demo, trained on synthetic data, not validated): flooding may become possible here in the next 3 days (forecast of {d}). Keep watching and get ready.",
        "see_app": "See the possible route and shelters in the app.",
        "official": "Follow official alerts.",
        "simulation": "SIMULATION · ",
        "cancelled_title": "Cancelled",
        "cancelled_body": "This earlier alert has been withdrawn. Follow official alerts.",
    },
}


# --- wording -----------------------------------------------------------------------------------------------

def day_text(iso: str, lang: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{str(d).translate(BN_DIGITS)} {BN_MONTHS[m - 1]}" if lang == "bn" else f"{d} {EN_MONTHS[m - 1]}"


def village_name(v: dict, lang: str) -> str:
    return (v.get("name_local") if lang == "bn" else None) or v["name"]


def compose(v: dict, lang: str, level: str, reason: str, simulation: bool, date: str | None = None,
            official_text: str | None = None) -> tuple[str, str]:
    """(title, body) of one alert in one language."""
    t = TEXT[lang]
    title = f"{t['simulation'] if simulation else ''}{t['level'][level]} · SafeWindow · {village_name(v, lang)}"
    what = official_text if reason == "official" else t[reason].format(d=day_text(date, lang))
    parts = [what] + ([t["see_app"]] if reason in ("roads", "isolated", "forecast", "ai_watch") else []) + [t["official"]]
    return title, " ".join(parts)


def check(level: str, reason: str, date: str | None, texts: dict | None, hours: int) -> None:
    """Refuse an alert that breaks the rules, with a reason a person can act on."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    if reason != "official" and not date:
        raise ValueError(f"reason {reason!r} needs the date of the radar image or rainfall")
    if reason == "official" and not (texts and texts.get("bn", "").strip() and texts.get("en", "").strip()):
        raise ValueError("an official warning needs its exact words in Bangla and English")
    if not 1 <= hours <= MAX_HOURS:
        raise ValueError(f"an alert stays valid for 1 to {MAX_HOURS} hours")


# --- app data ----------------------------------------------------------------------------------------------

def floods(data_dir: Path = APP_DATA) -> list[dict]:
    path = data_dir / "index.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run scripts/build_pwa.py first")
    return json.loads(path.read_text(encoding="utf-8"))["floods"]


def villages(flood: str, data_dir: Path = APP_DATA) -> list[dict]:
    path = data_dir / flood / "villages.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run scripts/build_pwa.py, and check the flood id")
    return json.loads(path.read_text(encoding="utf-8"))


def village_record(flood: str, village: str, data_dir: Path = APP_DATA) -> dict:
    for v in villages(flood, data_dir):
        if v["id"] == village:
            return v
    raise KeyError(f"village {village!r} is not in flood {flood!r}")


def flood_status(flood: str, data_dir: Path = APP_DATA) -> dict:
    """{dates: [...], villages: {id: 'ciu...'}} as the app shows it."""
    return json.loads((data_dir / flood / "status.json").read_text(encoding="utf-8"))


# --- the alert record and its lifecycle --------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _event(rec: dict, action: str, by: str, now: datetime, note: str = "") -> None:
    rec.setdefault("history", []).append({"at": _iso(now), "action": action, "by": by, **({"note": note} if note else {})})


def new_alert(flood: str, village: str, level: str, reason: str, by: str, *, date: str | None = None,
              texts: dict | None = None, hours: int = 24, simulation: bool = True, demo: bool = False,
              forecast: dict | None = None, now: datetime | None = None, data_dir: Path = APP_DATA) -> dict:
    """A draft alert, checked against the rules. Nothing is sent. `forecast` (model forecasts only) records the
    probability, the rain inputs and the model's status next to the alert."""
    if not by.strip():
        raise ValueError("write your name: every action is logged")
    check(level, reason, date, texts, hours)
    if reason in UNVALIDATED_REASONS and not simulation and not forecast_live_allowed():
        raise ValueError(FORECAST_LIVE_REFUSAL)
    now = now or _now()
    v = village_record(flood, village, data_dir)
    rec = {"id": uuid.uuid4().hex, "status": "draft", "flood": flood, "village": village,
           "village_name": village_name(v, "en"), "level": level, "reason": reason, "date": date,
           "texts": texts or {}, "hours": hours, "simulation": simulation, "demo": demo,
           "created_at": _iso(now), "created_by": by.strip()}
    if forecast:
        rec["forecast"] = forecast
    rec["preview"] = {lang: dict(zip(("title", "body"), compose(v, lang, level, reason, simulation, date,
                                                                 (texts or {}).get(lang)))) for lang in ("bn", "en")}
    _event(rec, "created", by.strip(), now)
    return rec


def submit(rec: dict, by: str, now: datetime | None = None) -> dict:
    """Draft -> pending approval."""
    if rec["status"] != "draft":
        raise ValueError(f"only a draft can be sent for approval (this one is {rec['status']})")
    rec["status"] = "pending"
    _event(rec, "submitted", by, now or _now())
    return rec


def reject(rec: dict, by: str, note: str, now: datetime | None = None) -> dict:
    """Pending -> cancelled, never sent."""
    if rec["status"] not in ("draft", "pending"):
        raise ValueError(f"only an unsent alert can be rejected (this one is {rec['status']})")
    if not note.strip():
        raise ValueError("write why it is rejected")
    rec["status"] = "cancelled"
    _event(rec, "rejected", by, now or _now(), note.strip())
    return rec


def status_now(rec: dict, now: datetime | None = None) -> str:
    """The stored status, or 'expired' once a published alert's time is over."""
    if rec["status"] == "published" and rec.get("expires_at") and datetime.fromisoformat(rec["expires_at"]) <= (now or _now()):
        return "expired"
    return rec["status"]


DUPLICATE_MINUTES = 10


def recent_duplicate(rec: dict, all_alerts: list[dict], now: datetime | None = None,
                     minutes: int = DUPLICATE_MINUTES) -> dict | None:
    """A still-valid alert with the same village, level, reason and date sent in the last `minutes`, if any.
    Stops a double click (or two people) sending the same alert twice."""
    now = now or _now()
    key = ("flood", "village", "level", "reason", "date", "simulation")
    for other in all_alerts:
        if other.get("id") == rec.get("id") or other.get("status") != "published" or not other.get("published_at"):
            continue
        if all(other.get(k) == rec.get(k) for k in key) and \
                now - datetime.fromisoformat(other["published_at"]) < timedelta(minutes=minutes):
            return other
    return None


def message_data(rec: dict, lang: str, cancelled: bool = False) -> dict:
    """The FCM data message (all values strings): the app's service worker shows it and keeps a copy."""
    p = rec["preview"][lang]
    title, body = p["title"], p["body"]
    if cancelled:
        title = f"{TEXT[lang]['cancelled_title']} · {title}"
        body = TEXT[lang]["cancelled_body"]
    return {"id": rec["id"], "level": rec["level"], "flood": rec["flood"], "village": rec["village"],
            "title": title, "body": body, "simulation": "1" if rec["simulation"] else "0",
            "cancelled": "1" if cancelled else "0", "sent_at": rec.get("published_at", ""),
            "expires_at": rec.get("expires_at", ""), "link": f"/village?flood={rec['flood']}&village={rec['village']}"}


def recipients(subscriptions: list[dict], flood: str, village: str, test_ids: set[str] | None) -> list[dict]:
    """Subscriptions of one village; with test_ids, only those test phones."""
    return [s for s in subscriptions if s.get("flood") == flood and s.get("village") == village
            and (test_ids is None or s["uid"] in test_ids)]


def live_allowed() -> bool:
    return os.environ.get("SAFEWINDOW_ALLOW_LIVE") == "1"


FORECAST_LIVE_REFUSAL = ("an automated forecast (a model trained on synthetic data, or the automated satellite and river-data watch) "
                         "cannot be sent to real phones: it has not been validated against real floods. "
                         "Keep SIMULATION on (test phones only)")


def forecast_live_allowed() -> bool:
    """Sending a forecast from a model that was never validated on real floods to real phones needs this second,
    deliberate switch on top of SAFEWINDOW_ALLOW_LIVE. Leave it off unless the model has been validated."""
    return live_allowed() and os.environ.get("SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST") == "1"


def publish(rec: dict, by: str, subscriptions: list[dict], test_ids: set[str], sender, verified: bool,
            now: datetime | None = None) -> dict:
    """Pending -> published: sends to the village's phones. `verified` is the approver's statement that the source
    and date were checked. `sender(chosen, data_by_lang, ttl_seconds)` returns (sent, failed)."""
    if rec["status"] != "pending":
        raise ValueError(f"only an alert waiting for approval can be published (this one is {rec['status']})")
    if not verified:
        raise ValueError("confirm that you checked the source and the date")
    if not rec["simulation"] and not live_allowed():
        raise ValueError("real alerts are switched off on this computer (SAFEWINDOW_ALLOW_LIVE is not set)")
    if rec["reason"] in UNVALIDATED_REASONS and not rec["simulation"] and not forecast_live_allowed():
        raise ValueError(FORECAST_LIVE_REFUSAL)
    now = now or _now()
    rec["published_at"], rec["expires_at"] = _iso(now), _iso(now + timedelta(hours=rec["hours"]))
    chosen = recipients(subscriptions, rec["flood"], rec["village"], test_ids if rec["simulation"] else None)
    sent, failed = sender(chosen, {lang: message_data(rec, lang) for lang in ("bn", "en")}, rec["hours"] * 3600)
    rec.update(status="published", approved_by=by, sent=sent, failed=failed)
    _event(rec, "approved and published", by, now, f"sent {sent}, failed {failed}")
    return rec


def cancel(rec: dict, by: str, note: str, subscriptions: list[dict], test_ids: set[str], sender,
           now: datetime | None = None) -> dict:
    """Published -> cancelled: the same phones get a 'withdrawn' message that replaces the alert."""
    if status_now(rec, now) not in ("published", "expired"):
        raise ValueError(f"only a sent alert can be cancelled (this one is {rec['status']})")
    if not note.strip():
        raise ValueError("write why it is cancelled")
    now = now or _now()
    chosen = recipients(subscriptions, rec["flood"], rec["village"], test_ids if rec["simulation"] else None)
    sent, failed = sender(chosen, {lang: message_data(rec, lang, cancelled=True) for lang in ("bn", "en")},
                          rec["hours"] * 3600)
    rec["status"] = "cancelled"
    _event(rec, "cancelled", by, now, f"{note.strip()} (withdrawal sent {sent}, failed {failed})")
    return rec


# --- Firebase (Admin SDK; GOOGLE_APPLICATION_CREDENTIALS points at the Admin key, never in the repo) ---------

def firestore_client():
    import firebase_admin
    from firebase_admin import firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    return firestore.client()


def load_subscriptions(db) -> list[dict]:
    return [{**d.to_dict(), "uid": d.id} for d in db.collection("subscriptions").stream()]


def load_test_ids(db) -> set[str]:
    return {d.id for d in db.collection("test_devices").stream()}


def load_admin_ids(db) -> set[str]:
    """Phones of the people who approve alerts: told when new alerts wait for approval (admin_devices/{phone id})."""
    return {d.id for d in db.collection("admin_devices").stream()}


# --- telling the admin that alerts are waiting -------------------------------------------------------------

ADMIN_TEXT = {
    "bn": {"title": "🛡️ SafeWindow Admin · {n}টি সতর্কতা অনুমোদনের অপেক্ষায়",
           "body": "স্বয়ংক্রিয় নজরদারি ({mode}, {d}): {list}। Admin panel খুলে যাচাই করুন, তারপর অনুমোদন বা বাতিল করুন। "
                   "আপনি অনুমোদন না দিলে কোনো গ্রামে কিছু যাবে না।",
           "level": {"watch": "পর্যবেক্ষণ", "warning": "সতর্কতা", "critical": "জরুরি"},
           "mode": {"live": "সরাসরি", "replay": "অতীতের দিন"}, "more": "আরও {n}টি"},
    "en": {"title": "🛡️ SafeWindow Admin · {n} alert(s) waiting for approval",
           "body": "Automated watch ({mode}, {d}): {list}. Open the admin panel, check them, then approve or reject. "
                   "No village is told anything until you approve.",
           "level": {"watch": "watch", "warning": "warning", "critical": "critical"},
           "mode": {"live": "live", "replay": "replay of a past day"}, "more": "{n} more"},
}
ADMIN_LIST_MAX = 4               # villages named in the notification; the rest are counted


def admin_notice(drafts: list[dict], lang: str, now: datetime | None = None) -> dict:
    """The FCM data message that tells an admin's phone how many alerts wait for approval. `kind: admin` lets the app
    show it without keeping it as a village alert. All values are strings, like message_data."""
    t, now = ADMIN_TEXT[lang], now or _now()
    ranked = sorted(drafts, key=lambda r: -LEVELS.index(r["level"]))
    names = [f"{r['preview'][lang]['title'].rsplit(' · ', 1)[-1]} ({t['level'][r['level']]})" for r in ranked[:ADMIN_LIST_MAX]]
    if len(ranked) > ADMIN_LIST_MAX:
        names.append(t["more"].format(n=len(ranked) - ADMIN_LIST_MAX))
    first = ranked[0] if ranked else {}
    mode = "live" if (first.get("forecast") or {}).get("mode") == "live" else "replay"
    date = first.get("date")
    n = len(drafts)
    return {"id": f"admin-{uuid.uuid4().hex}", "kind": "admin", "level": first.get("level", "watch"),
            "flood": first.get("flood", ""), "village": "",
            "title": t["title"].format(n=str(n).translate(BN_DIGITS) if lang == "bn" else n),
            "body": t["body"].format(mode=t["mode"][mode], d=day_text(date, lang) if date else "", list=", ".join(names)),
            "simulation": "1", "cancelled": "0", "sent_at": _iso(now), "expires_at": _iso(now + timedelta(hours=24)),
            "link": "/"}


def notify_admins(drafts: list[dict], subscriptions: list[dict], admin_ids: set[str], sender,
                  now: datetime | None = None) -> tuple[int, int]:
    """Tell the admins' phones that `drafts` wait for approval. Nothing goes to any village. Returns (sent, failed).
    An admin phone receives it only if alerts are switched on in the app on that phone (it then has a push address)."""
    if not drafts:
        return 0, 0
    chosen = [s for s in subscriptions if s["uid"] in admin_ids]
    if not chosen:
        return 0, 0
    return sender(chosen, {lang: admin_notice(drafts, lang, now) for lang in ("bn", "en")}, 24 * 3600)


def save(db, rec: dict) -> dict:
    db.collection("alerts").document(rec["id"]).set(rec)
    return rec


def load_alerts(db) -> list[dict]:
    return sorted((d.to_dict() for d in db.collection("alerts").stream()),
                  key=lambda r: r.get("created_at", ""), reverse=True)


def fcm_sender(db):
    """A sender for publish/cancel that uses Firebase Cloud Messaging and drops phones that removed the app."""
    from firebase_admin import messaging

    def send(chosen: list[dict], data_by_lang: dict, ttl: int) -> tuple[int, int]:
        sent = failed = 0
        for s in chosen:
            msg = messaging.Message(token=s["token"], data=data_by_lang[s.get("lang", "bn")],
                                    webpush=messaging.WebpushConfig(headers={"TTL": str(ttl), "Urgency": "high"}))
            try:
                messaging.send(msg)
                sent += 1
            except messaging.UnregisteredError:
                db.collection("subscriptions").document(s["uid"]).delete()      # the phone removed the app
                failed += 1
            except Exception:  # noqa: BLE001 - one phone's failure must not stop the others
                failed += 1
        return sent, failed
    return send
