"""Benchmark many time-series prediction algorithms on real river and rain data, and see where each is most correct.

    python scripts/benchmark_forecasts.py fetch                 # download the data (free APIs, no key) -> data/benchmark/raw/
    python scripts/benchmark_forecasts.py run --sites all       # train and test every model -> data/benchmark/results/
    python scripts/benchmark_forecasts.py report                # tables, charts and docs/FORECAST_BENCHMARK.md

Data (all free, no key)
  river discharge  Open-Meteo Flood API (GloFAS reanalysis), 1997-2025. A MODELLED series, not a gauge.
  rain             Open-Meteo archive (ERA5) at the site and at an approximate upstream point; NASA POWER (IMERG-based) at the site.

Task: from what is known at the end of day t, predict the river discharge h days later, h = 1, 3 and 7.
Split by time, never at random: train 1997-2016, validation 2017-2019 (early stopping, settings), TEST 2020-2025, which
includes real floods (2020, 2022, 2024). Every model sees the same features and is scored on the same test origins.
The learned models predict the CHANGE in log discharge from today and add it back, so every method starts from persistence.

Models: persistence, seasonal climatology, moving average | Ridge, Lasso, KNN, SVR | decision tree, random forest, extra trees,
gradient boosting, XGBoost, LightGBM, CatBoost | sklearn MLP | ARIMA | LSTM, GRU, 1D-CNN, DLinear, Transformer, PatchTST-style
Transformer | Chronos (pretrained time-series Transformer, zero-shot).
Scores: NSE (1 is perfect, 0 is no better than the mean; hydrology's standard), MAE, skill against persistence, and flood-event
detection (discharge above the training 95th percentile). Also split by season and by high against normal flow.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "benchmark" / "raw"
OUT = ROOT / "data" / "benchmark" / "results"
FIG = ROOT / "docs" / "figures"

SITES = {
    "sunamganj_bd": dict(name="Sunamganj, Bangladesh (Surma, haor)", lat=25.07, lon=91.40, up=(25.27, 91.72)),
    "kurigram_bd": dict(name="Kurigram, Bangladesh (Brahmaputra)", lat=25.80, lon=89.65, up=(26.30, 92.00)),
    "trimmu_pk": dict(name="Trimmu, Pakistan (Chenab)", lat=31.15, lon=72.15, up=(32.90, 75.00)),
    "bara_np": dict(name="Bara-Parsa, Nepal Terai", lat=27.05, lon=84.95, up=(28.00, 85.40)),
}
START, END = "1997-01-01", "2025-12-31"
TRAIN_END, VAL_END = "2016-12-31", "2019-12-31"
HORIZONS = (1, 3, 7)
LAGS = 14
WINDOW = 30
STEP = 3                      # every 3rd test day is a scored origin (ARIMA and Chronos are slow); same for every model


# ---------------------------------------------------------------------------------------------------------------
# data

def _get(url: str, retries: int = 8):
    """GET JSON. The free APIs limit how fast you may ask: on 429 wait a minute and try again."""
    import requests
    time.sleep(2)                                           # be polite: a short pause before every request
    for i in range(retries):
        r = requests.get(url, timeout=180, headers={"User-Agent": "safewindow-benchmark"})
        if r.status_code == 200:
            return r.json()
        wait = 65 if r.status_code == 429 else 3 * (i + 1)
        print(f"    HTTP {r.status_code}, waiting {wait}s", flush=True)
        time.sleep(wait)
    r.raise_for_status()


def main_river_cell(lat: float, lon: float) -> tuple[float, float, float]:
    """The 0.05-degree discharge cell near the point with the largest mean flow: the main river, not a small stream the point
    happens to fall on. Looks at a 7 x 7 block (about 35 km across)."""
    pts = [(round(lat + i * 0.05, 3), round(lon + j * 0.05, 3)) for i in range(-3, 4) for j in range(-3, 4)]
    data = _get("https://flood-api.open-meteo.com/v1/flood?latitude=" + ",".join(str(p[0]) for p in pts) + "&longitude="
                + ",".join(str(p[1]) for p in pts) + "&daily=river_discharge&start_date=2015-01-01&end_date=2019-12-31")
    means = [np.nanmean([v for v in d["daily"]["river_discharge"] if v is not None] or [0.0]) for d in data]
    i = int(np.argmax(means))
    return pts[i][0], pts[i][1], float(means[i])


def fetch_site(key: str) -> pd.DataFrame:
    s = SITES[key]
    clat, clon, mean_q = main_river_cell(s["lat"], s["lon"])
    print(f"  {key}: main-river cell {clat}, {clon} (mean flow {mean_q:.0f} m3/s)")
    q = _get(f"https://flood-api.open-meteo.com/v1/flood?latitude={clat}&longitude={clon}&daily=river_discharge&start_date={START}&end_date={END}")
    df = pd.DataFrame({"date": q["daily"]["time"], "q": q["daily"]["river_discharge"]})
    for col, (la, lo) in (("rain", (s["lat"], s["lon"])), ("rain_up", s["up"])):
        r = _get(f"https://archive-api.open-meteo.com/v1/archive?latitude={la}&longitude={lo}&start_date={START}&end_date={END}&daily=precipitation_sum&timezone=UTC")
        df[col] = r["daily"]["precipitation_sum"]
    p = _get(f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR&community=AG&longitude={s['lon']}&latitude={s['lat']}&start=19970101&end=20251231&format=JSON")
    pw = pd.Series(p["properties"]["parameter"]["PRECTOTCORR"])
    pw.index = pd.to_datetime(pw.index, format="%Y%m%d").strftime("%Y-%m-%d")
    df["rain_power"] = df["date"].map(pw).where(lambda x: x > -900)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load(key: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"{key}.csv", parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=["q"]).copy()
    df["q"] = df["q"].clip(lower=0.01)
    for c in ("rain", "rain_up", "rain_power"):
        df[c] = df[c].fillna(0.0).clip(lower=0.0)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------------------------------------------
# features and targets

def build(df: pd.DataFrame, feature_set: str = "full") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """X (known at the end of day t), Y (log discharge change at +1, +3, +7 days), and bookkeeping."""
    lq = np.log1p(df["q"])
    f = {}
    for k in range(LAGS):
        f[f"lq_l{k}"] = lq.shift(k)
    for w in (3, 7, 14, 30):
        f[f"lq_mean{w}"] = lq.rolling(w).mean()
    f["lq_d1"], f["lq_d3"], f["lq_d7"] = lq - lq.shift(1), lq - lq.shift(3), lq - lq.shift(7)
    f["lq_max30"] = lq.rolling(30).max()
    doy = df["date"].dt.dayofyear
    f["sin"], f["cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    clim = lq.groupby(doy).transform(lambda s: s.loc[df["date"].loc[s.index] <= TRAIN_END].mean())
    f["anom"] = lq - clim
    if feature_set != "base":
        for w in (1, 2, 3, 5, 7, 14, 30, 60):
            f[f"rain_s{w}"] = np.log1p(df["rain"].rolling(w).sum())
    if feature_set in ("full", "full_power"):
        for w in (1, 3, 7, 14, 30):
            f[f"up_s{w}"] = np.log1p(df["rain_up"].rolling(w).sum())
    if feature_set == "full_power":
        for w in (1, 3, 7, 14):
            f[f"pw_s{w}"] = np.log1p(df["rain_power"].rolling(w).sum())
    X = pd.DataFrame(f)
    Y = pd.DataFrame({f"h{h}": lq.shift(-h) - lq for h in HORIZONS})
    return X, Y, {"lq": lq, "clim": clim}


def split_masks(df: pd.DataFrame, X: pd.DataFrame, Y: pd.DataFrame) -> dict[str, np.ndarray]:
    ok = X.notna().all(axis=1).to_numpy() & Y.notna().all(axis=1).to_numpy() & (np.arange(len(df)) >= WINDOW + 60)
    d = df["date"]
    gap = max(HORIZONS)                      # the last 7 origins of a block have targets in the next block: dropped
    train = ok & (d <= pd.Timestamp(TRAIN_END) - pd.Timedelta(days=gap)).to_numpy()
    val = ok & (d > TRAIN_END).to_numpy() & (d <= pd.Timestamp(VAL_END) - pd.Timedelta(days=gap)).to_numpy()
    test = ok & (d > VAL_END).to_numpy()
    idx = np.where(test)[0]
    keep = np.zeros(len(df), bool)
    keep[idx[::STEP]] = True
    return {"train": train, "val": val, "test": test & keep}


# ---------------------------------------------------------------------------------------------------------------
# metrics

def nse(y, p):
    den = float(np.sum((y - y.mean()) ** 2))
    return float(1 - np.sum((y - p) ** 2) / den) if den > 0 else float("nan")


def score(q_true, q_hat, q_persist, thr_event, thr_high, monsoon):
    q_true, q_hat = np.asarray(q_true, float), np.maximum(np.asarray(q_hat, float), 0.0)
    out = {"n": len(q_true), "NSE": nse(q_true, q_hat), "NSE_log": nse(np.log1p(q_true), np.log1p(q_hat)),
           "MAE": float(np.mean(np.abs(q_true - q_hat))), "RMSE": float(np.sqrt(np.mean((q_true - q_hat) ** 2))),
           "MAPE": float(np.mean(np.abs(q_true - q_hat) / np.maximum(q_true, 1.0)) * 100)}
    mse, mse_p = np.mean((q_true - q_hat) ** 2), np.mean((q_true - q_persist) ** 2)
    out["skill_vs_persistence"] = float(1 - mse / mse_p) if mse_p > 0 else float("nan")
    ev, pr = q_true >= thr_event, q_hat >= thr_event
    tp, fp, fn = int((ev & pr).sum()), int((~ev & pr).sum()), int((ev & ~pr).sum())
    out.update(events=int(ev.sum()), event_precision=tp / (tp + fp) if tp + fp else float("nan"),
               event_recall=tp / (tp + fn) if tp + fn else float("nan"), event_f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    hi = q_true >= thr_high
    out["NSE_high_flow"] = nse(q_true[hi], q_hat[hi]) if hi.sum() > 5 else float("nan")
    out["MAPE_high_flow"] = float(np.mean(np.abs(q_true[hi] - q_hat[hi]) / q_true[hi]) * 100) if hi.any() else float("nan")
    out["NSE_monsoon"] = nse(q_true[monsoon], q_hat[monsoon]) if monsoon.sum() > 5 else float("nan")
    out["NSE_dry_season"] = nse(q_true[~monsoon], q_hat[~monsoon]) if (~monsoon).sum() > 5 else float("nan")
    return out


# ---------------------------------------------------------------------------------------------------------------
# models

def tabular_models(quick: bool):
    from catboost import CatBoostRegressor
    from lightgbm import LGBMRegressor
    from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Lasso, Ridge
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR
    from sklearn.tree import DecisionTreeRegressor
    from xgboost import XGBRegressor

    n = 80 if quick else 300
    return {
        "Ridge": ("linear", lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0))),
        "Lasso": ("linear", lambda: make_pipeline(StandardScaler(), Lasso(alpha=0.002, max_iter=5000))),
        "KNN": ("instance", lambda: make_pipeline(StandardScaler(), KNeighborsRegressor(n_neighbors=15, weights="distance"))),
        "SVR": ("kernel", lambda: make_pipeline(StandardScaler(), SVR(C=1.0, epsilon=0.02, gamma="scale"))),
        "DecisionTree": ("tree", lambda: DecisionTreeRegressor(max_depth=8, min_samples_leaf=10, random_state=0)),
        "RandomForest": ("tree ensemble", lambda: RandomForestRegressor(n_estimators=n, min_samples_leaf=3, max_features=0.5, n_jobs=-1, random_state=0)),
        "ExtraTrees": ("tree ensemble", lambda: ExtraTreesRegressor(n_estimators=n, min_samples_leaf=3, max_features=0.5, n_jobs=-1, random_state=0)),
        "HistGradientBoosting": ("boosting", lambda: HistGradientBoostingRegressor(max_iter=n, learning_rate=0.05, random_state=0)),
        "XGBoost": ("boosting", lambda: XGBRegressor(n_estimators=n * 2, learning_rate=0.03, max_depth=5, subsample=0.8, colsample_bytree=0.7, n_jobs=4, random_state=0, verbosity=0)),
        "LightGBM": ("boosting", lambda: LGBMRegressor(n_estimators=n * 2, learning_rate=0.03, num_leaves=24, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, random_state=0, verbose=-1)),
        "CatBoost": ("boosting", lambda: CatBoostRegressor(iterations=n * 2, learning_rate=0.05, depth=6, random_seed=0, verbose=0, thread_count=4, allow_writing_files=False)),
        "MLP (sklearn)": ("neural", lambda: make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(64, 32), early_stopping=True, max_iter=300, random_state=0))),
    }


def run_tabular(X, Y, masks, quick):
    preds = {}
    for name, (family, make) in tabular_models(quick).items():
        t0 = time.time()
        cols = {}
        for h in HORIZONS:
            m = make()
            m.fit(X[masks["train"]], Y.loc[masks["train"], f"h{h}"])
            cols[h] = m.predict(X[masks["test"]])
        preds[name] = (family, cols)
        print(f"    {name:22s} {time.time() - t0:5.1f}s", flush=True)
    return preds


def arima_forecasts(lq, origins, quick):
    """ARIMA(2,1,2) on log discharge: parameters fitted once on the training years, then each test origin is forecast from its own
    recent history (last 400 days) with those fixed parameters."""
    from statsmodels.tsa.arima.model import ARIMA

    arr = lq.to_numpy()
    fit = ARIMA(arr[max(0, origins[0] - 3500): origins[0] - 8], order=(2, 1, 2)).fit()      # fitted only on days before the test years
    out = {h: [] for h in HORIZONS}
    for o in origins:
        r = ARIMA(arr[o - 399: o + 1], order=(2, 1, 2)).smooth(fit.params)
        f = r.forecast(max(HORIZONS))
        for h in HORIZONS:
            out[h].append(f[h - 1])
    return {h: np.array(v) for h, v in out.items()}


def chronos_forecasts(lq, origins, quick, size="tiny"):
    import torch
    from chronos import ChronosPipeline

    pipe = ChronosPipeline.from_pretrained(f"amazon/chronos-t5-{size}", device_map="cpu", torch_dtype=torch.float32)
    ctx = [torch.tensor(lq.to_numpy()[o - 127: o + 1], dtype=torch.float32) for o in origins]
    out = {h: [] for h in HORIZONS}
    for i in range(0, len(ctx), 32):
        f = pipe.predict(ctx[i:i + 32], prediction_length=max(HORIZONS), num_samples=10 if quick else 20)
        med = f.median(dim=1).values.numpy()
        for h in HORIZONS:
            out[h].extend(med[:, h - 1])
    return {h: np.array(v) for h, v in out.items()}


# ---- neural networks (PyTorch) ----------------------------------------------------------------------------------

def torch_models():
    import torch
    from torch import nn

    class Head(nn.Module):
        def __init__(self, d, out):
            super().__init__()
            self.net = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Dropout(0.1), nn.Linear(64, out))

        def forward(self, x):
            return self.net(x)

    class LSTM(nn.Module):
        def __init__(self, f, out):
            super().__init__()
            self.rnn, self.head = nn.LSTM(f, 64, batch_first=True), Head(64, out)

        def forward(self, x):
            return self.head(self.rnn(x)[0][:, -1])

    class GRU(nn.Module):
        def __init__(self, f, out):
            super().__init__()
            self.rnn, self.head = nn.GRU(f, 64, batch_first=True), Head(64, out)

        def forward(self, x):
            return self.head(self.rnn(x)[0][:, -1])

    class CNN(nn.Module):
        def __init__(self, f, out):
            super().__init__()
            self.c = nn.Sequential(nn.Conv1d(f, 32, 3, padding=1), nn.ReLU(), nn.Conv1d(32, 32, 3, padding=2, dilation=2), nn.ReLU(),
                                   nn.Conv1d(32, 32, 3, padding=4, dilation=4), nn.ReLU(), nn.AdaptiveAvgPool1d(1))
            self.head = Head(32, out)

        def forward(self, x):
            return self.head(self.c(x.transpose(1, 2)).squeeze(-1))

    class DLinear(nn.Module):
        """Trend (moving average) and remainder, each with its own linear map over the window."""
        def __init__(self, f, out):
            super().__init__()
            self.k = 7
            self.trend, self.rest = nn.Linear(WINDOW * f, out), nn.Linear(WINDOW * f, out)

        def forward(self, x):
            pad = torch.cat([x[:, :1].repeat(1, self.k // 2, 1), x, x[:, -1:].repeat(1, self.k // 2, 1)], 1)
            tr = pad.unfold(1, self.k, 1).mean(-1)
            return self.trend(tr.flatten(1)) + self.rest((x - tr).flatten(1))

    class Transformer(nn.Module):
        def __init__(self, f, out):
            super().__init__()
            self.inp, self.pos = nn.Linear(f, 32), nn.Parameter(torch.randn(1, WINDOW, 32) * 0.02)
            self.enc = nn.TransformerEncoder(nn.TransformerEncoderLayer(32, 4, 64, 0.1, batch_first=True), 2)
            self.head = Head(32, out)

        def forward(self, x):
            return self.head(self.enc(self.inp(x) + self.pos).mean(1))

    class PatchTST(nn.Module):
        """Patches of 5 days become tokens (as in PatchTST), then a Transformer encoder."""
        def __init__(self, f, out):
            super().__init__()
            self.p = 5
            self.emb = nn.Linear(f * self.p, 32)
            self.pos = nn.Parameter(torch.randn(1, WINDOW // self.p, 32) * 0.02)
            self.enc = nn.TransformerEncoder(nn.TransformerEncoderLayer(32, 4, 64, 0.1, batch_first=True), 2)
            self.head = Head(32 * (WINDOW // self.p), out)

        def forward(self, x):
            b = x.shape[0]
            tok = self.emb(x.reshape(b, WINDOW // self.p, -1)) + self.pos
            return self.head(self.enc(tok).flatten(1))

    class MLPW(nn.Module):
        def __init__(self, f, out):
            super().__init__()
            self.net = nn.Sequential(nn.Flatten(), nn.Linear(WINDOW * f, 128), nn.ReLU(), nn.Dropout(0.1), nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, out))

        def forward(self, x):
            return self.net(x)

    return {"LSTM": ("recurrent", LSTM), "GRU": ("recurrent", GRU), "CNN-1D (dilated)": ("convolutional", CNN), "DLinear": ("linear", DLinear),
            "Transformer": ("transformer", Transformer), "PatchTST-style": ("transformer", PatchTST), "MLP (window)": ("neural", MLPW)}


def run_torch(df, Y, masks, seeds, quick):
    import torch
    from torch import nn

    lq = np.log1p(df["q"]).to_numpy()
    doy = df["date"].dt.dayofyear.to_numpy()
    feats = np.column_stack([lq, np.log1p(df["rain"].to_numpy()), np.log1p(df["rain_up"].to_numpy()),
                             np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)]).astype(np.float32)
    mu, sd = feats[masks["train"]].mean(0), feats[masks["train"]].std(0) + 1e-6
    feats = (feats - mu) / sd

    def windows(mask):
        idx = np.where(mask)[0]
        return torch.tensor(np.stack([feats[i - WINDOW + 1: i + 1] for i in idx]))

    Yv = Y.to_numpy(np.float32)
    ymu, ysd = Yv[masks["train"]].mean(0), Yv[masks["train"]].std(0) + 1e-6
    tr_x, va_x, te_x = windows(masks["train"]), windows(masks["val"]), windows(masks["test"])
    tr_y, va_y = torch.tensor((Yv[masks["train"]] - ymu) / ysd), torch.tensor((Yv[masks["val"]] - ymu) / ysd)
    out = {}
    for name, (family, cls) in torch_models().items():
        t0 = time.time()
        per_seed = []
        for seed in range(seeds):
            torch.manual_seed(seed)
            np.random.seed(seed)
            net = cls(feats.shape[1], len(HORIZONS))
            opt = torch.optim.Adam(net.parameters(), lr=2e-3, weight_decay=1e-5)
            best, best_state, bad = 1e9, None, 0
            for epoch in range(25 if quick else 80):
                net.train()
                perm = torch.randperm(len(tr_x))
                for i in range(0, len(perm), 128):
                    b = perm[i:i + 128]
                    opt.zero_grad()
                    nn.functional.mse_loss(net(tr_x[b]), tr_y[b]).backward()
                    opt.step()
                net.eval()
                with torch.no_grad():
                    v = nn.functional.mse_loss(net(va_x), va_y).item()
                if v < best - 1e-5:
                    best, bad = v, 0
                    best_state = {k: t.clone() for k, t in net.state_dict().items()}
                else:
                    bad += 1
                    if bad >= 10:
                        break
            net.load_state_dict(best_state)
            net.eval()
            with torch.no_grad():
                p = net(te_x).numpy() * ysd + ymu
            per_seed.append({h: p[:, k] for k, h in enumerate(HORIZONS)})
        out[name] = (family, per_seed)
        print(f"    {name:22s} {time.time() - t0:5.1f}s  ({seeds} seeds, best val {best:.3f})", flush=True)
    return out


# ---------------------------------------------------------------------------------------------------------------
# one site

def run_site(key: str, seeds: int, quick: bool, skip: set[str]) -> pd.DataFrame:
    print(f"== {SITES[key]['name']}", flush=True)
    df = load(key)
    X, Y, aux = build(df, "full")
    masks = split_masks(df, X, Y)
    lq, clim = aux["lq"], aux["clim"]
    q_train = df["q"][masks["train"]]
    thr_event, thr_high = float(q_train.quantile(0.95)), float(q_train.quantile(0.90))
    test_idx = np.where(masks["test"])[0]
    print(f"  {len(df)} days | train {masks['train'].sum()} val {masks['val'].sum()} test origins {len(test_idx)} | event threshold {thr_event:.0f} m3/s", flush=True)
    today = lq.to_numpy()[test_idx]
    clim_t = clim.to_numpy()
    results, store = [], {}

    def add(model, family, seed, cols):
        for h in HORIZONS:
            tgt = test_idx + h
            q_true = df["q"].to_numpy()[tgt]
            q_hat = np.expm1(cols[h])
            month = df["date"].dt.month.to_numpy()[tgt]
            r = score(q_true, q_hat, np.expm1(today), thr_event, thr_high, (month >= 6) & (month <= 9))
            results.append({"site": key, "horizon": h, "model": model, "family": family, "seed": seed, **r})
            if seed == 0:
                store[(model, h)] = q_hat

    persist = {h: today for h in HORIZONS}
    add("Persistence", "baseline", 0, persist)
    add("Seasonal climatology", "baseline", 0, {h: clim_t[test_idx + h] for h in HORIZONS})
    add("7-day moving average", "baseline", 0, {h: X["lq_mean7"].to_numpy()[test_idx] for h in HORIZONS})
    delta = lambda cols: {h: today + cols[h] for h in HORIZONS}                           # noqa: E731
    if "tabular" not in skip:
        for name, (family, cols) in run_tabular(X, Y, masks, quick).items():
            add(name, family, 0, delta(cols))
    if "arima" not in skip:
        t0 = time.time()
        add("ARIMA(2,1,2)", "statistical", 0, arima_forecasts(lq, test_idx, quick))
        print(f"    {'ARIMA(2,1,2)':22s} {time.time() - t0:5.1f}s", flush=True)
    if "chronos" not in skip:
        try:
            t0 = time.time()
            add("Chronos (pretrained, zero-shot)", "foundation transformer", 0, chronos_forecasts(lq, test_idx, quick))
            print(f"    {'Chronos':22s} {time.time() - t0:5.1f}s", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"    Chronos skipped: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
    if "torch" not in skip:
        for name, (family, per_seed) in run_torch(df, Y, masks, seeds, quick).items():
            for s, cols in enumerate(per_seed):
                add(name, family, s, delta(cols))
    OUT.mkdir(parents=True, exist_ok=True)
    res = pd.DataFrame(results)
    res.to_csv(OUT / f"{key}.csv", index=False)
    dates = df["date"].to_numpy()
    np.savez_compressed(OUT / f"{key}_predictions.npz", origin_dates=dates[test_idx],
                        **{f"{m}|{h}": v for (m, h), v in store.items()},
                        **{f"truth|{h}": df["q"].to_numpy()[test_idx + h] for h in HORIZONS})
    return res


# ---------------------------------------------------------------------------------------------------------------

def cmd_fetch(args):
    RAW.mkdir(parents=True, exist_ok=True)
    for key in (SITES if args.sites == "all" else args.sites.split(",")):
        df = fetch_site(key)
        df.to_csv(RAW / f"{key}.csv", index=False)
        print(f"{key}: {len(df)} days, discharge {df['q'].notna().sum()} days, {df['q'].min():.0f}-{df['q'].max():.0f} m3/s")


def cmd_run(args):
    keys = list(SITES) if args.sites == "all" else args.sites.split(",")
    skip = set(args.skip.split(",")) if args.skip else set()
    for key in keys:
        run_site(key, args.seeds, args.quick, skip)


def md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    cols = list(df.columns)
    rows = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        rows.append("| " + " | ".join(floatfmt.format(v) if isinstance(v, float) and v == v else ("n/a" if isinstance(v, float) else str(v)) for v in r) + " |")
    return "\n".join(rows)


def cmd_report(args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    files = [f for f in sorted(OUT.glob("*.csv"))]
    allr = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    allr.to_csv(OUT.parent / "results_all_seeds.csv", index=False)
    num = [c for c in allr.columns if c not in ("site", "horizon", "model", "family", "seed")]
    agg = allr.groupby(["site", "horizon", "model", "family"], as_index=False)[num].mean()
    std = allr.groupby(["site", "horizon", "model"], as_index=False)["NSE"].std().rename(columns={"NSE": "NSE_seed_std"})
    agg = agg.merge(std, on=["site", "horizon", "model"], how="left")
    agg.to_csv(OUT.parent / "results_summary.csv", index=False)
    FIG.mkdir(parents=True, exist_ok=True)
    sites = [k for k in SITES if k in set(agg["site"])]

    # overall ranking per horizon (mean over sites)
    rank = agg.groupby(["horizon", "model", "family"], as_index=False)[["NSE", "NSE_log", "MAE", "MAPE", "skill_vs_persistence", "event_f1", "event_recall", "NSE_high_flow", "NSE_monsoon", "NSE_dry_season"]].mean()
    wins = agg.loc[agg.groupby(["site", "horizon"])["NSE"].idxmax()].groupby(["horizon", "model"]).size().rename("sites_won").reset_index()
    rank = rank.merge(wins, on=["horizon", "model"], how="left").fillna({"sites_won": 0})
    rank["sites_won"] = rank["sites_won"].astype(int)
    rank.to_csv(OUT.parent / "ranking.csv", index=False)

    # figure: heatmaps of NSE
    fig, axes = plt.subplots(1, 3, figsize=(17, 9), sharey=True)
    order = rank[rank["horizon"] == 3].sort_values("NSE", ascending=False)["model"].tolist()
    for ax, h in zip(axes, HORIZONS):
        piv = agg[agg["horizon"] == h].pivot(index="model", columns="site", values="NSE").reindex(order)[sites]
        im = ax.imshow(piv.clip(lower=-0.5).to_numpy(), cmap="RdYlGn", vmin=-0.5, vmax=1, aspect="auto")
        ax.set_xticks(range(len(sites)), [SITES[k]["name"].split(",")[0] for k in sites], rotation=30, ha="right")
        ax.set_title(f"{h}-day ahead: NSE")
        for i in range(piv.shape[0]):
            for j in range(piv.shape[1]):
                v = piv.iloc[i, j]
                ax.text(j, i, "n/a" if v != v else f"{v:.2f}", ha="center", va="center", fontsize=7)
    axes[0].set_yticks(range(len(order)), order, fontsize=8)
    fig.colorbar(im, ax=axes, shrink=0.6, label="NSE (1 = perfect)")
    fig.savefig(FIG / "forecast_benchmark_heatmap.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    # figure: a real flood, truth against the best models and persistence
    f = OUT / "sunamganj_bd_predictions.npz"
    if f.exists():
        d = np.load(f, allow_pickle=True)
        dates = pd.to_datetime(d["origin_dates"])
        h = 7
        best = rank[rank["horizon"] == h].sort_values("NSE", ascending=False)["model"].tolist()
        picks = [m for m in best if m != "Persistence"][:3]
        fig, axes = plt.subplots(1, 2, figsize=(15, 4.2))
        for ax, (a, b, title) in zip(axes, (("2022-05-15", "2022-08-31", "2022 flood"), ("2024-05-15", "2024-08-31", "2024 flood"))):
            sel = (dates >= a) & (dates <= b)
            x = dates[sel] + pd.Timedelta(days=h)
            ax.plot(x, d[f"truth|{h}"][sel], "k-", lw=2.2, label="observed (GloFAS reanalysis)")
            ax.plot(x, d[f"Persistence|{h}"][sel], "--", color="grey", label="persistence")
            for m in picks:
                if f"{m}|{h}" in d:
                    ax.plot(x, d[f"{m}|{h}"][sel], lw=1.4, label=m)
            ax.set_title(f"Sunamganj {title}: discharge, predicted {h} days ahead")
            ax.set_ylabel("m3/s")
            ax.legend(fontsize=7)
        fig.savefig(FIG / "forecast_benchmark_floods.png", dpi=130, bbox_inches="tight")
        plt.close(fig)

    # markdown report
    out = ["# Which prediction algorithm is most correct for river flow? (benchmark)", "",
           "Generated by `python scripts/benchmark_forecasts.py report`. Every model sees the same features and is scored on the same test days.", "",
           "## What was tested", "",
           "* **Data (free APIs):** daily river discharge (Open-Meteo Flood API, GloFAS reanalysis, **a modelled series, not a gauge**), rain at the site and at an approximate upstream point (Open-Meteo archive, ERA5), and NASA POWER rain (IMERG-based) for the feature test.",
           f"* **Sites:** {'; '.join(SITES[k]['name'] for k in sites)}.",
           "* **Split by time:** train 1997-2016, validation 2017-2019, **test 2020-2025** (includes the real 2020, 2022 and 2024 floods). The last 7 days of each block are dropped so no target leaks across blocks. Every 3rd test day is an origin (the same for every model).",
           "* **Task:** from the end of day *t*, predict discharge at *t*+1, *t*+3 and *t*+7. Learned models predict the change in log discharge from today and add it back.",
           "* **Scores:** NSE (1 = perfect, 0 = no better than always guessing the test-period mean; the standard in hydrology), MAE, skill against persistence (positive = beats \"tomorrow is like today\"), and flood-event detection (discharge above the training 95th percentile).", ""]
    for h in HORIZONS:
        t = rank[rank["horizon"] == h].sort_values("NSE", ascending=False).head(12)[["model", "family", "NSE", "skill_vs_persistence", "MAE", "MAPE", "event_f1", "NSE_high_flow", "sites_won"]]
        t = t.rename(columns={"skill_vs_persistence": "skill vs persistence", "MAPE": "MAPE %", "event_f1": "flood-event F1", "NSE_high_flow": "NSE at high flow", "sites_won": "sites won"})
        out += [f"## {h}-day-ahead: top 12 of {rank[rank['horizon'] == h].shape[0]} (mean over {len(sites)} sites)", "", md_table(t), ""]
    fam = agg.groupby(["horizon", "family"], as_index=False)["NSE"].mean().pivot(index="family", columns="horizon", values="NSE").reset_index()
    fam.columns = ["family"] + [f"NSE {h}-day" for h in fam.columns[1:]]
    out += ["## By family of method (mean NSE over models and sites)", "", md_table(fam.sort_values(fam.columns[-1], ascending=False)), ""]
    bests = agg.loc[agg.groupby(["site", "horizon"])["NSE"].idxmax()][["site", "horizon", "model", "NSE", "event_f1"]]
    bests["site"] = bests["site"].map(lambda k: SITES[k]["name"])
    out += ["## Best model for each site and horizon", "", md_table(bests.sort_values(["site", "horizon"])), ""]
    sea = agg[agg["horizon"] == 7].groupby("model", as_index=False)[["NSE_monsoon", "NSE_dry_season", "NSE_high_flow", "event_recall"]].mean().sort_values("NSE_monsoon", ascending=False).head(10)
    out += ["## Where is it correct? Season and flow regime (7-day ahead, mean over sites, top 10)", "", md_table(sea), "",
            "![heatmap](figures/forecast_benchmark_heatmap.png)", "", "![floods](figures/forecast_benchmark_floods.png)", ""]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "FORECAST_BENCHMARK.md").write_text("\n".join(out), encoding="utf-8")
    print("wrote docs/FORECAST_BENCHMARK.md, ranking.csv, results_summary.csv and two figures")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--sites", default="all")
    f.set_defaults(fn=cmd_fetch)
    r = sub.add_parser("run")
    r.add_argument("--sites", default="all")
    r.add_argument("--seeds", type=int, default=3)
    r.add_argument("--quick", action="store_true", help="fewer trees and epochs, for a smoke test")
    r.add_argument("--skip", default="", help="comma list of: tabular, arima, chronos, torch")
    r.set_defaults(fn=cmd_run)
    rp = sub.add_parser("report")
    rp.set_defaults(fn=cmd_report)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
