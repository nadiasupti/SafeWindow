"""Daily check of the monitored regions (app plan, step 4): new Sentinel-1 images and recent NASA GPM rain.

It only looks and records. It never runs the flood pipeline by itself and never sends an alert: what it finds is
shown to the admin (app/admin_app.py, monitoring tab), who decides.

For each region it writes data/monitor/<region>.json and appends a line to data/monitor/checks.csv:
    checked_at            when this check ran (the app's "last checked")
    radar_dates           Sentinel-1 image dates over the region in the last `days` days
    newest_radar          the latest of them
    new_since_last_check  dates not seen by the previous check
    rain                  per rainfall box: mm over the last 1, 3 and 7 complete days, and the day they end on
Days are the region's local calendar days as used by pipeline/04_rainfall_gpm.py.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import region as regions

ROOT = Path(__file__).resolve().parent.parent
MONITOR_DIR = ROOT / "data" / "monitor"
# Regions watched now: the current monsoon areas (the 2026 region files).
MONITORED = ("sunamganj_2026", "punjab_trimmu_2026")
RAIN_WINDOWS = (1, 3, 7)


def _pipeline(name: str):
    """Import a numbered pipeline step (e.g. 04_rainfall_gpm) as a module."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "pipeline" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def radar_dates_ee(ee, bbox, start: str, end: str) -> list[str]:
    """Dates of Sentinel-1 IW images touching the bbox (same filter as pipeline/02a_sentinel1_gee.py)."""
    s1 = _pipeline("02a_sentinel1_gee")
    table = s1.list_dates(ee, ee.Geometry.Rectangle(list(bbox)), start, end)
    return sorted(table["date"].tolist())


def rain_ee(ee, box, start: str, days: int) -> list[float | None]:
    """Daily mm of NASA GPM IMERG over a box (pipeline/04_rainfall_gpm.py)."""
    return _pipeline("04_rainfall_gpm").daily_series(ee, box, start, days)


def rain_summary(daily: list[float | None], end: date) -> dict:
    """mm over the last 1, 3 and 7 days. A window with a missing day is None: never a guessed total."""
    out = {"through": end.isoformat()}
    for w in RAIN_WINDOWS:
        part = daily[-w:]
        out[f"{w}d_mm"] = round(sum(part), 1) if len(part) == w and all(v is not None for v in part) else None
    return out


RAIN_LOOKBACK_DAYS = 3        # extra days fetched, so the windows can end on the last complete day


def rain_or_none(rain, ee, bounds, start: str, end: date) -> dict:
    """The rain summary, ending on the last complete day: NASA publishes a day's 48 half-hour images hours later,
    so the most recent days can still be missing (None); they are left out and `through` says where the windows end.
    If fetching the rain fails, the windows are None with the reason, so the radar part of the check is still
    recorded (one failing source must not lose the whole check)."""
    n = max(RAIN_WINDOWS) + RAIN_LOOKBACK_DAYS
    first = date.fromisoformat(start) - timedelta(days=RAIN_LOOKBACK_DAYS)
    try:
        daily = list(rain(ee, bounds, first.isoformat(), n))
    except Exception as exc:  # noqa: BLE001 - recorded, not hidden
        out = rain_summary([], end)
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return out
    last = end
    while daily and daily[-1] is None and last > first:      # not published yet: step back to a complete day
        daily.pop()
        last -= timedelta(days=1)
    return rain_summary(daily, last) if daily else rain_summary([], end)


def previous(region_id: str, out_dir: Path = MONITOR_DIR) -> dict:
    path = out_dir / f"{region_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def check_region(region_id: str, now: datetime | None = None, days: int = 30, radar=radar_dates_ee,
                 rain=rain_ee, ee=None, out_dir: Path = MONITOR_DIR) -> dict:
    """Look once at one region and record what was found. `radar` and `rain` can be replaced in tests."""
    now = now or datetime.now(timezone.utc)
    reg = regions.load(region_id)
    if reg.bbox is None:
        raise ValueError(f"region {region_id} has no bbox")
    today = now.date()
    last_full_day = today - timedelta(days=1)           # today's rain is still coming in
    dates = radar(ee, reg.bbox, (today - timedelta(days=days)).isoformat(), (today + timedelta(days=1)).isoformat())
    seen = set(previous(region_id, out_dir).get("radar_dates", []))
    start = last_full_day - timedelta(days=max(RAIN_WINDOWS) - 1)
    result = {
        "region": region_id, "name": reg.name, "checked_at": now.isoformat(timespec="seconds"),
        "radar_dates": dates, "newest_radar": dates[-1] if dates else None,
        "new_since_last_check": [d for d in dates if d not in seen] if seen else [],
        "rain": {box: rain_or_none(rain, ee, bounds, start.isoformat(), last_full_day)
                 for box, bounds in reg.rain_boxes.items()},
        "sends_alerts": False,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{region_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    log = out_dir / "checks.csv"
    new_file = not log.exists()
    with log.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["checked_at", "region", "newest_radar", "new_dates", *[f"{b}_3d_mm" for b in reg.rain_boxes]])
        w.writerow([result["checked_at"], region_id, result["newest_radar"] or "", " ".join(result["new_since_last_check"]),
                    *[result["rain"][b]["3d_mm"] if result["rain"][b]["3d_mm"] is not None else "" for b in reg.rain_boxes]])
    return result


def load_all(out_dir: Path = MONITOR_DIR) -> list[dict]:
    """The latest check of every monitored region, for the admin panel."""
    if not out_dir.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out_dir.glob("*.json"))]
