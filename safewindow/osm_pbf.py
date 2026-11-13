"""Shelter and health candidates from an OpenStreetMap country extract (a .osm.pbf file), with no Overpass server.

Overpass can be down or blocking. A Geofabrik extract (https://download.geofabrik.de, ODbL) is a plain download that
contains the same data. The results have the same shape as the Overpass ones, so the rest of the pipeline is unchanged.
Everything here is a candidate: OpenStreetMap is incomplete and nothing is verified.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from safewindow import health
from safewindow.places import SHELTER_COLS

KEYS = ("amenity", "healthcare", "building", "emergency", "social_facility", "office")
AMENITY = {"school", "college", "university", "hospital", "clinic", "doctors", "townhall", "shelter", "community_centre"}
BUILDING = {"school", "hospital"}
# Same selection as SHELTER_TAGS in pipeline/03_osm_roads_places.py (healthcare=* matches any value).


def wanted(tags: dict) -> bool:
    return (tags.get("amenity") in AMENITY or "healthcare" in tags or tags.get("building") in BUILDING
            or tags.get("emergency") == "assembly_point" or tags.get("social_facility") == "shelter"
            or tags.get("office") == "government")


def elements(pbf: Path, bbox: tuple[float, float, float, float]) -> list[dict]:
    """Matching nodes and ways inside bbox (west, south, east, north), as Overpass-style dicts with a `center`."""
    import osmium
    west, south, east, north = bbox
    out = []
    proc = osmium.FileProcessor(str(pbf), osmium.osm.NODE | osmium.osm.WAY).with_locations() \
        .with_filter(osmium.filter.KeyFilter(*KEYS))
    for o in proc:
        tags = {t.k: t.v for t in o.tags}
        if not wanted(tags):
            continue
        if o.is_node():
            if not o.location.valid():
                continue
            lat, lon = o.location.lat, o.location.lon
            kind = "node"
        else:
            pts = [(n.lat, n.lon) for n in o.nodes if n.location.valid()]
            if not pts:
                continue
            lat, lon = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            kind = "way"
        if west <= lon <= east and south <= lat <= north:
            out.append({"type": kind, "id": o.id, "center": {"lat": lat, "lon": lon}, "tags": tags})
    return out


def shelter_frame(elems: list[dict]) -> pd.DataFrame:
    """The rows of shelters_candidates.csv, in the same layout pipeline step 3 writes."""
    rows = []
    for e in elems:
        t = e["tags"]
        kind = ""
        for col in KEYS:
            v = t.get(col, "")
            if v and not kind:
                kind = col if v == "yes" else v
        rows.append({"shelter_id": f"osm{e['id']}", "name": t.get("name") or "(unnamed)", "type": kind,
                     "lat": round(e["center"]["lat"], 6), "lon": round(e["center"]["lon"], 6),
                     "source": "OpenStreetMap", "verified": "", "notes": ""})
    return pd.DataFrame(rows, columns=SHELTER_COLS)


def health_fetch(pbf: Path):
    """A `fetch(bbox)` for health.build that reads the extract instead of calling Overpass."""
    def fetch(bbox):
        elems = [e for e in elements(pbf, bbox)
                 if e["tags"].get("amenity") in ("hospital", "clinic", "doctors")
                 or e["tags"].get("healthcare") in ("hospital", "clinic", "doctor", "centre", "health_post")]
        return health.from_osm(elems)
    return fetch


def bridges(pbf: Path, bbox: tuple[float, float, float, float]) -> list[dict]:
    """Road ways tagged bridge=* (not bridge=no) with any node inside bbox: {id, tags, coords [(lon, lat), ...]}."""
    import osmium
    west, south, east, north = bbox
    out = []
    proc = osmium.FileProcessor(str(pbf), osmium.osm.NODE | osmium.osm.WAY).with_locations() \
        .with_filter(osmium.filter.KeyFilter("bridge"))
    for o in proc:
        if not o.is_way():
            continue
        tags = {t.k: t.v for t in o.tags}
        if "highway" not in tags or tags.get("bridge") == "no":
            continue
        coords = [(n.lon, n.lat) for n in o.nodes if n.location.valid()]
        if len(coords) >= 2 and any(west <= x <= east and south <= y <= north for x, y in coords):
            out.append({"id": o.id, "tags": tags, "coords": coords})
    return out
