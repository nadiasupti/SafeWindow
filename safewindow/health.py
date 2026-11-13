"""Hospitals and clinics for the evacuation cards.

A flood package can carry `health.geojson`, written from the first source that has data:
  1. a local list named in the region file (`health_csv`: name, lat, lon, optional type),
  2. OpenStreetMap (hospitals, clinics, doctors, health posts) inside the study area,
  3. the hospital and clinic entries already in the shelter list.
Everything is a candidate: OpenStreetMap is incomplete and nothing here is verified.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

HEALTH_TYPES = {"hospital", "clinic", "doctors", "doctor", "health_post", "health_centre", "centre",
                "community_clinic", "healthcare"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
RETRY_STATUS = {429, 502, 503, 504}


def query(bbox: tuple[float, float, float, float]) -> str:
    west, south, east, north = bbox
    box = f"({south},{west},{north},{east})"
    return ('[out:json][timeout:120];('
            f'nwr["amenity"~"^(hospital|clinic|doctors)$"]{box};'
            f'nwr["healthcare"~"^(hospital|clinic|doctor|centre|health_post)$"]{box};'
            ');out center tags;')


def fetch_osm(bbox, post=None, sleep=time.sleep, waits=(20, 60, 120)) -> list[dict]:
    """Facilities from Overpass. Waits out an overloaded server and tries each mirror in turn."""
    if post is None:
        import requests
        post = requests.post
    last = "no attempt made"
    for wait in (0, *waits):
        for url in OVERPASS:
            if wait:
                sleep(wait)
                wait = 0                      # wait once per round, not once per mirror
            try:
                r = post(url, data={"data": query(bbox)}, timeout=180)
            except Exception as exc:          # network trouble: try the next mirror
                last = str(exc)[:80]
                continue
            if r.status_code == 200:
                return from_osm(r.json().get("elements", []))
            last = f"HTTP {r.status_code}"
            if r.status_code not in RETRY_STATUS:       # a bad query will not get better by waiting
                raise RuntimeError(f"Overpass rejected the request: {last}")
    raise RuntimeError(f"Overpass did not answer: {last}")


def from_osm(elements: list[dict]) -> list[dict]:
    out = []
    for e in elements:
        tags = e.get("tags", {})
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        kind = tags.get("amenity") or tags.get("healthcare") or "clinic"
        name = tags.get("name:en") or tags.get("name") or f"{kind.replace('_', ' ').title()} (unnamed)"
        out.append({"name": name, "type": kind, "lat": float(lat), "lon": float(lon), "source": "osm"})
    return out


def from_csv(path: Path) -> list[dict]:
    df = pd.read_csv(path, encoding="utf-8-sig")
    missing = {"name", "lat", "lon"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} needs the columns name, lat, lon (missing {sorted(missing)})")
    return [{"name": str(r["name"]), "type": str(r.get("type", "clinic")), "lat": float(r["lat"]),
             "lon": float(r["lon"]), "source": "local list"} for _, r in df.iterrows()]


def from_shelters(shelters) -> list[dict]:
    return [{"name": str(s.name), "type": str(s.type), "lat": s.geometry.y, "lon": s.geometry.x, "source": "shelter list"}
            for s in shelters.itertuples() if str(getattr(s, "type", "")).lower() in HEALTH_TYPES]


def build(app_dir: Path, region, shelters=None, bbox=None, fetch=fetch_osm) -> dict:
    """Write health.geojson into a package. Returns {"source": ..., "n": ...}; nothing is written if there is no data."""
    app_dir = Path(app_dir)
    items, source = [], None
    if getattr(region, "health_csv", None):
        items, source = from_csv(region.health_csv), "local list"
    if not items and bbox is not None:
        try:
            items, source = fetch(bbox), "osm"
        except Exception as exc:              # the server may be down: fall through to what we already have
            print(f"  health facilities from OpenStreetMap unavailable ({exc}); using the shelter list")
    if not items and shelters is not None:
        items, source = from_shelters(shelters), "shelter list"
    if not items:
        return {"source": None, "n": 0}
    features = [{"type": "Feature", "properties": {k: v for k, v in i.items() if k not in ("lat", "lon")},
                 "geometry": {"type": "Point", "coordinates": [round(i["lon"], 5), round(i["lat"], 5)]}} for i in items]
    (app_dir / "health.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"source": source, "n": len(items)}


def read(app_dir: Path) -> list[tuple[str, float, float]]:
    """(name, lat, lon) of every facility in a package's health.geojson, or [] if it has none."""
    f = Path(app_dir) / "health.geojson"
    if not f.exists():
        return []
    feats = json.loads(f.read_text(encoding="utf-8")).get("features", [])
    return [(x["properties"]["name"], x["geometry"]["coordinates"][1], x["geometry"]["coordinates"][0]) for x in feats]
