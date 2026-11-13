"""Where could relief stock have been placed before a flood? Learned on one flood, tested on a later one.

    python scripts/relief_prepositioning.py                                  # 2022 -> 2024 Sunamganj
    python scripts/relief_prepositioning.py --train data/live --test data/sunamganj_2024 --k 3 --radius-km 5

1. Training flood only: the villages it isolated (people as weight) and its shelter candidates (unverified).
   Greedy choice of up to k candidates covering the most of those people within radius_km (straight line).
2. Test flood: how many of the villages *it* isolated, and their people, those same sites cover.
   Yardsticks: k sites picked at random (average over every combination), and the best any k sites could do
   with hindsight. Also the same for other radii.

Straight line, not roads: an isolated village by definition has no open road to any shelter, so stock must move
into the villages before the roads close (the "last seen passable" dates are listed), or by boat, which the
model does not know. Writes <test>/results/relief_prepositioning.json and .csv. An analysis, not a decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from safewindow.prepositioning import best_possible, covered, distance_km, greedy_sites, random_mean  # noqa: E402


def _date(v):
    return None if pd.isna(v) else pd.to_datetime(v).strftime("%Y-%m-%d")


def flood_id(pkg: Path) -> str:
    return json.loads((pkg / "app" / "meta.json").read_text(encoding="utf-8")).get("region") or pkg.name


def isolated(pkg: Path) -> gpd.GeoDataFrame:
    v = gpd.read_file(pkg / "app" / "villages.geojson").to_crs(4326)
    v["village_id"] = v["village_id"].astype(str)
    return v[v["outcome"] == "isolated"].reset_index(drop=True)


def candidates(pkg: Path) -> pd.DataFrame:
    s = pd.read_csv(pkg / "results" / "shelters_snapped.csv", dtype={"shelter_id": str})
    return s[s["road_reachable"].astype(bool)].reset_index(drop=True)


def run(train: Path, test: Path, k: int, radius_km: float, radii: list[float]) -> dict:
    tr, te, sites = isolated(train), isolated(test), candidates(train)
    d_tr = distance_km(sites["lat"], sites["lon"], tr.geometry.y, tr.geometry.x)
    d_te = distance_km(sites["lat"], sites["lon"], te.geometry.y, te.geometry.x)
    w_tr, w_te = tr["population"].fillna(0).to_numpy(), te["population"].fillna(0).to_numpy()

    chosen = greedy_sites(d_tr, w_tr, k, radius_km)
    hit = covered(d_te, chosen, radius_km)
    nearest = d_te[chosen].min(axis=0) if chosen else np.full(len(te), np.nan)

    sens = []
    for r in radii:
        c = greedy_sites(d_tr, w_tr, k, r)
        sens.append({"radius_km": r, "sites": len(c),
                     "test_people_covered": int(w_te[covered(d_te, c, r)].sum()),
                     "random_mean_people": round(random_mean(d_te, w_te, k, r)),
                     "best_possible_people": best_possible(d_te, w_te, k, r)})

    same = set(tr["village_id"]) == set(te["village_id"])
    return {
        "train_flood": flood_id(train), "test_flood": flood_id(test), "k": k, "radius_km": radius_km,
        "method": "greedy max coverage of the training flood's isolated people, straight-line radius",
        "sites": [{"shelter_id": sites.loc[s, "shelter_id"], "name": sites.loc[s, "name"], "type": sites.loc[s, "type"],
                   "lat": round(float(sites.loc[s, "lat"]), 5), "lon": round(float(sites.loc[s, "lon"]), 5),
                   "verified": False,
                   "train_villages": tr.loc[d_tr[s] <= radius_km, "village_id"].tolist()} for s in chosen],
        "train": {"villages": len(tr), "people": int(w_tr.sum()), "village_ids": tr["village_id"].tolist()},
        "test": {
            "villages": len(te), "people": int(w_te.sum()),
            "covered_villages": int(hit.sum()), "covered_people": int(w_te[hit].sum()),
            "random_mean_people": round(random_mean(d_te, w_te, k, radius_km)),
            "best_possible_people": best_possible(d_te, w_te, k, radius_km),
            "same_villages_as_train": same,
            "village_rows": [{"village_id": r.village_id, "name": r.name,
                              "name_bn": None if pd.isna(r.name_bn) else r.name_bn,
                              "population": int(r.population or 0), "covered": bool(h),
                              "nearest_site_km": None if np.isnan(n) else round(float(n), 1),
                              "last_connected": _date(r.last_connected), "first_isolated": _date(r.first_isolated)}
                             for r, h, n in zip(te.itertuples(), hit, nearest)],
        },
        "sensitivity": sens,
        "notes": [
            "Sites are unverified OpenStreetMap shelter candidates.",
            "Straight-line distance: during the flood no open road joins an isolated village to any shelter.",
            "Stock would have to move before the village's last-seen-passable date, or by boat (not modelled).",
            "If the test flood isolates the same villages as the training flood, the test shows that isolation "
            "recurs; it is not an independent test of the method.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=Path, default=ROOT / "data" / "live")
    ap.add_argument("--test", type=Path, default=ROOT / "data" / "sunamganj_2024")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--radius-km", type=float, default=5.0)
    ap.add_argument("--radii", type=float, nargs="*", default=[3.0, 5.0, 10.0])
    a = ap.parse_args()
    res = run(a.train, a.test, a.k, a.radius_km, a.radii)
    out = a.test / "results"
    (out / "relief_prepositioning.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame(res["sensitivity"]).to_csv(out / "relief_prepositioning.csv", index=False)
    t = res["test"]
    print(f"train {res['train_flood']}: {res['train']['villages']} isolated villages, {res['train']['people']:,} people")
    print(f"sites chosen: {len(res['sites'])} -> {[s['shelter_id'] for s in res['sites']]}")
    print(f"test {res['test_flood']}: covered {t['covered_villages']}/{t['villages']} villages, "
          f"{t['covered_people']:,}/{t['people']:,} people; random {t['random_mean_people']:,}; "
          f"best possible {t['best_possible_people']}; same villages as training: {t['same_villages_as_train']}")
    for s in res["sensitivity"]:
        print(f"   radius {s['radius_km']:>4} km: {s['test_people_covered']:,} people (random {s['random_mean_people']:,}, "
              f"best {s['best_possible_people']})")


if __name__ == "__main__":
    main()
