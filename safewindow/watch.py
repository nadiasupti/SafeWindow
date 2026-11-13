"""Automated early-warning watch: satellite water maps + river and rain data (+ an optional AI image reader).

It runs without a person and ends in a DRAFT alert for the admin. Nothing is sent to phones until the admin approves
it (safewindow/alerts.py: draft -> pending approval -> published -> that village's subscribers).

Signals, each a vote per village: none / watch / warning / critical
  satellite  OUR OWN measurement: the share of the area around the village that Sentinel-1 shows as water, now against
             the previous usable pass (the flood maps the pipeline already made).
  river      Open-Meteo Flood API (free, no key): the river-discharge forecast near the village, as the rise from today.
  rain       Open-Meteo weather API (free, no key): forecast rain here and upstream over the next 3 days.
  ai         OPTIONAL. An AI model (Gemini free tier, or any OpenAI-compatible free API) reads the satellite images and the
             measured numbers and judges each village. It is one vote among the others: it can never raise an alert alone.

An alert is drafted only when at least `min_signals` (default 2) independent signals agree, and its level is the
second-highest vote (the cautious one). The thresholds below are working assumptions, not validated values.

Honest limits: an AI model cannot measure a river's water level in metres from a picture, and it can be wrong, so it only
adds a vote. River discharge (m3/s) from the free API is a modelled value, not a gauge reading. Until this watch has been
checked against real floods, its alerts go only to test phones (see alerts.forecast_live_allowed).
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from safewindow import alerts, flowforecast

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "watch"
LEVEL_NUM = {"none": 0, "watch": 1, "warning": 2, "critical": 3}
NUM_LEVEL = {v: k for k, v in LEVEL_NUM.items()}
MIN_SIGNALS = 2
RADIUS_KM = 3.0                  # the area around a village that is measured
MAX_UNKNOWN = 0.5                # a pass with more unknown than this around the village gives no vote
LIVE_MAX_AGE_DAYS = 10           # a satellite pass older than this is a replay (hindcast), not a live watch

# Working thresholds (assumptions): satellite = (water share now, rise since previous pass) for watch/warning/critical
SAT_CUTS = {"critical": (0.45, 0.10), "warning": (0.25, 0.07), "watch": (0.10, 0.03)}
RIVER_CUTS = {"critical": 2.5, "warning": 1.8, "watch": 1.3}          # forecast peak / today's discharge
RAIN_LOCAL_CUTS = {"critical": 150.0, "warning": 100.0, "watch": 60.0}       # mm in the next 3 days
RAIN_UPSTREAM_CUTS = {"critical": 300.0, "warning": 200.0, "watch": 120.0}
UPSTREAM_POINTS = {"sunamganj": (25.27, 91.72)}                       # Meghalaya hills, by flood id prefix

WATER_RGB, UNKNOWN_RGB = (30, 110, 230), (140, 140, 140)

# --- network (replaceable in tests) ---------------------------------------------------------------------------


def http_get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "safewindow-watch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 - fixed https endpoints
        return json.loads(r.read().decode("utf-8"))


def ai_error_text(exc: Exception, provider: dict | None = None) -> str:
    """Why the AI call failed, readable (e.g. "HTTP 403: free tier is not available..."), never showing the key."""
    import urllib.error
    text = type(exc).__name__
    if isinstance(exc, AIRefused):
        text = str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace"))
            msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("error")
        except Exception:  # noqa: BLE001
            msg = None
        text = f"HTTP {exc.code}" + (f": {str(msg)[:200]}" if msg else "")
    key = (provider or {}).get("key")
    return text.replace(key, "<key>") if key else text


def http_post_json(url: str, headers: dict, body: dict, timeout: int = 90):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310
        return json.loads(r.read().decode("utf-8"))


# --- satellite: our own measurement ---------------------------------------------------------------------------

def usable_dates(flood: str, data_dir: Path = alerts.APP_DATA, up_to: str | None = None) -> list[str]:
    meta = json.loads((data_dir / flood / "metadata.json").read_text(encoding="utf-8"))
    unknown = meta.get("unknown_pct") or {}
    return [d for d in meta["dates"] if (up_to is None or d <= up_to) and unknown.get(d, 0) < 100 and (data_dir / flood / "flood" / f"{d.replace('-', '')}.png").exists()]


def load_mask(flood: str, day: str, data_dir: Path = alerts.APP_DATA) -> tuple[np.ndarray, np.ndarray, list]:
    """(water, unknown, bounds[[S,W],[N,E]]) of one pass. The pipeline paints water blue and no-data grey."""
    meta = json.loads((data_dir / flood / "metadata.json").read_text(encoding="utf-8"))
    bounds = meta["flood_bounds"][day]
    px = np.array(Image.open(data_dir / flood / "flood" / f"{day.replace('-', '')}.png").convert("RGBA"))
    visible = px[..., 3] > 0
    water = visible & (px[..., 0] == WATER_RGB[0]) & (px[..., 1] == WATER_RGB[1]) & (px[..., 2] == WATER_RGB[2])
    unknown = visible & (px[..., 0] == UNKNOWN_RGB[0]) & (px[..., 1] == UNKNOWN_RGB[1])
    return water, unknown, bounds


def share_around(water: np.ndarray, unknown: np.ndarray, bounds: list, lat: float, lon: float,
                 radius_km: float = RADIUS_KM) -> tuple[float | None, float]:
    """(water share of the known pixels within radius_km of the point, unknown share). None if outside the map."""
    (south, west), (north, east) = bounds
    h, w = water.shape
    if not (south <= lat <= north and west <= lon <= east):
        return None, 1.0
    cy, cx = (north - lat) / (north - south) * h, (lon - west) / (east - west) * w
    ry = radius_km / 111.0 / (north - south) * h
    rx = radius_km / (111.0 * math.cos(math.radians(lat))) / (east - west) * w
    y0, y1, x0, x1 = max(int(cy - ry), 0), min(int(cy + ry) + 1, h), max(int(cx - rx), 0), min(int(cx + rx) + 1, w)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    inside = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0
    n = int(inside.sum())
    if n == 0:
        return None, 1.0
    unk = float((unknown[y0:y1, x0:x1] & inside).sum()) / n
    known = inside & ~unknown[y0:y1, x0:x1]
    nk = int(known.sum())
    return (float((water[y0:y1, x0:x1] & known).sum()) / nk if nk else None), unk


def vote_satellite(now: float | None, before: float | None, unk_now: float) -> str:
    if now is None or before is None or unk_now > MAX_UNKNOWN:
        return "none"
    rise = now - before
    for level, (share, step) in SAT_CUTS.items():                 # critical first
        if now >= share and rise >= step:
            return level
    return "none"


def satellite_signal(flood: str, villages: list[dict], data_dir: Path = alerts.APP_DATA, up_to: str | None = None) -> dict:
    dates = usable_dates(flood, data_dir, up_to)
    if len(dates) < 2:
        return {"ok": False, "why": "fewer than two usable satellite passes", "dates": dates}
    latest = dates[-1]
    earlier = [d for d in dates[:-1] if (date.fromisoformat(latest) - date.fromisoformat(d)).days >= 2] or dates[:-1]
    prev = earlier[-1]
    w1, u1, b1 = load_mask(flood, latest, data_dir)
    w0, u0, b0 = load_mask(flood, prev, data_dir)
    out = {"ok": True, "latest": latest, "previous": prev, "villages": {},
           "region_water_share": {"latest": round(float(w1.sum()) / max(1, int((~u1).sum())), 4),
                                  "previous": round(float(w0.sum()) / max(1, int((~u0).sum())), 4)}}
    for v in villages:
        now, unk = share_around(w1, u1, b1, v["lat"], v["lon"])
        before, _ = share_around(w0, u0, b0, v["lat"], v["lon"])
        out["villages"][v["id"]] = {"now": None if now is None else round(now, 4), "before": None if before is None else round(before, 4),
                                    "unknown": round(unk, 3), "vote": vote_satellite(now, before, unk)}
    return out


def render_image(flood: str, villages: list[dict], data_dir: Path = alerts.APP_DATA, panel_w: int = 640,
                 up_to: str | None = None) -> tuple[bytes, dict]:
    """A picture for the AI reader: the previous and the latest pass side by side (water blue, no-data grey) with the
    villages as numbered dots. Returns (PNG bytes, {marker number: village id})."""
    dates = usable_dates(flood, data_dir, up_to)
    latest = dates[-1]
    earlier = [d for d in dates[:-1] if (date.fromisoformat(latest) - date.fromisoformat(d)).days >= 2] or dates[:-1]
    panels, markers = [], {i + 1: v["id"] for i, v in enumerate(villages)}
    for day in (earlier[-1], latest):
        water, unknown, ((south, west), (north, east)) = load_mask(flood, day, data_dir)
        h, w = water.shape
        img = np.full((h, w, 3), (236, 239, 243), dtype=np.uint8)
        img[unknown] = UNKNOWN_RGB
        img[water] = WATER_RGB
        panel = Image.fromarray(img).resize((panel_w, int(panel_w * h / w)), Image.NEAREST)
        d = ImageDraw.Draw(panel)
        for i, v in enumerate(villages):
            x, y = (v["lon"] - west) / (east - west) * panel.width, (north - v["lat"]) / (north - south) * panel.height
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(217, 76, 76), outline=(255, 255, 255))
            d.text((x + 7, y - 6), str(i + 1), fill=(20, 20, 20))
        d.rectangle((0, 0, 190, 16), fill=(255, 255, 255))
        d.text((4, 2), f"Sentinel-1 pass {day}", fill=(0, 0, 0))
        panels.append(panel)
    sheet = Image.new("RGB", (panels[0].width * 2 + 10, panels[0].height), (255, 255, 255))
    sheet.paste(panels[0], (0, 0))
    sheet.paste(panels[1], (panels[0].width + 10, 0))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue(), markers


# --- river and rain: free Open-Meteo APIs ----------------------------------------------------------------------

def _as_list(payload) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def _vote(value: float | None, cuts: dict) -> str:
    if value is None:
        return "none"
    for level, cut in cuts.items():
        if value >= cut:
            return level
    return "none"


def river_signal(villages: list[dict], as_of: date, today: date, get=None) -> dict:
    """Peak river discharge forecast over the next 7 days against today's, near each village. In a replay (as_of in
    the past) the days after `as_of` come from the archive: a hindcast, not a forecast."""
    get = get or http_get_json
    pts = sorted({(round(v["lat"] * 20) / 20, round(v["lon"] * 20) / 20) for v in villages})       # 0.05 degree grid
    q = {"latitude": ",".join(str(p[0]) for p in pts), "longitude": ",".join(str(p[1]) for p in pts), "daily": "river_discharge"}
    if (today - as_of).days <= LIVE_MAX_AGE_DAYS:
        q.update(past_days=3, forecast_days=8)
    else:
        q.update(start_date=(as_of - timedelta(days=3)).isoformat(), end_date=(as_of + timedelta(days=7)).isoformat())
    try:
        data = _as_list(get("https://flood-api.open-meteo.com/v1/flood?" + urllib.parse.urlencode(q, safe=",")))
    except Exception as exc:  # noqa: BLE001 - a missing signal must not stop the watch
        return {"ok": False, "why": f"river API unavailable: {type(exc).__name__}"}
    by_pt = {}
    for pt, d in zip(pts, data):
        days, dis = d["daily"]["time"], d["daily"]["river_discharge"]
        if as_of.isoformat() not in days:
            continue
        i = days.index(as_of.isoformat())
        now = dis[i]
        future = [x for x in dis[i + 1:i + 8] if x is not None]
        if now is None or not future:
            continue
        by_pt[pt] = {"today_m3s": round(now, 1), "peak_next7_m3s": round(max(future), 1), "ratio": round(max(future) / max(now, 1.0), 2)}
    out = {"ok": bool(by_pt), "mode": "forecast" if (today - as_of).days <= LIVE_MAX_AGE_DAYS else "hindcast", "villages": {}}
    for v in villages:
        m = by_pt.get((round(v["lat"] * 20) / 20, round(v["lon"] * 20) / 20))
        out["villages"][v["id"]] = {**(m or {}), "vote": _vote(m["ratio"], RIVER_CUTS) if m else "none"}
    return out


def _rain_sum(get, lat: float, lon: float, as_of: date, today: date) -> float | None:
    q = {"latitude": lat, "longitude": lon, "daily": "precipitation_sum", "timezone": "UTC"}
    if (today - as_of).days <= LIVE_MAX_AGE_DAYS:
        url, q = "https://api.open-meteo.com/v1/forecast?", {**q, "past_days": 3, "forecast_days": 5}
    else:
        url = "https://archive-api.open-meteo.com/v1/archive?"
        q.update(start_date=as_of.isoformat(), end_date=(as_of + timedelta(days=3)).isoformat())
    d = get(url + urllib.parse.urlencode(q))["daily"]
    days, mm = d["time"], d["precipitation_sum"]
    nxt = [mm[days.index((as_of + timedelta(days=k)).isoformat())] for k in (1, 2, 3)
           if (as_of + timedelta(days=k)).isoformat() in days]
    nxt = [x for x in nxt if x is not None]
    return round(sum(nxt), 1) if nxt else None


def rain_signal(flood: str, centre: tuple[float, float], as_of: date, today: date, get=None) -> dict:
    get = get or http_get_json
    out = {"ok": False, "local_3d_mm": None, "upstream_3d_mm": None, "vote": "none"}
    try:
        out["local_3d_mm"] = _rain_sum(get, centre[0], centre[1], as_of, today)
        up = next((p for k, p in UPSTREAM_POINTS.items() if flood.startswith(k)), None)
        if up:
            out["upstream_3d_mm"] = _rain_sum(get, up[0], up[1], as_of, today)
    except Exception as exc:  # noqa: BLE001
        out["why"] = f"rain API unavailable: {type(exc).__name__}"
        return out
    votes = [_vote(out["local_3d_mm"], RAIN_LOCAL_CUTS), _vote(out["upstream_3d_mm"], RAIN_UPSTREAM_CUTS)]
    out["ok"] = out["local_3d_mm"] is not None
    out["vote"] = NUM_LEVEL[max(LEVEL_NUM[v] for v in votes)]
    return out


# --- optional AI image reader ----------------------------------------------------------------------------------

AI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "overall_trend": {"type": "STRING", "enum": ["rising", "stable", "falling", "unknown"]},
        "summary": {"type": "STRING"},
        "villages": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "marker": {"type": "INTEGER"}, "risk": {"type": "STRING", "enum": ["none", "watch", "warning", "critical"]},
            "reason": {"type": "STRING"}}, "required": ["marker", "risk", "reason"]}},
        "confidence": {"type": "NUMBER"},
        "limits": {"type": "STRING"},
    },
    "required": ["overall_trend", "summary", "villages", "confidence", "limits"],
}


# Tried in this order: Google retires model names (gemini-2.5-flash is closed to new keys) and busy models answer 503,
# so the watch moves on to the next one. GEMINI_MODEL, if set, is the only one used.
GEMINI_MODELS = ("gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash")
RETRY_HTTP = (404, 429, 500, 503)


def gemini_call(provider: dict, body: dict, post) -> dict:
    """POST to the first Gemini model that answers; a retired (404), busy (429/5xx) or silent model passes to the next.
    Records the model that answered in provider["model"]. Raises the last error if none answers."""
    import socket
    import urllib.error
    last = None
    for model in provider.get("models") or [provider["model"]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            reply = post(url, {"x-goog-api-key": provider["key"]}, body)
            provider["model"] = model
            return reply
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_HTTP:
                raise
            last = exc
        except (TimeoutError, socket.timeout) as exc:
            last = exc
    raise last


def ai_provider(env=None) -> dict | None:
    """Which AI service to use, from environment variables (keys are never stored in files or logs):
       GEMINI_API_KEY (+ GEMINI_MODEL)                     Google Gemini, free tier
       AI_API_KEY + AI_BASE_URL + AI_MODEL                 any OpenAI-compatible API (OpenRouter free models, Groq, ...)"""
    env = os.environ if env is None else env
    if env.get("GEMINI_API_KEY"):
        models = [env["GEMINI_MODEL"]] if env.get("GEMINI_MODEL") else list(GEMINI_MODELS)
        return {"kind": "gemini", "key": env["GEMINI_API_KEY"], "model": models[0], "models": models}
    if env.get("AI_API_KEY") and env.get("AI_BASE_URL") and env.get("AI_MODEL"):
        return {"kind": "openai", "key": env["AI_API_KEY"], "base": env["AI_BASE_URL"].rstrip("/"), "model": env["AI_MODEL"]}
    return None


def build_prompt(flood_name: str, measured: dict, n_markers: int) -> str:
    """Only dates, place names and measured numbers: nothing about any person or the project's team."""
    lines = [f"- marker {i}: water share within 3 km {m['before']} -> {m['now']}" for i, m in measured.items()]
    return (
        "You are helping a flood early-warning desk. The image shows two Sentinel-1 satellite passes of the same area "
        f"({flood_name}), the earlier on the left and the later on the right. Blue is water seen by radar, grey is no data, "
        "red numbered dots are villages.\n"
        "Describe whether the river and the water around the villages is rising, stable or falling, and give a risk for each "
        "numbered village for the next few days: none, watch, warning or critical.\n"
        "Measured water share around each village (earlier pass -> later pass), computed by software:\n" + "\n".join(lines) + "\n"
        "Rules: you cannot read a river's height in metres from a picture, so do not give one. Use only what is visible and "
        "the numbers above. If the image is unclear, or nothing changed, say so and use risk none. Be cautious; "
        f"cover markers 1 to {n_markers}. Say what you cannot tell in the 'limits' field."
    )


