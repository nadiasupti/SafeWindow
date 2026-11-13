"""What NISAR's L-band radar shows around each village that Sentinel-1's C-band does not ("hidden water").

L-band (about 24 cm) passes between plants and reaches the water below; C-band (about 6 cm) stops more at the leaves.
So where NISAR sees water and Sentinel-1 does not, the likeliest cause is water under vegetation: paddies flooded for
transplanting, or flooded grass and reeds. This module only MEASURES that gap around each village. It does not say which
of those causes it is (no field data), and it does not make a new class.

Inputs are files the NISAR step already writes (scripts/nisar_polarization.py): per date a water map for NISAR HH, HV and
the closest Sentinel-1 pass (blue = water, grey = no data or frame edge), and nisar.json with their bounds.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from safewindow.watch import share_around

RADIUS_KM = 3.0
MAX_UNKNOWN = 0.5
WATER = (30, 110, 230)


def load_water(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """(water, unknown) from one of the water PNGs: blue = water; grey with some transparency = no data / frame edge."""
    px = np.array(Image.open(path).convert("RGBA"))
    water = (px[..., 3] == 255) & (abs(px[..., 0].astype(int) - WATER[0]) < 4) & (abs(px[..., 2].astype(int) - WATER[2]) < 4)
    unknown = (px[..., 3] < 255) & (px[..., 0] == 140)
    return water, unknown


def village_gap(nisar: tuple[np.ndarray, np.ndarray], s1: tuple[np.ndarray, np.ndarray], bounds: list, lat: float, lon: float,
                radius_km: float = RADIUS_KM) -> dict:
    """Water share around one village in NISAR and in Sentinel-1, and the gap (NISAR minus Sentinel-1)."""
    n_share, n_unk = share_around(nisar[0], nisar[1], bounds, lat, lon, radius_km)
    s_share, s_unk = share_around(s1[0], s1[1], bounds, lat, lon, radius_km)
    unknown = max(n_unk, s_unk)
    ok = n_share is not None and s_share is not None and unknown <= MAX_UNKNOWN
    return {"nisar": None if n_share is None else round(n_share, 4), "sentinel1": None if s_share is None else round(s_share, 4),
            "hidden": round(n_share - s_share, 4) if ok else None, "unknown": round(unknown, 3)}


def region_summary(region_dir: Path, villages: list[dict], radius_km: float = RADIUS_KM) -> dict:
    """Per date (that has both a NISAR water map and a Sentinel-1 one): every village's gap. `villages` need
    village_id, name, lat, lon. NISAR HH is used when its map exists, otherwise HV (HH's threshold can fail where HV's does not)."""
    meta = json.loads((region_dir / "nisar.json").read_text(encoding="utf-8"))
    bounds = meta["bounds"]
    out = {"region": meta["region"], "radius_km": radius_km, "dates": []}
    for scene in meta["scenes"]:
        layers = scene["layers"]
        pol = "hh" if "hh_water" in layers else "hv" if "hv_water" in layers else None
        if pol is None or "s1_water" not in layers:
            continue
        nis = load_water(region_dir / layers[f"{pol}_water"])
        s1 = load_water(region_dir / layers["s1_water"])
        rows = {v["village_id"]: {"name": v["name"], "name_bn": v.get("name_bn"), **village_gap(nis, s1, bounds, v["lat"], v["lon"], radius_km)} for v in villages}
        known = [r["hidden"] for r in rows.values() if r["hidden"] is not None]
        out["dates"].append({"date": scene["date"], "polarization": pol.upper(), "sentinel1_date": (scene.get("sentinel1") or {}).get("date"),
                             "villages": rows, "villages_with_a_gap": sum(h >= 0.10 for h in known),
                             "median_hidden": round(float(np.median(known)), 4) if known else None})
    return out


def time_series(region_dir: Path) -> list[dict]:
    """Water area (km2) per NISAR date: HH, HV and the nearest Sentinel-1 pass, straight from nisar.json."""
    meta = json.loads((region_dir / "nisar.json").read_text(encoding="utf-8"))
    rows = []
    for s in meta["scenes"]:
        ok = lambda p: s[p]["water_km2"] if s[p]["status"] == "otsu" else None          # noqa: E731
        rows.append({"date": s["date"], "hh_km2": ok("hh"), "hv_km2": ok("hv"),
                     "s1_km2": (s.get("sentinel1") or {}).get("water_km2"), "s1_date": (s.get("sentinel1") or {}).get("date")})
    return rows
