"""The river-flow forecast (Random Forest, the benchmark winner) and how the watch uses it."""
import importlib.util
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from safewindow import alerts, flowforecast as ff, watch  # noqa: E402

SITES = list(ff.SITE_POINTS)
FLOOD = "sunamganj_2024"
AS_OF, TODAY = date(2024, 6, 17), date(2026, 11, 13)
needs_models = pytest.mark.skipif(not all((ff.MODEL_DIR / f"{s}.npz").exists() for s in SITES), reason="run scripts/train_flow_models.py")


@needs_models
@pytest.mark.parametrize("site", SITES)
def test_the_numpy_forest_gives_the_same_numbers_as_the_scikit_learn_forest_it_came_from(site):
    z = np.load(ff.MODEL_DIR / f"{site}.npz")
    model = ff.load_model(site)
    for h in ff.HORIZONS:
        np.testing.assert_allclose(model.forests[h].predict(z["ref_X"]), z[f"ref_h{h}"], atol=1e-4, err_msg=f"{site} +{h} days")
    assert model.meta["numpy_vs_sklearn_max_abs_diff"] < 1e-4


@needs_models
def test_models_say_what_they_are_and_are_small():
    for site in SITES:
        m = ff.load_model(site)
        assert m.meta["validated_on_gauge_data"] is False
        assert "Random Forest" in m.meta["kind"] and m.meta["trained_through"].startswith("2025")
        assert list(m.thresholds) == ["watch", "warning", "critical"] and m.thresholds["watch"] < m.thresholds["warning"] < m.thresholds["critical"]
        assert (ff.MODEL_DIR / f"{site}.npz").stat().st_size < 3e6


def test_the_features_are_exactly_the_ones_the_benchmark_trained_on():
    spec = importlib.util.spec_from_file_location("bm", ROOT / "scripts" / "benchmark_forecasts.py")
    bm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bm)
    raw = ROOT / "data" / "benchmark" / "raw" / "sunamganj_bd.csv"
    if not raw.exists():
        pytest.skip("benchmark data not downloaded")
    bm.RAW = raw.parent
    df = bm.load("sunamganj_bd").iloc[:2500]
    X_bm, _, _ = bm.build(df, "full")
    X_ff = ff.build_features(df, ff.climatology(df, until=bm.TRAIN_END))
    assert list(X_bm.columns) == list(X_ff.columns)
    pd.testing.assert_frame_equal(X_bm, X_ff, check_exact=False, rtol=1e-9, atol=1e-9)


def test_levels_and_the_flood_to_river_mapping():
    th = {"watch": 100.0, "warning": 200.0, "critical": 300.0}
    assert [ff.level_for(q, th) for q in (50, 100, 250, 999)] == ["none", "watch", "warning", "critical"]
    assert ff.site_for("sunamganj_2024") == "sunamganj_bd" and ff.site_for("punjab_trimmu_2025") == "trimmu_pk"
    assert ff.site_for("nepal_terai_2017") == "bara_np" and ff.site_for("somewhere_else") is None


# --- a fake Open-Meteo ---------------------------------------------------------------------------------------------------------

def fake_get(level=500.0, rain=5.0, river=(100.0, 100.0), fail=False):
    """Daily series for whatever dates the URL asks for: constant discharge `level` (single river cell), constant rain."""
    def get(url, timeout=30):
        if fail:
            raise OSError("offline")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "past_days" in q:
            end = TODAY
            start = end - timedelta(days=int(q["past_days"][0]))
        else:
            start, end = date.fromisoformat(q["start_date"][0]), date.fromisoformat(q["end_date"][0])
        days = [(start + timedelta(days=k)).isoformat() for k in range((end - start).days + 1)]
        if "flood-api" in url:
            n = len(q["latitude"][0].split(","))
            if n > 1:                                       # the watch's river-forecast call: today, then later
                dis = [river[0]] * 4 + [river[1]] * (len(days) - 4)
                return [{"daily": {"time": days, "river_discharge": dis}} for _ in range(n)]
            return {"daily": {"time": days, "river_discharge": [level] * len(days)}}
        return {"daily": {"time": days, "precipitation_sum": [rain] * len(days)}}
    return get


