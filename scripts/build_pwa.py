"""Export every built flood package into small files for the mobile app (pwa/).

    python scripts/build_pwa.py                       # every data/*/app -> pwa/public/data/
    python scripts/build_pwa.py --out <folder>        # somewhere else

The app reads only these files, so it needs no Python and works offline once
they are cached. Every flood gets the same layout, in a folder named after its
region id (regions/<id>.yaml):

    index.json                     the floods, newest study first
    <region>/metadata.json         name, radar dates, image bounds, times, supply days
    <region>/villages.json         one record per village, with its observed dates
    <region>/status.json           each village's status on each radar date
    <region>/flooded_roads.geojson each possibly flooded road once, with the dates it was flooded
    <region>/routes.geojson        possible routes to a shelter (not checked on the ground)
    <region>/shelters.geojson      shelter candidates (not verified)
    <region>/health.geojson        hospitals and clinics, when the package has them
    <region>/roads.geojson, area.geojson   offline base map
    <region>/flood/YYYYMMDD.png    flood image per radar date
    <region>/critical_roads.geojson  road stretches whose closure alone strands villages (dry network, and the
                                   roads seen open on each radar date, `d`), when road_criticality.py has run
    <region>/critical.json         per village and radar date: 1 = connected but through a single road segment
    <region>/relief.json           pre-positioning sites learned on an earlier flood, scored on this one
                                   (relief_prepositioning.py), when that analysis exists for this flood
    <region>/files.json            every file above, for the app's "download this area" button

Three times are kept apart: the latest radar image (`observed_through`), when
the results were published (`published_at`) and when the system last looked
for new images (`last_checked`, empty until automation exists).

The packages are only read. Nothing in data/ changes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiLineString, mapping, shape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from safewindow import region as regions  # noqa: E402

DEFAULT_OUT = ROOT / "pwa" / "public" / "data"
PRECISION = 5                 # decimal places of a degree: about 1 m
ROAD_SIMPLIFY_DEG = 0.00005   # about 5 m: finer than the 20 m flood pixels
MAX_FLOOD_MB = 5.0            # what a phone should download for one flood
STATUS_CODES = {"connected": "c", "isolated": "i", "uncertain": "u", "boat_dependent": "b"}
VILLAGE_DATES = ("last_connected", "first_isolated", "isolated_from_earliest", "reconnected")


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(c, PRECISION) for c in coords[:2]]
    return [_round(c) for c in coords]


def _geometry(geom) -> dict:
    g = mapping(geom)
    return {"type": g["type"], "coordinates": _round(g["coordinates"])}


def _value(v):
    """JSON-safe: NaN and NaT become null, numpy numbers become Python numbers."""
    if v is None or (not isinstance(v, (list, dict, str)) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return v.item() if hasattr(v, "item") else v


def _features(gdf: gpd.GeoDataFrame, columns: list[str], extra: dict | None = None) -> dict:
    feats = []
    for _, row in gdf.iterrows():
        props = {c: _value(row[c]) for c in columns if c in gdf.columns}
        feats.append({"type": "Feature", "properties": {**props, **(extra or {})}, "geometry": _geometry(row.geometry)})
    return {"type": "FeatureCollection", "features": feats}


def _clean(obj):
    """NaN (e.g. no source on a date whose Otsu test failed) becomes null: browsers cannot parse NaN."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def _write(path: Path, obj) -> None:
    # allow_nan=False: a NaN that slipped through fails here, not silently in the phone's browser
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def packages(data_root: Path) -> list[tuple[str, Path, dict]]:
    """(region id, app folder, meta) for every built package whose region file exists."""
    found = []
    for meta_path in sorted(data_root.glob("*/app/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        rid = meta.get("region") or regions.DEFAULT_REGION
        try:
            regions.load(rid)
        except (FileNotFoundError, ValueError):
            print(f"  skipped {meta_path.parent}: no valid region file for {rid!r}")
            continue
        found.append((rid, meta_path.parent, meta))
    return found


def published_at(app: Path) -> str:
    """When the results were built: the package manifest's time, else the meta.json file time."""
    manifest = app.parent / "manifest.json"
    if manifest.exists():
        stamp = json.loads(manifest.read_text(encoding="utf-8")).get("generated_at_utc")
        if stamp:
            return stamp
    return datetime.fromtimestamp((app / "meta.json").stat().st_mtime, timezone.utc).isoformat()


def villages_json(app: Path) -> list[dict]:
    v = gpd.read_file(app / "villages.geojson")
    out = []
    for _, r in v.iterrows():
        rec = {"id": str(r["village_id"]), "name": _value(r["name"]), "name_local": _value(r.get("name_bn")),
               "lat": round(r.geometry.y, PRECISION), "lon": round(r.geometry.x, PRECISION),
               "population": _value(r["population"]), "outcome": _value(r["outcome"]),
               "urgency_rank": _value(r.get("urgency_rank")), "boat_dependent": bool(r.get("boat_dependent")),
               "n_dates_isolated": _value(r.get("n_dates_isolated")),
               "n_dates_connected": _value(r.get("n_dates_connected")),
               "n_dates_uncertain": _value(r.get("n_dates_uncertain")),
               "route_shelter": _value(r.get("exit_shelter")), "route_m": _value(r.get("exit_route_m"))}
        for c in ("urgency_rank", "population", "n_dates_isolated", "n_dates_connected", "n_dates_uncertain"):
            rec[c] = None if rec[c] is None else int(rec[c])     # whole numbers, not 5.0
        for c in VILLAGE_DATES:
            rec[c] = _value(pd.to_datetime(r.get(c), errors="coerce"))
        out.append(rec)
    return out


def status_json(app: Path, dates: list[str], village_ids: list[str]) -> dict:
    s = pd.read_csv(app / "village_status.csv", dtype={"village_id": str})
    s["date"] = pd.to_datetime(s["date"]).dt.strftime("%Y-%m-%d")
    lookup = {(r.village_id, r.date): STATUS_CODES.get(r.status, "u") for r in s.itertuples()}
    return {"codes": {v: k for k, v in STATUS_CODES.items()},
            "villages": {vid: "".join(lookup.get((vid, d), "u") for d in dates) for vid in village_ids}}


def flooded_roads_json(app: Path, dates: list[str]) -> dict:
    """Each road segment once, simplified, with `d`: the indices of the radar dates it was flooded on.
    Segments flooded on exactly the same dates share one multi-part feature (`n` segments): the same
    picture, far fewer features to download and draw."""
    cut = gpd.read_file(app / "cut_roads.geojson")
    if cut.empty:
        return {"type": "FeatureCollection", "features": []}
    index = {d: i for i, d in enumerate(dates)}
    cut["date"] = pd.to_datetime(cut["date"]).dt.strftime("%Y-%m-%d")
    by_days: dict[tuple, list] = {}
    for _, grp in cut.groupby("edge_id", sort=True):
        days = tuple(sorted(index[d] for d in grp["date"].unique() if d in index))
        by_days.setdefault(days, []).append(grp.geometry.iloc[0].simplify(ROAD_SIMPLIFY_DEG))
    feats = []
    for days, lines in sorted(by_days.items()):
        parts = [ln for geom in lines for ln in (geom.geoms if hasattr(geom, "geoms") else [geom])]
        feats.append({"type": "Feature", "properties": {"d": list(days), "n": len(lines)},
                      "geometry": _geometry(MultiLineString(parts))})
    return {"type": "FeatureCollection", "features": feats}


def critical_files(results: Path, dates: list[str], village_ids: list[str]) -> tuple[dict, dict] | None:
    """The road-criticality analysis (scripts/road_criticality.py) in the app's form, or None if it has not run."""
    dry_path, daily_path = results / "road_criticality.geojson", results / "road_criticality_by_date.geojson"
    frag_path = results / "fragile_villages.csv"
    if not (dry_path.exists() and daily_path.exists() and frag_path.exists()):
        return None
    index = {d: i for i, d in enumerate(dates)}
    keep = ("rank", "villages", "population", "n_segments", "length_m", "village_ids", "buildings")
    feats = []
    for kind, path in (("dry", dry_path), ("date", daily_path)):
        for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
            props = {k: _value(f["properties"].get(k)) for k in keep}
            props["kind"] = kind
            if kind == "date":
                props["d"] = sorted(index[d] for d in f["properties"]["dates"] if d in index)
            feats.append({"type": "Feature", "properties": props, "geometry": _geometry(shape(f["geometry"]))})
    frag = pd.read_csv(frag_path, dtype={"village_id": str})
    on = set(zip(frag["village_id"], frag["date"]))
    summary = {
        "fragile": {vid: "".join("1" if (vid, d) in on else "0" for d in dates) for vid in village_ids},
        "dry_stretches": sum(1 for f in feats if f["properties"]["kind"] == "dry"),
        "checked_on_ground": False,
    }
    return {"type": "FeatureCollection", "features": feats}, summary


def _b36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    n, out = int(n), ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


def buildings_file(results: Path) -> dict | None:
    """Mapped buildings (scripts/building_exposure.py) for the app, or None if that analysis has not run.

    cells: [lat, lon, buildings, far from roads, isolated per date, uncertain per date, near water per date].
    To keep the phone download small, a per-date list is null when it is all zero, and otherwise one string of
    base-36 numbers joined by "." ("0.0.c5" = 0, 0, 437); lat and lon have 4 decimals (about 11 m, for 400 m cells)."""
    summary, cells_csv, clusters_csv = (results / "buildings_summary.json", results / "buildings_cells.csv",
                                        results / "buildings_clusters.csv")
    if not (summary.exists() and cells_csv.exists() and clusters_csv.exists()):
        return None
    import ast
    s = json.loads(summary.read_text(encoding="utf-8"))
    c = pd.read_csv(cells_csv)
    packed = []
    for r in c.itertuples():
        lists = [ast.literal_eval(x) for x in (r.i, r.u, r.w)]
        packed.append([round(r.lat, 4), round(r.lon, 4), int(r.n), int(r.far)] +
                      [".".join(_b36(v) for v in lst) if any(lst) else None for lst in lists])
    cl = pd.read_csv(clusters_csv, dtype={"nearest_village_id": str})
    keep = ["rank", "buildings", "max_isolated", "dates_isolated", "first_isolated", "score", "lat", "lon",
            "nearest_village_id", "nearest_village_km"]
    return _clean({**s, "cells": packed, "clusters": [{k: _value(row[k]) for k in keep if k in cl}
                                                        for _, row in cl.head(20).iterrows()],
                   "checked_on_ground": False})


def build_one(rid: str, app: Path, meta: dict, out: Path) -> dict:
    reg = regions.load(rid)
    dest = out / rid
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "flood").mkdir(parents=True)
    dates = list(meta["dates"])

    metadata = {
        "id": rid, "name": reg.name, "country": reg.country, "data_label": meta.get("data_label", ""),
        "demonstration": meta.get("data_label", "").upper().startswith(("DEMONSTRATION", "SYNTHETIC")),
        "dates": dates, "flood_bounds": meta["flood_bounds"], "unknown_pct": _clean(meta.get("unknown_pct", {})),
        "sources": _clean(meta.get("sources", {})), "cut_threshold": meta.get("cut_threshold"),
        "app_start": meta.get("app_start"), "app_end": meta.get("app_end"),
        "default_supply_days": meta.get("default_supply_days"), "supply_days_range": meta.get("supply_days_range"),
        "observed_through": max(dates) if dates else None, "published_at": published_at(app), "last_checked": None,
        "languages": reg.languages, "agencies": reg.agencies, "emergency_contacts": reg.emergency_contacts,
        "bbox": list(reg.bbox) if reg.bbox else None,
    }
    _write(dest / "metadata.json", metadata)

    villages = villages_json(app)
    _write(dest / "villages.json", villages)
    _write(dest / "status.json", {"dates": dates, **status_json(app, dates, [v["id"] for v in villages])})
    _write(dest / "flooded_roads.geojson", flooded_roads_json(app, dates))
    results = app.parent / "results"
    critical = critical_files(results, dates, [v["id"] for v in villages])
    if critical:
        _write(dest / "critical_roads.geojson", critical[0])
        _write(dest / "critical.json", critical[1])
    buildings = buildings_file(results)
    if buildings:
        _write(dest / "buildings.json", buildings)
    relief = results / "relief_prepositioning.json"
    if relief.exists():
        r = json.loads(relief.read_text(encoding="utf-8"))
        if r.get("test_flood") == rid:
            _write(dest / "relief.json", _clean(r))

    routes = gpd.read_file(app / "exit_routes.geojson")
    _write(dest / "routes.geojson", _features(routes, ["village_id", "date", "shelter_id", "shelter_name", "length_m"],
                                              {"checked_on_ground": False}))
    _write(dest / "shelters.geojson", _features(gpd.read_file(app / "shelters.geojson"),
                                                ["shelter_id", "name", "type", "source"], {"verified": False}))
    if (app / "health.geojson").exists():
        _write(dest / "health.geojson", _features(gpd.read_file(app / "health.geojson"), ["name", "type", "source"],
                                                  {"verified": False}))
    for src, name in (("roads.geojson", "roads.geojson"), ("study_area.geojson", "area.geojson")):
        if (app / src).exists():
            shutil.copy2(app / src, dest / name)
    for png in sorted((app / "flood").glob("*.png")):
        shutil.copy2(png, dest / "flood" / png.name)

    # what the app's "download this area" button fetches, so the flood works offline
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    size_bytes = sum((dest / f).stat().st_size for f in files)
    _write(dest / "files.json", {"files": files + ["files.json"], "bytes": size_bytes})
    size_mb = size_bytes / 1e6
    return {"id": rid, "name": reg.name, "country": reg.country, "first_date": dates[0] if dates else None,
            "observed_through": metadata["observed_through"], "demonstration": metadata["demonstration"],
            "villages": len(villages), "size_mb": round(size_mb, 2),
            "analyses": {"critical_roads": (dest / "critical.json").exists(), "relief": (dest / "relief.json").exists(),
                         "buildings": (dest / "buildings.json").exists()}}


def nisar_export(data_root: Path, out: Path) -> dict | None:
    """NISAR L-band layers (scripts/nisar_polarization.py, data/<region>/results/nisar/) for the app's NISAR page:
    out/nisar/index.json plus, per region, its PNG layers and the study-area outline. None if there are none."""
    found = sorted(data_root.glob("*/results/nisar/nisar.json"))
    dest_root = out / "nisar"
    if dest_root.exists():
        shutil.rmtree(dest_root)
    if not found:
        return None
    entries = []
    for path in found:
        pkg = path.parent.parent.parent
        meta = json.loads(path.read_text(encoding="utf-8"))
        rid = meta["region"]
        try:
            reg = regions.load(rid)
            name = reg.name
        except (FileNotFoundError, ValueError):
            name = rid
        dest = dest_root / rid
        dest.mkdir(parents=True)
        for scene in meta["scenes"]:
            for f in scene["layers"].values():
                shutil.copy2(path.parent / f, dest / f)
        gap = path.parent / "village_water.json"          # scripts/nisar_village_water.py: water NISAR sees and Sentinel-1 does not
        if gap.exists():
            shutil.copy2(gap, dest / "village_water.json")
        area = pkg / "processed" / "study_area.gpkg"
        if area.exists():
            _write(dest / "area.geojson", _features(gpd.read_file(area).to_crs(4326), []))
        villages = pkg / "processed" / "villages.gpkg"
        if villages.exists():
            v = gpd.read_file(villages).to_crs(4326)
            keep = [c for c in ("village_id", "name", "name_bn") if c in v.columns]
            _write(dest / "villages.geojson", _features(v, keep))
        entries.append(_clean({"id": rid, "name": name, "product": meta.get("product"), "bounds": meta["bounds"],
                               "method": meta.get("method"), "scenes": meta["scenes"],
                               "has_area": area.exists(), "has_villages": villages.exists(),
                               "has_village_water": gap.exists()}))
    index = {"regions": entries}
    _write(dest_root / "index.json", index)
    return index


MONITOR_KEYS = ("region", "name", "checked_at", "newest_radar", "new_since_last_check", "rain", "sends_alerts")


def monitor_json(data_root: Path) -> dict | None:
    """The daily check (scripts/daily_check.py, data/monitor/<region>.json) for the app, or None if it never ran.
    Only what the check itself wrote: the newest radar date found and NASA GPM rain totals. It sends nothing."""
    files = sorted((data_root / "monitor").glob("*.json"))
    if not files:
        return None
    regions_out = []
    for f in files:
        m = json.loads(f.read_text(encoding="utf-8"))
        regions_out.append({k: m.get(k) for k in MONITOR_KEYS} | {"radar_dates": len(m.get("radar_dates") or [])})
    return {"regions": _clean(regions_out)}


def build(data_root: Path = ROOT / "data", out: Path = DEFAULT_OUT) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    floods = [build_one(rid, app, meta, out) for rid, app, meta in packages(data_root)]
    # the published 2022 study first, then by date; demonstrations last
    floods.sort(key=lambda f: (f["demonstration"], f["id"] != regions.DEFAULT_REGION, f["first_date"] or ""))
    _write(out / "index.json", {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "floods": floods})
    nisar_export(data_root, out)
    monitor = monitor_json(data_root)
    if monitor:
        _write(out / "monitor.json", monitor)
    elif (out / "monitor.json").exists():
        (out / "monitor.json").unlink()
    return floods


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="folder holding the flood packages (data/*/app)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where the app's data files go")
    args = ap.parse_args()
    floods = build(args.data, args.out)
    for f in floods:
        flag = "  TOO BIG for a phone download" if f["size_mb"] > MAX_FLOOD_MB else ""
        print(f"  {f['id']:22s} {f['villages']:4d} villages  {f['size_mb']:5.2f} MB{flag}")
    print(f"Wrote {len(floods)} floods to {args.out}")


if __name__ == "__main__":
    main()