def ai_read(provider: dict, image_png: bytes, prompt: str, post=None) -> dict:
    """Ask the AI; returns the parsed JSON answer (unvalidated: see parse_ai)."""
    post = post or http_post_json
    b64 = base64.b64encode(image_png).decode("ascii")
    if provider["kind"] == "gemini":
        body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": b64}}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json", "responseSchema": AI_SCHEMA}}
        text = gemini_text(gemini_call(provider, body, post))
    else:
        schema_hint = " Answer with JSON only, with the keys overall_trend, summary, villages [{marker, risk, reason}], confidence (0 to 1), limits."
        body = {"model": provider["model"], "temperature": 0.1, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt + schema_hint},
                                                          {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
        reply = post(provider["base"] + "/chat/completions", {"Authorization": f"Bearer {provider['key']}"}, body)
        text = reply["choices"][0]["message"]["content"]
    return parse_json_text(text)


class AIRefused(RuntimeError):
    """The AI service answered but gave no usable text (blocked, empty, or cut off)."""


def gemini_text(reply: dict) -> str:
    """All text parts of Gemini's first answer joined (an answer can come in several parts); a clear reason if the
    service blocked the request or returned nothing."""
    block = (reply.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise AIRefused(f"Gemini blocked the request ({block})")
    cands = reply.get("candidates") or []
    if not cands:
        raise AIRefused("Gemini returned no answer")
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise AIRefused(f"Gemini returned no text (finishReason {cands[0].get('finishReason', 'unknown')})")
    return text


def parse_json_text(text: str) -> dict:
    """JSON from a model's answer, also when it is wrapped in ```json fences or has words around it."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start:end + 1])
        raise


def ai_ping(provider: dict, post=None) -> str:
    """A tiny text-only request, to check a key and model before a full watch. Returns the model's short reply."""
    post = post or http_post_json
    if provider["kind"] == "gemini":
        reply = gemini_call(provider, {"contents": [{"parts": [{"text": "Reply with the single word OK."}]}]}, post)
        return gemini_text(reply).strip()[:40]
    reply = post(provider["base"] + "/chat/completions", {"Authorization": f"Bearer {provider['key']}"},
                 {"model": provider["model"], "messages": [{"role": "user", "content": "Reply with the single word OK."}]})
    return str(reply["choices"][0]["message"]["content"]).strip()[:40]


def parse_ai(raw: dict, markers: dict) -> dict:
    """Keep only what is valid; a village the AI invented is dropped; low confidence gives no votes."""
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    votes = {}
    for item in raw.get("villages", []) if isinstance(raw.get("villages"), list) else []:
        try:
            marker, risk = int(item["marker"]), str(item["risk"]).lower()
        except (KeyError, TypeError, ValueError):
            continue
        if marker in markers and risk in LEVEL_NUM:
            votes[markers[marker]] = {"vote": risk if conf >= 0.5 else "none", "reason": str(item.get("reason", ""))[:300]}
    return {"ok": bool(votes), "confidence": conf, "trend": raw.get("overall_trend", "unknown"),
            "summary": str(raw.get("summary", ""))[:800], "limits": str(raw.get("limits", ""))[:400], "villages": votes}


# --- decide and report ------------------------------------------------------------------------------------------

# Signals that come from the same data are counted once (their highest vote): the flow model learns from the same river-discharge
# series that the river forecast comes from, so they are not independent evidence.
SAME_SOURCE = {"flow_model": "river"}


def decide(votes: dict[str, str], min_signals: int = MIN_SIGNALS) -> str:
    """The level for one village: the second-highest vote, and only if enough independent signals are at 'watch' or more."""
    merged: dict[str, str] = {}
    for name, v in votes.items():
        key = SAME_SOURCE.get(name, name)
        merged[key] = max(merged.get(key, "none"), v, key=LEVEL_NUM.get)
    levels = sorted((LEVEL_NUM[v] for v in merged.values()), reverse=True)
    agreeing = [n for n in levels if n >= 1]
    if len(agreeing) < min_signals:
        return "none"
    return NUM_LEVEL[levels[min_signals - 1]]


def run(flood: str, *, as_of: date | None = None, today: date | None = None, use_ai: bool = True, min_signals: int = MIN_SIGNALS,
        data_dir: Path = alerts.APP_DATA, get=None, post=None, provider: dict | None = None) -> dict:
    """One watch: measure, read the free APIs, ask the AI if configured, decide. Sends nothing, saves nothing."""
    today = today or datetime.now(timezone.utc).date()
    vs = alerts.villages(flood, data_dir)
    name = next((f["name"] for f in alerts.floods(data_dir) if f["id"] == flood), flood)
    up_to = as_of.isoformat() if as_of else None            # a replay looks only at passes up to that day
    sat = satellite_signal(flood, vs, data_dir, up_to)
    if not sat["ok"]:
        return {"flood": flood, "name": name, "ok": False, "why": sat["why"], "villages": []}
    as_of = as_of or date.fromisoformat(sat["latest"])
    mode = "live" if (today - as_of).days <= LIVE_MAX_AGE_DAYS else "replay (hindcast)"
    centre = (float(np.mean([v["lat"] for v in vs])), float(np.mean([v["lon"] for v in vs])))
    river = river_signal(vs, as_of, today, get)
    rain = rain_signal(flood, centre, as_of, today, get)
    site = flowforecast.site_for(flood)
    flow = (flowforecast.forecast_site(site, as_of=as_of, today=today, get=get) if site
            else {"ok": False, "why": "no flow model for this flood's river"})
    ai = {"ok": False, "why": "AI reader not configured (set GEMINI_API_KEY, or AI_API_KEY + AI_BASE_URL + AI_MODEL)"}
    provider = provider if provider is not None else (ai_provider() if use_ai else None)
    if use_ai and provider:
        try:
            png, markers = render_image(flood, vs, data_dir, up_to=up_to)
            measured = {i: sat["villages"][vid] for i, vid in markers.items()}
            ai = parse_ai(ai_read(provider, png, build_prompt(name, measured, len(markers)), post), markers)
            ai["provider"] = f"{provider['kind']}:{provider['model']}"
        except Exception as exc:  # noqa: BLE001 - the watch still works from the other signals
            ai = {"ok": False, "why": f"AI reader failed: {ai_error_text(exc, provider)}"}
    elif not use_ai:
        ai = {"ok": False, "why": "AI reader switched off"}
    rows = []
    for v in vs:
        votes = {"satellite": sat["villages"][v["id"]]["vote"]}
        if river.get("ok"):
            votes["river"] = river["villages"][v["id"]]["vote"]
        if rain.get("ok"):
            votes["rain"] = rain["vote"]
        if flow.get("ok"):
            votes["flow_model"] = flow["vote"]
        if ai.get("ok") and v["id"] in ai["villages"]:
            votes["ai"] = ai["villages"][v["id"]]["vote"]
        level = decide(votes, min_signals)
        rows.append({"village": v["id"], "name": v.get("name_local") or v["name"], "name_en": v["name"], "votes": votes, "level": level,
                     "satellite": sat["villages"][v["id"]], "river": river.get("villages", {}).get(v["id"]),
                     "ai_reason": ai.get("villages", {}).get(v["id"], {}).get("reason") if ai.get("ok") else None})
    return {"flood": flood, "name": name, "ok": True, "mode": mode, "issue_date": as_of.isoformat(), "min_signals": min_signals,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "satellite": {k: v for k, v in sat.items() if k != "villages"}, "river": {k: v for k, v in river.items() if k != "villages"},
            "rain": rain, "flow": flow, "ai": {k: v for k, v in ai.items() if k != "villages"}, "villages": rows,
            "note": "Automated and not validated. Alerts from this watch go to test phones only unless validated."}


def save_report(report: dict, report_dir: Path = REPORT_DIR) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"watch_{report['flood']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_report(flood: str, report_dir: Path = REPORT_DIR) -> dict | None:
    path = report_dir / f"watch_{flood}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def villages_to_draft(report: dict, existing: list[dict]) -> set[str]:
    """Flagged villages that need a new draft. A village is skipped while an automated alert for the same flood and
    satellite date already exists at the same or a higher level, whatever its status: one the admin rejected or
    already sent does not come back every day, but it does come back if the level rises."""
    have: dict[tuple, int] = {}
    for a in existing:
        if a.get("reason") == "ai_watch":
            key = (a.get("flood"), a.get("village"), a.get("date"))
            have[key] = max(have.get(key, 0), LEVEL_NUM.get(a.get("level"), 0))
    return {r["village"] for r in report.get("villages", []) if r["level"] != "none"
            and LEVEL_NUM[r["level"]] > have.get((report["flood"], r["village"], report["issue_date"]), 0)}


# --- the app's data from the published app (for a run without the local pipeline output, e.g. GitHub Actions) ---

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _http_get_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SafeWindow-watch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:        # noqa: S310 - the app's own https address
        return r.read()


def mirror_app_data(base_url: str, floods: list[str], dest: Path, get_bytes=None) -> Path:
    """Copy what the watch reads (index.json; per flood villages.json, metadata.json and the flood maps) from the
    published app into `dest`, and return `dest` to use as data_dir. The hosting answers a missing file with the
    app's page, so a flood map is kept only if it really is a PNG, and a JSON file only if it parses."""
    get_bytes = get_bytes or _http_get_bytes
    base = base_url.rstrip("/")

    def fetch_json(rel: str) -> bytes:
        raw = get_bytes(f"{base}/{rel}")
        try:
            json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FileNotFoundError(f"{base}/{rel} is not in the published app") from exc
        return raw

    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.json").write_bytes(fetch_json("index.json"))
    for flood in floods:
        (dest / flood / "flood").mkdir(parents=True, exist_ok=True)
        for name in ("villages.json", "metadata.json"):
            (dest / flood / name).write_bytes(fetch_json(f"{flood}/{name}"))
        meta = json.loads((dest / flood / "metadata.json").read_text(encoding="utf-8"))
        for day in meta.get("dates", []):
            png = get_bytes(f"{base}/{flood}/flood/{day.replace('-', '')}.png")
            if png.startswith(PNG_MAGIC):
                (dest / flood / "flood" / f"{day.replace('-', '')}.png").write_bytes(png)
    return dest


def draft_alerts(report: dict, by: str, *, simulation: bool = True, hours: int = 24, villages: set[str] | None = None,
                 data_dir: Path = alerts.APP_DATA) -> list[dict]:
    """Draft alerts (nothing sent) for the villages the watch flagged. The admin still approves each one."""
    out = []
    for r in report.get("villages", []):
        if r["level"] == "none" or (villages is not None and r["village"] not in villages):
            continue
        info = {"source": "automated watch", "mode": report.get("mode"), "votes": r["votes"], "satellite": r["satellite"],
                "river": r["river"], "flow": report.get("flow"), "min_signals": report.get("min_signals"), "validated_on_real_data": False}
        out.append(alerts.new_alert(report["flood"], r["village"], r["level"], "ai_watch", by, date=report["issue_date"], hours=hours,
                                    simulation=simulation, forecast=info, data_dir=data_dir))
    return out