@needs_models
def test_a_calm_river_gives_no_vote_and_a_very_high_one_gives_a_capped_vote():
    calm = ff.forecast_site("sunamganj_bd", as_of=AS_OF, today=TODAY, get=fake_get(level=300.0))
    assert calm["ok"] and calm["vote"] == "none" and set(calm["predicted_m3s"]) == {"1", "3", "7"}
    high = ff.forecast_site("sunamganj_bd", as_of=AS_OF, today=TODAY, get=fake_get(level=6000.0, rain=60.0))
    assert high["ok"] and high["levels"]["1"] == "critical"
    assert high["vote"] == "warning"                                  # never above the 1-day cap, never Critical


@needs_models
def test_only_the_one_and_three_day_values_vote_and_each_has_its_cap(monkeypatch):
    big = {"1": 1e9, "3": 1e9, "7": 1e9}
    for which, expected in (("7", "none"), ("3", "watch"), ("1", "warning")):
        def predict(self, X, which=which):
            return {h: np.array([1e9 if str(h) == which else 1.0]) for h in ff.HORIZONS}
        monkeypatch.setattr(ff.SiteModel, "predict", predict)
        r = ff.forecast_site("sunamganj_bd", as_of=AS_OF, today=TODAY, get=fake_get(level=300.0))
        assert r["levels"][which] == "critical" and r["vote"] == expected, which
    assert big  # (documented in the model: no horizon can make this model vote Critical)


def test_a_missing_model_missing_data_or_an_api_outage_is_reported_not_raised(tmp_path):
    assert ff.forecast_site("sunamganj_bd", model_dir=tmp_path)["ok"] is False
    if all((ff.MODEL_DIR / f"{s}.npz").exists() for s in SITES):
        down = ff.forecast_site("sunamganj_bd", as_of=AS_OF, today=TODAY, get=fake_get(fail=True))
        assert down["ok"] is False and "unavailable" in down["why"]


# --- inside the watch ---------------------------------------------------------------------------------------------------------

def test_the_flow_model_and_the_river_forecast_count_as_one_signal():
    assert watch.decide({"river": "watch", "flow_model": "warning"}) == "none"                 # one source, one vote
    assert watch.decide({"river": "warning", "flow_model": "watch"}) == "none"
    assert watch.decide({"flow_model": "warning", "rain": "watch"}) == "watch"                  # two independent sources
    assert watch.decide({"river": "critical", "flow_model": "none", "satellite": "warning"}) == "warning"


@needs_models
def test_the_watch_reports_the_flow_forecast_and_adds_its_vote():
    rep = watch.run(FLOOD, as_of=AS_OF, today=TODAY, use_ai=False, get=fake_get(level=6000.0, rain=0.0))
    assert rep["flow"]["ok"] and rep["flow"]["vote"] == "warning"
    assert all(v["votes"].get("flow_model") == "warning" for v in rep["villages"])
    assert all(v["level"] == "none" for v in rep["villages"])         # the flow model alone is not enough
    both = watch.run(FLOOD, as_of=AS_OF, today=TODAY, use_ai=False, get=fake_get(level=6000.0, rain=70.0))
    assert any(v["level"] != "none" for v in both["villages"])        # flow model + heavy forecast rain agree


def test_a_river_without_a_flow_model_still_runs_on_the_other_signals(monkeypatch):
    monkeypatch.setattr(ff, "SITE_FOR_FLOOD", {})
    rep = watch.run(FLOOD, as_of=AS_OF, today=TODAY, use_ai=False, get=fake_get(river=(100.0, 250.0), rain=70.0))
    assert rep["ok"] and rep["flow"]["ok"] is False and "no flow model" in rep["flow"]["why"]
    assert all("flow_model" not in v["votes"] for v in rep["villages"])
    assert any(v["level"] != "none" for v in rep["villages"])          # river forecast + rain still agree
