"""River-flow forecast with the model that won the benchmark (Random Forest; see README, "Automated watch and river forecasts").

From the last weeks of river discharge and rain it predicts the discharge 1, 3 and 7 days ahead for a main river, and turns
that into a vote (none / watch / warning / critical) for the automated watch (safewindow/watch.py).

* Data (free APIs, no key): river discharge from the Open-Meteo Flood API (GloFAS: a MODELLED series, not a gauge) and rain at the
  site and upstream from Open-Meteo (ERA5 / weather analysis). Only rain that has already fallen is used, not forecast rain.
* The forest is trained by scripts/train_flow_models.py (scikit-learn, in a separate environment) and exported to plain arrays
  (data/forecast/flow/<site>.npz). This module runs it with numpy only, so the project's own environment needs no scikit-learn.
* The vote uses the 1- and 3-day forecasts only, and is capped by what the test years supported: the 1-day forecast may vote up
  to Warning, the 3-day forecast only Watch, and this model never votes Critical. At 7 days the benchmark found the models miss
  flood peaks (NSE at high flow about -1), so the 7-day value is shown for information and never votes.
* Thresholds are the site's own historical discharge quantiles (95th, 97.5th, 99th). Their hit and false-alarm rates on the
  2020-2025 test years are in data/forecast/flow/evaluation.json. They are not validated against real gauge data.
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "data" / "forecast" / "flow"
HORIZONS = (1, 3, 7)
VOTING_HORIZONS = (1, 3)
# Highest level each horizon may vote for. On the 2020-2025 test years, Watch was caught 84-93% of the time at 1 day and 65-97% at
# 3 days with 83-100% of alarms right; Warning held up only at 1 day; Critical never did (3-9 events per river, weak at 3 days).
VOTE_CAPS = {1: "warning", 3: "watch"}
LIVE_DAYS = 10
LEVEL_QUANTILES = {"watch": 0.95, "warning": 0.975, "critical": 0.99}

# Which benchmark river stands for which app flood (by flood id prefix) and its upstream rain point
SITE_FOR_FLOOD = {"sunamganj": "sunamganj_bd", "punjab_trimmu": "trimmu_pk", "nepal_terai": "bara_np"}
SITE_POINTS = {
    "sunamganj_bd": dict(cell=None, rain=(25.07, 91.40), up=(25.27, 91.72)),
    "kurigram_bd": dict(cell=None, rain=(25.80, 89.65), up=(26.30, 92.00)),
    "trimmu_pk": dict(cell=None, rain=(31.15, 72.15), up=(32.90, 75.00)),
    "bara_np": dict(cell=None, rain=(27.05, 84.95), up=(28.00, 85.40)),
}


# --- features (the same as scripts/benchmark_forecasts.py, 'full' set; a test keeps them identical) ---------------------

def climatology(df: pd.DataFrame, until: str | None = None) -> np.ndarray:
    """Mean log discharge for each day of the year (index 1..366), from the days up to `until`."""
    lq = np.log1p(df["q"])
    use = df["date"] <= pd.Timestamp(until) if until else pd.Series(True, index=df.index)
    by = lq[use].groupby(df["date"][use].dt.day_of_year).mean()
    out = np.full(367, float(lq[use].mean()))
    out[by.index.to_numpy()] = by.to_numpy()
    return out


def build_features(df: pd.DataFrame, clim: np.ndarray) -> pd.DataFrame:
    """Feature table, one row per day, from columns date, q (m3/s), rain, rain_up. Rows without enough history hold NaN."""
    lq = np.log1p(df["q"].astype(float))
    f = {f"lq_l{k}": lq.shift(k) for k in range(14)}
    for w in (3, 7, 14, 30):
        f[f"lq_mean{w}"] = lq.rolling(w).mean()
    f["lq_d1"], f["lq_d3"], f["lq_d7"] = lq - lq.shift(1), lq - lq.shift(3), lq - lq.shift(7)
    f["lq_max30"] = lq.rolling(30).max()
    doy = df["date"].dt.day_of_year
    f["sin"], f["cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    f["anom"] = lq - clim[doy.to_numpy()]
    for w in (1, 2, 3, 5, 7, 14, 30, 60):
        f[f"rain_s{w}"] = np.log1p(df["rain"].rolling(w).sum())
    for w in (1, 3, 7, 14, 30):
        f[f"up_s{w}"] = np.log1p(df["rain_up"].rolling(w).sum())
    return pd.DataFrame(f)


# --- the exported forest ------------------------------------------------------------------------------------------------

class Forest:
    """A Random Forest regressor as flat arrays. Same answers as scikit-learn's predict (checked at export and in tests)."""

    def __init__(self, feature, threshold, left, right, value, roots):
        self.feature, self.threshold, self.left, self.right, self.value, self.roots = feature, threshold, left, right, value, roots

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        n = len(X)
        idx = np.repeat(self.roots[:, None], n, axis=1)               # one cursor per tree and sample
        rows = np.broadcast_to(np.arange(n), idx.shape)
        while True:
            live = self.left[idx] != -1
            if not live.any():
                break
            node = idx[live]
            go_left = X[rows[live], self.feature[node]] <= self.threshold[node]
            idx[live] = np.where(go_left, self.left[node], self.right[node])
        return self.value[idx].mean(axis=0)


