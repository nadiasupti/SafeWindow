import csv
import json
from datetime import date, datetime, timezone

from safewindow import monitor

NOW = datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc)


def fake_radar(dates):
    calls = []

    def radar(ee, bbox, start, end):
        calls.append((bbox, start, end))
        return list(dates)
    radar.calls = calls
    return radar


def fake_rain(values):
    def rain(ee, box, start, days):
        assert days == 10 and start == "2026-10-28"           # 7 days before today, and 3 more to step back
        return list(values)
    return rain


def test_rain_windows_never_guess_a_missing_day():
    s = monitor.rain_summary([1, 2, 3, 4, 5, 6, 7.25], date(2026, 11, 6))
    assert s == {"through": "2026-11-06", "1d_mm": 7.2, "3d_mm": 18.2, "7d_mm": 28.2}
    gap = monitor.rain_summary([1, 2, 3, 4, None, 6, 7], date(2026, 11, 6))
    assert gap["1d_mm"] == 7 and gap["3d_mm"] is None and gap["7d_mm"] is None


def test_check_records_radar_rain_and_time(tmp_path):
    radar = fake_radar(["2026-10-24", "2026-10-31", "2026-11-05"])
    r = monitor.check_region("sunamganj_2026", now=NOW, radar=radar, rain=fake_rain([9, 9, 9, 0, 0, 0, 0, 10, 20, 30]),
                             out_dir=tmp_path)
    assert r["checked_at"] == "2026-11-07T06:00:00+00:00" and r["newest_radar"] == "2026-11-05"
    assert r["rain"]["meghalaya_upstream"]["3d_mm"] == 60 and r["rain"]["meghalaya_upstream"]["through"] == "2026-11-06"
    assert r["sends_alerts"] is False
    assert radar.calls[0] == ((91.25, 24.8, 91.75, 25.18), "2026-10-08", "2026-11-08")
    saved = json.loads((tmp_path / "sunamganj_2026.json").read_text(encoding="utf-8"))
    assert saved == r and monitor.load_all(tmp_path) == [r]


def test_new_dates_are_those_the_last_check_had_not_seen(tmp_path):
    rain = fake_rain([1] * 10)
    first = monitor.check_region("sunamganj_2026", now=NOW, radar=fake_radar(["2026-10-31"]), rain=rain, out_dir=tmp_path)
    assert first["new_since_last_check"] == []                 # a first check has nothing to compare with
    second = monitor.check_region("sunamganj_2026", now=NOW, radar=fake_radar(["2026-10-31", "2026-11-05"]), rain=rain,
                                  out_dir=tmp_path)
    assert second["new_since_last_check"] == ["2026-11-05"]
    rows = list(csv.DictReader((tmp_path / "checks.csv").open(encoding="utf-8")))
    assert [row["new_dates"] for row in rows] == ["", "2026-11-05"]


def test_no_radar_image_is_recorded_as_none(tmp_path):
    r = monitor.check_region("punjab_trimmu_2026", now=NOW, radar=fake_radar([]), rain=fake_rain([None] * 10),
                             out_dir=tmp_path)
    assert r["newest_radar"] is None and all(v["3d_mm"] is None for v in r["rain"].values())


def test_rain_ends_on_the_last_complete_day_when_the_latest_is_not_published(tmp_path):
    # in the morning NASA has not finished yesterday (and maybe the day before): those days are None
    r = monitor.check_region("sunamganj_2026", now=NOW, radar=fake_radar(["2026-11-05"]),
                             rain=fake_rain([0, 0, 0, 0, 0, 1, 2, 3, None, None]), out_dir=tmp_path)
    box = r["rain"]["meghalaya_upstream"]
    assert box["through"] == "2026-11-04" and box["1d_mm"] == 3 and box["3d_mm"] == 6 and box["7d_mm"] == 6


def test_a_failing_rain_source_still_records_the_radar(tmp_path):
    def broken(ee, box, start, days):
        raise RuntimeError("Image.multiply: If one image has no bands, the other must also have no bands.")
    r = monitor.check_region("sunamganj_2026", now=NOW, radar=fake_radar(["2026-11-05"]), rain=broken, out_dir=tmp_path)
    assert r["newest_radar"] == "2026-11-05"                    # the radar part is kept
    box = r["rain"]["meghalaya_upstream"]
    assert box["3d_mm"] is None and "Image.multiply" in box["error"]
    assert (tmp_path / "sunamganj_2026.json").exists()
