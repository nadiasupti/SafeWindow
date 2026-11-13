"""A flood early-warning DEMO model trained on SYNTHETIC data.

What this is, in plain words
----------------------------
* A small logistic-regression model that estimates, for each village, the chance that flooding becomes possible in the
  next 3 days, from rainfall at the village and upstream (the inputs the daily check already records).
* It is trained on **synthetic** examples made by `synthetic_data()`: invented rainfall patterns and an invented rule
  that decides which of them "flooded". It has learned that invented rule, not the real river. Its numbers show the
  pipeline works (forecast -> draft alert -> admin approval -> village phones); they are NOT a validated flood forecast.
* Real validation needs real past floods and real rainfall (see scripts/early_warning_hindcast.py for the hindcast
  that exists). Until a model is marked validated, forecast alerts go only to registered test phones.

Nothing here sends anything. Alerts are made with safewindow/alerts.py, so they follow the same lifecycle:
draft -> pending approval -> published (admin approves) -> sent to that village's subscribers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "data" / "forecast" / "model.json"

RAIN_COLS = ["rain_1d", "rain_3d", "rain_7d", "upstream_3d", "upstream_7d"]
FEATURES = RAIN_COLS + ["susceptibility"]
HORIZON_DAYS = 3                      # "flooding may become possible within the next 3 days"
LEVEL_CUTS = {"critical": 0.70, "warning": 0.50, "watch": 0.30}   # probability -> alert level
SCENARIOS = {                          # synthetic rainfall scenarios for the demo (mm)
    "calm": dict(rain_1d=1.0, rain_3d=3.0, rain_7d=8.0, upstream_3d=6.0, upstream_7d=15.0),
    "rising": dict(rain_1d=12.0, rain_3d=40.0, rain_7d=90.0, upstream_3d=90.0, upstream_7d=170.0),
    "heavy_upstream": dict(rain_1d=25.0, rain_3d=70.0, rain_7d=140.0, upstream_3d=200.0, upstream_7d=340.0),
}


# --- synthetic training data ------------------------------------------------------------------------------

def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def synthetic_data(n: int = 8000, seed: int = 42) -> pd.DataFrame:
    """Invented village-days. Rainfall is skewed (most days dry, some wet spells); `flood_next_3d` is drawn from a
    made-up rule in which upstream rain, local rain and the village's susceptibility all raise the chance of flooding.
    The rule is a modelling assumption, not physics and not a measurement."""
    rng = np.random.default_rng(seed)
    wet = rng.random(n) < 0.40
    rain_1d = rng.gamma(0.7, 7.0, n) * wet
    rain_3d = rain_1d + rng.gamma(0.9, 9.0, n) * wet
    rain_7d = rain_3d + rng.gamma(1.0, 16.0, n) * wet
    upstream_on = rng.random(n) < 0.45
    upstream_3d = rng.gamma(0.8, 38.0, n) * upstream_on
    upstream_7d = upstream_3d + rng.gamma(1.0, 55.0, n) * upstream_on
    susceptibility = rng.beta(2.0, 2.5, n)
    z = (-4.6 + 0.032 * rain_3d + 0.008 * rain_7d + 0.030 * upstream_3d + 0.010 * upstream_7d
         + 3.0 * susceptibility + rng.normal(0.0, 0.5, n))
    flood = rng.random(n) < _sigmoid(z)
    return pd.DataFrame({"rain_1d": rain_1d, "rain_3d": rain_3d, "rain_7d": rain_7d, "upstream_3d": upstream_3d,
                         "upstream_7d": upstream_7d, "susceptibility": susceptibility, "flood_next_3d": flood.astype(int)})


# --- the model --------------------------------------------------------------------------------------------

def _design(df: pd.DataFrame) -> np.ndarray:
    """Rain is log-transformed (it is very skewed); susceptibility is used as is."""
    cols = [np.log1p(df[c].clip(lower=0).astype(float).to_numpy()) for c in RAIN_COLS]
    cols.append(df["susceptibility"].astype(float).to_numpy())
    return np.column_stack(cols)


@dataclass
class Model:
    weights: list[float]
    bias: float
    mean: list[float]
    std: list[float]
    meta: dict = field(default_factory=dict)

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        z = (_design(df) - np.array(self.mean)) / np.array(self.std)
        return _sigmoid(z @ np.array(self.weights) + self.bias)

    def contributions(self, row: pd.Series) -> list[tuple[str, float]]:
        """What pushed this village's estimate up or down (weight x standardised input), largest first."""
        x = (_design(pd.DataFrame([row])) - np.array(self.mean)) / np.array(self.std)
        c = x[0] * np.array(self.weights)
        return sorted(zip(FEATURES, (float(v) for v in c)), key=lambda kv: -abs(kv[1]))

    def to_json(self) -> str:
        return json.dumps({"weights": self.weights, "bias": self.bias, "mean": self.mean, "std": self.std, "meta": self.meta},
                          indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Model":
        d = json.loads(text)
        return cls(d["weights"], d["bias"], d["mean"], d["std"], d.get("meta", {}))

    @property
    def validated(self) -> bool:
        return bool(self.meta.get("validated_on_real_data", False))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Area under the ROC curve, from ranks (no external library)."""
    ranks = pd.Series(p).rank(method="average").to_numpy()
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def evaluate(model: Model, df: pd.DataFrame) -> dict:
    y = df["flood_next_3d"].to_numpy()
    p = model.predict_proba(df)
    out = {"n": int(len(df)), "base_rate": round(float(y.mean()), 4), "auc": round(auc(y, p), 4),
           "brier": round(float(np.mean((p - y) ** 2)), 4)}
    for level, cut in LEVEL_CUTS.items():
        hit = p >= cut
        out[f"{level}_precision"] = round(float(y[hit].mean()), 4) if hit.any() else None
        out[f"{level}_recall"] = round(float(hit[y == 1].mean()), 4) if (y == 1).any() else None
        out[f"{level}_share_of_days"] = round(float(hit.mean()), 4)
    return out


def train(n: int = 8000, seed: int = 42, steps: int = 4000, lr: float = 0.2, l2: float = 1e-3) -> tuple[Model, dict]:
    """Train on synthetic data, test on a separate synthetic sample (never used for fitting)."""
    data = synthetic_data(n, seed)
    split = int(0.75 * len(data))
    fit, test = data.iloc[:split], data.iloc[split:]
    x = _design(fit)
    mean, std = x.mean(axis=0), x.std(axis=0) + 1e-9
    x = (x - mean) / std
    y = fit["flood_next_3d"].to_numpy(dtype=float)
    w, b = np.zeros(x.shape[1]), 0.0
    for _ in range(steps):
        p = _sigmoid(x @ w + b)
        w -= lr * (x.T @ (p - y) / len(y) + l2 * w)
        b -= lr * float(np.mean(p - y))
    model = Model(w.tolist(), float(b), mean.tolist(), std.tolist(), {
        "kind": "logistic regression on log rainfall + village susceptibility",
        "trained_on": "synthetic data (invented rainfall and an invented flood rule)",
        "validated_on_real_data": False, "horizon_days": HORIZON_DAYS, "seed": seed, "n_train": int(len(fit)),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "warning": "DEMO. Not validated against real floods. Do not present as a forecast.",
    })
    return model, evaluate(model, test)


def load_or_train() -> Model:
    if MODEL_PATH.exists():
        return Model.from_json(MODEL_PATH.read_text(encoding="utf-8"))
    return train()[0]


def save(model: Model, metrics: dict, path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    model.meta["test_metrics"] = metrics
    path.write_text(model.to_json(), encoding="utf-8")


# --- from villages and rainfall to alerts -----------------------------------------------------------------

def susceptibility(v: dict) -> float:
    """A rule of thumb from what the radar timeline showed for the village (not a measured elevation)."""
    base = {"isolated": 0.75, "boat_dependent": 0.65, "uncertain": 0.5, "connected_when_seen": 0.25,
            "never_isolated": 0.1}.get(v.get("outcome"), 0.4)
    if v.get("boat_dependent"):
        base = max(base, 0.65)
    return round(base, 2)


def level_for(p: float) -> str | None:
    for level, cut in LEVEL_CUTS.items():          # critical first
        if p >= cut:
            return level
    return None


def rain_from_monitor(record: dict) -> dict | None:
    """The daily check's rain numbers (data/monitor/<region>.json) as model inputs. None if the numbers are missing."""
    boxes = record.get("rain") or {}
    local = next((v for k, v in boxes.items() if "upstream" not in k), None)
    up = next((v for k, v in boxes.items() if "upstream" in k), None)
    if not local or not up:
        return None
    try:
        vals = dict(rain_1d=local["1d_mm"], rain_3d=local["3d_mm"], rain_7d=local["7d_mm"],
                    upstream_3d=up["3d_mm"], upstream_7d=up["7d_mm"])
    except KeyError:
        return None
    return None if any(v is None for v in vals.values()) else {k: float(v) for k, v in vals.items()}


def forecast_villages(model: Model, villages: list[dict], rain: dict) -> pd.DataFrame:
    """One row per village: probability, alert level ('none' below the lowest cut) and the main reasons, most likely first."""
    rows = []
    for v in villages:
        row = pd.Series({**{c: float(rain[c]) for c in RAIN_COLS}, "susceptibility": susceptibility(v)})
        p = float(model.predict_proba(pd.DataFrame([row]))[0])
        why = [name for name, c in model.contributions(row) if c > 0.15][:3]
        rows.append({"village": v["id"], "name": v.get("name_local") or v["name"], "name_en": v["name"],
                     "population": v.get("population"), "probability": round(p, 3), "level": level_for(p) or "none", "why": why})
    return pd.DataFrame(rows).sort_values("probability", ascending=False).reset_index(drop=True)


def forecast_info(model: Model, probability: float, rain: dict, source: str) -> dict:
    """What is stored with a forecast alert so the admin and the log can see where it came from."""
    return {"probability": probability, "horizon_days": HORIZON_DAYS, "source": source, "rain": rain,
            "model": model.meta.get("kind"), "trained_on": model.meta.get("trained_on"),
            "validated_on_real_data": model.validated}


def draft_alerts(model: Model, table: pd.DataFrame, flood: str, rain: dict, source: str, by: str, *, issue_date: str,
                 simulation: bool = True, hours: int = 24, villages: set[str] | None = None) -> list[dict]:
    """Draft alerts (nothing sent) for the villages in `table` that reach an alert level. `villages` limits the choice.
    Each draft is a normal alert (reason 'forecast'): the admin still approves it before anyone is notified."""
    from safewindow import alerts

    out = []
    for r in table.itertuples():
        if r.level == "none" or (villages is not None and r.village not in villages):
            continue
        out.append(alerts.new_alert(flood, r.village, r.level, "forecast", by, date=issue_date, hours=hours,
                                    simulation=simulation, forecast=forecast_info(model, float(r.probability), rain, source)))
    return out