class SiteModel:
    def __init__(self, path: Path):
        z = np.load(path, allow_pickle=False)
        self.meta = json.loads(str(z["meta"]))
        self.columns = self.meta["columns"]
        self.clim = z["clim"]
        self.forests = {h: Forest(z[f"h{h}_feature"], z[f"h{h}_threshold"], z[f"h{h}_left"], z[f"h{h}_right"], z[f"h{h}_value"],
                                  z[f"h{h}_roots"]) for h in HORIZONS}
        self.thresholds = self.meta["thresholds"]          # m3/s for watch, warning, critical

    def predict(self, X: pd.DataFrame) -> dict[int, np.ndarray]:
        """Discharge (m3/s) 1, 3 and 7 days after each row's day. The forest predicts the change in log discharge from that day."""
        x = X[self.columns].to_numpy(dtype=np.float32)
        today = X["lq_l0"].to_numpy()
        return {h: np.expm1(today + self.forests[h].predict(x)) for h in HORIZONS}


def load_model(site: str, model_dir: Path = MODEL_DIR) -> SiteModel | None:
    path = model_dir / f"{site}.npz"
    return SiteModel(path) if path.exists() else None


def site_for(flood: str) -> str | None:
    return next((s for p, s in SITE_FOR_FLOOD.items() if flood.startswith(p)), None)


# --- live inputs ---------------------------------------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 40):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "safewindow-flow"})
    with urllib.request.urlopen(req, timeout=timeout) as r:       # noqa: S310 - fixed https endpoints
        return json.loads(r.read().decode("utf-8"))


def fetch_recent(site: str, as_of: date, today: date, model: SiteModel, get=None, days: int = 90) -> pd.DataFrame:
    """The last `days` days up to `as_of`: discharge, rain here and rain upstream. A recent day uses the forecast and weather
    endpoints (with past days); an older day the archives."""
    get = get or _http_get
    p = SITE_POINTS[site]
    cell = model.meta["cell"]
    recent = (today - as_of).days <= LIVE_DAYS
    start, end = as_of - timedelta(days=days), as_of

    def series(url, key):
        d = get(url)["daily"]
        return pd.Series(d[key], index=pd.to_datetime(d["time"]), dtype="float64")

    if recent:
        flood = f"https://flood-api.open-meteo.com/v1/flood?latitude={cell[0]}&longitude={cell[1]}&daily=river_discharge&past_days={days}&forecast_days=1"
        wx = lambda la, lo: (f"https://api.open-meteo.com/v1/forecast?latitude={la}&longitude={lo}&daily=precipitation_sum&timezone=UTC"
                             f"&past_days={days}&forecast_days=1")                                          # noqa: E731
    else:
        flood = (f"https://flood-api.open-meteo.com/v1/flood?latitude={cell[0]}&longitude={cell[1]}&daily=river_discharge"
                 f"&start_date={start}&end_date={end}")
        wx = lambda la, lo: (f"https://archive-api.open-meteo.com/v1/archive?latitude={la}&longitude={lo}&daily=precipitation_sum"
                             f"&timezone=UTC&start_date={start}&end_date={end}")                           # noqa: E731
    q = series(flood, "river_discharge")
    rain = series(wx(*p["rain"]), "precipitation_sum")
    up = series(wx(*p["up"]), "precipitation_sum")
    df = pd.DataFrame({"q": q, "rain": rain, "rain_up": up}).sort_index()
    df = df[df.index <= pd.Timestamp(as_of)]
    df["rain"], df["rain_up"] = df["rain"].fillna(0.0).clip(lower=0.0), df["rain_up"].fillna(0.0).clip(lower=0.0)
    df = df.dropna(subset=["q"]).copy()
    df["q"] = df["q"].clip(lower=0.01)
    df.index.name = "date"
    return df.reset_index()


def level_for(q: float, thresholds: dict) -> str:
    for level in ("critical", "warning", "watch"):
        if q >= thresholds[level]:
            return level
    return "none"


LEVEL_NUM = {"none": 0, "watch": 1, "warning": 2, "critical": 3}


def forecast_site(site: str, *, as_of: date | None = None, today: date | None = None, get=None, model_dir: Path = MODEL_DIR) -> dict:
    """Forecast for one river: today's discharge, the 1-, 3- and 7-day values, the level each reaches, and the vote."""
    model = load_model(site, model_dir)
    if model is None:
        return {"ok": False, "why": f"no flow model for {site} (run scripts/train_flow_models.py)"}
    today = today or date.today()
    as_of = as_of or today
    try:
        df = fetch_recent(site, as_of, today, model, get)
        X = build_features(df, model.clim)
        row = X.iloc[[-1]]
        if row[model.columns].isna().any(axis=1).iloc[0] or len(df) < 61:
            return {"ok": False, "why": "not enough recent data to build the features"}
        pred = {h: float(v[0]) for h, v in model.predict(row).items()}
    except Exception as exc:  # noqa: BLE001 - a missing signal must not stop the watch
        return {"ok": False, "why": f"flow forecast unavailable: {type(exc).__name__}"}
    levels = {h: level_for(pred[h], model.thresholds) for h in HORIZONS}
    capped = [min(levels[h], VOTE_CAPS[h], key=lambda lv: LEVEL_NUM[lv]) for h in VOTING_HORIZONS]
    vote = max(capped, key=lambda lv: LEVEL_NUM[lv])
    return {"ok": True, "site": site, "origin": str(df["date"].iloc[-1].date()), "today_m3s": round(float(df["q"].iloc[-1]), 1),
            "predicted_m3s": {str(h): round(v, 1) for h, v in pred.items()}, "levels": {str(h): lv for h, lv in levels.items()},
            "thresholds_m3s": {k: round(v, 1) for k, v in model.thresholds.items()}, "vote": vote,
            "voting_horizons": list(VOTING_HORIZONS), "vote_caps": {str(h): c for h, c in VOTE_CAPS.items()}, "model": model.meta.get("kind"), "trained_through": model.meta.get("trained_through"),
            "note": "Modelled discharge, not a gauge. The 7-day value is for information: it does not vote."}
