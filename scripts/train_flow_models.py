"""Train the winning model (Random Forest) for each river on ALL the history and export it as plain arrays for numpy.

    python scripts/train_flow_models.py        # needs the benchmark environment (scikit-learn); data from `benchmark_forecasts.py fetch`

Writes data/forecast/flow/<site>.npz (the forests, climatology, thresholds) and data/forecast/flow/evaluation.json.

Two steps per river:
  1. Honest check: train on 1997-2016 (climatology from those years only), test on 2020-2025 as in the benchmark, with the small
     forest that will be exported and with the full-size benchmark forest. Records NSE and, for the watch's thresholds (site
     discharge quantiles 95 / 97.5 / 99 %), how many floods were caught and how many alarms were false.
  2. Production: train on every year (1997-2025), export, and verify that the numpy forest gives the same numbers as scikit-learn.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_forecasts as bm  # noqa: E402
from safewindow import flowforecast as ff  # noqa: E402

OUT = ROOT / "data" / "forecast" / "flow"
# The 0.05-degree discharge cell of the main river near each site (chosen by `benchmark_forecasts.py fetch`: largest mean flow)
CELLS = {"sunamganj_bd": [24.97, 91.25], "kurigram_bd": [25.65, 89.7], "trimmu_pk": [31.15, 72.05], "bara_np": [27.15, 85.1]}
PARAMS = dict(n_estimators=60, min_samples_leaf=20, max_features=0.5, random_state=0)
QUANT = ff.LEVEL_QUANTILES


def forest_arrays(model) -> dict:
    feats, thr, left, right, val, roots, off = [], [], [], [], [], [], 0
    for est in model.estimators_:
        t = est.tree_
        roots.append(off)
        feats.append(np.where(t.children_left == -1, 0, t.feature).astype(np.int16))
        thr.append(t.threshold.astype(np.float64))
        left.append(np.where(t.children_left == -1, -1, t.children_left + off).astype(np.int32))
        right.append(np.where(t.children_right == -1, -1, t.children_right + off).astype(np.int32))
        val.append(t.value[:, 0, 0].astype(np.float32))
        off += t.node_count
    return dict(feature=np.concatenate(feats), threshold=np.concatenate(thr), left=np.concatenate(left), right=np.concatenate(right),
                value=np.concatenate(val), roots=np.array(roots, np.int32))


def events(q_true, q_hat, thr):
    ev, pr = q_true >= thr, q_hat >= thr
    tp, fp, fn = int((ev & pr).sum()), int((~ev & pr).sum()), int((ev & ~pr).sum())
    return {"events": int(ev.sum()), "alarms": int(pr.sum()), "hits": tp, "false_alarms": fp, "missed": fn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None, "recall": round(tp / (tp + fn), 3) if tp + fn else None}


def evaluate(site: str) -> dict:
    from sklearn.ensemble import RandomForestRegressor

    df = bm.load(site)
    clim = ff.climatology(df, until=bm.TRAIN_END)
    X = ff.build_features(df, clim)
    _, Y, _ = bm.build(df, "full")
    masks = bm.split_masks(df, X, Y)
    thr = {k: float(df["q"][masks["train"]].quantile(v)) for k, v in QUANT.items()}
    test_idx = np.where(masks["test"])[0]
    today = X["lq_l0"].to_numpy()[test_idx]
    out = {"site": site, "test_origins": int(len(test_idx)), "thresholds_m3s": {k: round(v, 1) for k, v in thr.items()}, "horizons": {}}
    for h in ff.HORIZONS:
        q_true = df["q"].to_numpy()[test_idx + h]
        row = {}
        for name, params in (("exported (60 trees, leaf 20)", PARAMS),
                             ("benchmark size (300 trees, leaf 3)", dict(n_estimators=300, min_samples_leaf=3, max_features=0.5, random_state=0))):
            m = RandomForestRegressor(n_jobs=-1, **params).fit(X[masks["train"]], Y.loc[masks["train"], f"h{h}"])
            q_hat = np.expm1(today + m.predict(X[masks["test"]]))
            row[name] = {"NSE": round(bm.nse(q_true, q_hat), 4), "MAE": round(float(np.mean(np.abs(q_true - q_hat))), 1)}
            if name.startswith("exported"):
                row[name]["event_detection"] = {lv: events(q_true, q_hat, thr[lv]) for lv in thr}
        row["persistence"] = {"NSE": round(bm.nse(q_true, np.expm1(today)), 4)}
        out["horizons"][str(h)] = row
    return out


def export(site: str) -> dict:
    from sklearn.ensemble import RandomForestRegressor

    df = bm.load(site)
    clim = ff.climatology(df)
    X = ff.build_features(df, clim)
    _, Y, _ = bm.build(df, "full")
    ok = X.notna().all(axis=1).to_numpy() & Y.notna().all(axis=1).to_numpy() & (np.arange(len(df)) >= bm.WINDOW + 60)
    thresholds = {k: float(df["q"].quantile(v)) for k, v in QUANT.items()}
    arrays, parity, ref = {}, 0.0, {}
    sample = np.random.default_rng(0).choice(np.where(ok)[0], 200, replace=False)
    for h in ff.HORIZONS:
        m = RandomForestRegressor(n_jobs=-1, **PARAMS).fit(X[ok], Y.loc[ok, f"h{h}"])
        a = forest_arrays(m)
        for k, v in a.items():
            arrays[f"h{h}_{k}"] = v
        # numpy forest against scikit-learn on 200 rows
        f = ff.Forest(a["feature"], a["threshold"], a["left"], a["right"], a["value"], a["roots"])
        parity = max(parity, float(np.abs(f.predict(X.iloc[sample].to_numpy(np.float32)) - m.predict(X.iloc[sample])).max()))
        ref[h] = m.predict(X.iloc[sample[:20]]).astype(np.float32)          # scikit-learn's answers for this horizon, kept for the tests
    assert parity < 1e-4, f"numpy forest differs from scikit-learn by {parity}"
    meta = {"site": site, "kind": f"Random Forest ({PARAMS['n_estimators']} trees, min leaf {PARAMS['min_samples_leaf']}) on log-discharge change",
            "columns": list(X.columns), "cell": CELLS[site], "thresholds": thresholds, "quantiles": QUANT,
            "trained_through": str(df["date"].iloc[-1].date()), "trained_days": int(ok.sum()), "params": PARAMS,
            "numpy_vs_sklearn_max_abs_diff": parity, "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "validated_on_gauge_data": False}
    # a few reference rows so the project's tests can check the numpy forest without scikit-learn
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / f"{site}.npz", meta=np.array(json.dumps(meta)), clim=clim, ref_X=X.iloc[sample[:20]].to_numpy(np.float32), **{f"ref_h{h}": v for h, v in ref.items()}, **arrays)
    return meta


def main():
    results = {}
    for site in CELLS:
        print(f"== {site}", flush=True)
        results[site] = evaluate(site)
        meta = export(site)
        size = (OUT / f"{site}.npz").stat().st_size / 1e6
        h3 = results[site]["horizons"]["3"]
        print(f"   3-day NSE exported {h3['exported (60 trees, leaf 20)']['NSE']} | benchmark-size {h3['benchmark size (300 trees, leaf 3)']['NSE']}"
              f" | persistence {h3['persistence']['NSE']} | file {size:.1f} MB | parity {meta['numpy_vs_sklearn_max_abs_diff']:.1e}", flush=True)
    (OUT / "evaluation.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("saved", OUT)


if __name__ == "__main__":
    main()
