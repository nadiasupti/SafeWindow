"""SafeWindow - Streamlit app (Step 8).

    streamlit run app/streamlit_app.py
    (set SAFEWINDOW_DATA_DIR=data_demo to view the synthetic demo)

Reads only the pre-computed files in <data>/app/ (pipeline/08_build_app_data.py),
so it stays fast and does not need the heavy GIS libraries.
"""
from __future__ import annotations

import html
import json
import math
import os
import sys
from pathlib import Path

import altair as alt
from jinja2 import Template
import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import config  # noqa: E402
from safewindow import evac_card  # noqa: E402
from safewindow import health as health_layer  # noqa: E402
from safewindow import region as regions  # noqa: E402
from safewindow.region import rain_label  # noqa: E402
from safewindow.validation import validate_app_dataset  # noqa: E402

# Licence credits (OpenStreetMap's ODbL requires visible attribution wherever its data is used).
CREDITS = ("Data: roads, villages and shelter candidates © OpenStreetMap contributors (ODbL); offline world map Natural Earth (public domain); "
           "population WorldPop 2020 (CC BY 4.0); "
           "flood maps from ESA Copernicus Sentinel-1; NASA NASADEM and GPM IMERG; flood references UNITAR-UNOSAT and Copernicus EMS.")

# SAFEWINDOW_OFFLINE=1 makes the app need no internet: no map tiles are requested (Leaflet itself is served
# from app/static, never from a CDN), so only villages, shelters, routes and the flood image are drawn.
OFFLINE = os.environ.get("SAFEWINDOW_OFFLINE", "").lower() in ("1", "true", "yes")
LEAFLET_DIR = Path(__file__).resolve().parent / "static" / "vendor" / "leaflet"
LEAFLET_URL = "/app/static/vendor/leaflet"      # served by Streamlit (server.enableStaticServing)
SHELTER_ICON = ("<div style='width:18px;height:18px;background:#ffd23f;border:3px solid #0b2e6b;"
                "box-shadow:0 0 3px #000'></div>")      # yellow with a navy edge: visible on the blue flood layer

# Offline base map: the road network drawn from roads.geojson, by class (1 major ... 4 tracks and paths).
ROAD_STYLE = {1: ("#c98a1b", 3.2), 2: ("#d9b45a", 2.4), 3: ("#a8a195", 1.3), 4: ("#bdb6a8", 1.0)}
PAPER = "#f2efe9"
LABEL_STYLE = ("background:rgba(255,255,255,.78);border:0;box-shadow:none;color:#222;font-size:11px;"
               "font-weight:600;padding:0 3px")
LABEL_LIMIT = 30          # more villages than this and permanent name labels would cover the map

# One stylesheet for every screen: phones, tablets, laptops and very wide monitors.
RESPONSIVE_CSS = """<style>
.block-container {max-width: 1400px; padding-top: 1.2rem; padding-bottom: 3rem;}
h1 {font-size: clamp(1.7rem, 5.5vw, 2.6rem) !important; line-height: 1.15 !important;}
/* the map follows the screen height: tall enough to use, never so tall that it traps page scrolling */
iframe[title="streamlit_folium.st_folium"] {height: clamp(300px, 62vh, 760px) !important;}
[data-testid="stExpander"] summary {min-height: 48px; display: flex; align-items: center;}
[data-testid="stExpander"] summary:focus-visible, button:focus-visible, [role=combobox]:focus-visible {outline: 3px solid #1e6ee6; outline-offset: 2px;}
@media (max-width: 640px) {
  .block-container {padding: 0.6rem 0.8rem 3rem;}
  [data-testid="stHeader"] {height: 2.6rem;}
  [data-testid="stMetricValue"] {font-size: 1.5rem;}
  [data-testid="stAlert"] {font-size: 0.92rem;}
  [data-testid="stDownloadButton"] button {width: 100%;}
}
@media (pointer: coarse) {        /* fingers: bigger controls */
  button, [role=combobox], [data-testid="stRadio"] label, [data-testid="stCheckbox"] label {min-height: 44px;}
  [data-testid="stRadio"] label {padding-inline: 0.4rem;}
  [data-testid="stTooltipHoverTarget"], [data-testid="stTooltipHoverTarget"] button {min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center;}
  [data-testid="stBaseButton-elementToolbar"], [data-testid="stBaseButton-headerNoPadding"], [data-testid="stMainMenuButton"] {min-width: 40px; min-height: 40px;}
  [data-testid="stSlider"] [role=slider] {transform: scale(1.5);}
  [data-testid="stSlider"] {padding-bottom: 0.4rem;}
}
@media (prefers-reduced-motion: reduce) {* {animation: none !important; transition: none !important;}}
</style>"""


WORLD_DIR = Path(__file__).resolve().parent / "static" / "world"
WORLD_URL = "/app/static/world/"
SEA = (0xCF, 0xE3, 0xF1)

STATUS_COLOR = {"connected": "#2e9d4f", "isolated": "#d7263d", "uncertain": "#f39c12",
                "boat_dependent": "#8a8f98"}

def legend_html(t: dict) -> str:
    """The colour and symbol key, as one wrapping line that works at any width."""
    box = "display:inline-block;max-width:100%"        # an item may wrap, but never runs off a narrow screen
    items = [f"<span style='{box}'><span style='color:{c};font-size:1.2em'>●</span> "
             f"{evac_card.STATUS_SYMBOLS[k]} {t[k]}</span>" for k, c in STATUS_COLOR.items()]
    items.append(f"<span style='{box}'><span style='color:#1e6ee6'>■</span> {t['flood']}</span>")
    items.append(f"<span style='{box}'><span style='color:#8c8c8c'>■</span> {t['no_data']}</span>")
    return "<div style='line-height:2;font-size:0.9rem'>" + " &nbsp;&nbsp; ".join(items) + "</div>"


# App text, one file per language in locales/. A new language needs only a new
# file there and its code in the region's `languages`.
LOCALES_DIR = config.ROOT / "locales"
RAW_LOCALES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(LOCALES_DIR.glob("*.json"))}
# A language may leave keys out: they fall back to English, so a new language can start small.
T = {code: raw if code == "en" else {**RAW_LOCALES["en"], **raw} for code, raw in RAW_LOCALES.items()}


def app_languages(reg: regions.Region | None = None) -> list[str]:
    """The region's languages that have a locale file, English first if present."""
    langs = [lang for lang in (reg or config.REGION).languages if lang in T]
    return langs or ["en"]


def texts(lang: str, reg: regions.Region | None = None) -> dict:
    """Locale text with the region's warning agencies filled in."""
    t = dict(T[lang])
    agencies = ", ".join((reg or config.REGION).agencies)
    if t.get("dir") == "rtl":
        agencies = f"{chr(0x2068)}{agencies}{chr(0x2069)}"
    t["limits_text"] = t["limits_text"].format(agencies=agencies)
    t["card_disclaimer"] = t["card_disclaimer"].format(agencies=agencies)
    return t


def flood_packages(data_root: Path | None = None) -> list[tuple[str, Path]]:
    """Built app packages under data/ (one per flood), the published 2022 study first.
    Each is (region id, data folder); the region comes from the package's meta.json.
    A package whose meta.json or region file cannot be read (e.g. half-built) is
    skipped, so it never stops the other floods from opening."""
    found = []
    for meta_path in sorted((data_root or config.ROOT / "data").glob("*/app/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rid = meta.get("region") or regions.DEFAULT_REGION
            start = regions.load(rid).flood_start
        except Exception:      # unreadable JSON, missing or invalid region file
            continue
        found.append((rid, meta_path.parent.parent, start))
    live = config.DEFAULT_DATA_DIR.split("/")[-1]
    found.sort(key=lambda p: (p[1].name != live, p[2], p[0]))
    return [(rid, folder) for rid, folder, _ in found]


def tf(t: dict, key: str, **kw) -> str:
    """Format a locale string. In right-to-left languages every inserted value is wrapped in Unicode isolates, so a
    Latin name, date or number cannot pull the punctuation beside it to the wrong side. Not used for SMS text:
    older phones can show isolates as boxes."""
    if t.get("dir") == "rtl":
        fsi, pdi = chr(0x2068), chr(0x2069)
        kw = {k: f"{fsi}{v}{pdi}" if isinstance(v, str) else v for k, v in kw.items()}
    return t[key].format(**kw)


def local_num(x, lang: str) -> str:
    digits = T[lang].get("digits")
    return str(x).translate(str.maketrans("0123456789", digits)) if digits else str(x)


def fmt_date(d, lang: str) -> str:
    if d is None or pd.isna(d):
        return "-"
    d = pd.Timestamp(d)
    months = T[lang].get("months")
    if months:
        return (T[lang].get("date_format") or "{d} {m}").format(d=local_num(d.day, lang), m=months[d.month - 1])
    return d.strftime("%d %b")


# --- data ------------------------------------------------------------------------

@st.cache_data
def load(app_dir: str):
    d = Path(app_dir)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    villages = gpd.read_file(d / "villages.geojson")
    for c in ("last_connected", "first_isolated", "isolated_from_earliest", "reconnected", "safe_exit_date"):
        villages[c] = pd.to_datetime(villages[c], errors="coerce")
    status = pd.read_csv(d / "village_status.csv", dtype={"village_id": str})
    status["date"] = pd.to_datetime(status["date"], errors="coerce")
    shelters = gpd.read_file(d / "shelters.geojson")
    routes = gpd.read_file(d / "exit_routes.geojson") if (d / "exit_routes.geojson").exists() else gpd.GeoDataFrame(
        columns=["village_id", "shelter_id", "shelter_name", "length_m", "geometry"],
        geometry="geometry", crs="EPSG:4326")
    for col in ("village_id", "shelter_id", "shelter_name", "length_m"):      # a package with no routes has an empty file
        if col not in routes.columns:
            routes[col] = pd.Series(dtype="object")
    cut = gpd.read_file(d / "cut_roads.geojson") if (d / "cut_roads.geojson").exists() else gpd.GeoDataFrame(
        columns=["edge_id", "date", "geometry"], geometry="geometry", crs="EPSG:4326")
    opt = {n: pd.read_csv(d / f) for n, f in [("rain", "rainfall_daily.csv"), ("modis", "modis_flood_area.csv"),
                                               ("sens", "sensitivity_summary.csv"), ("valid", "validation.csv"),
                                               ("roads", "road_reports_verdict.csv")]
           if (d / f).exists()}
    return meta, villages, status, shelters, routes, cut, opt


def village_name(v, lang: str) -> str:
    """The village name in the locale's own name column (e.g. name_bn) when it has one."""
    col = T[lang].get("name_column")
    local = v.get(col) if col else None
    return local if isinstance(local, str) and local else v["name"]


def sms_text(v, route_km, shelter, lang: str) -> str:
    t = T[lang]
    lo, hi = fmt_date(v["isolated_from_earliest"], lang), fmt_date(v["first_isolated"], lang)
    when = (t["sms_when_range"] if pd.notna(v["last_connected"]) else t["sms_when_before"]).format(lo=lo, hi=hi)
    route = (t["sms_route"].format(km=local_num(f"{route_km:.1f}", lang), shelter=shelter)
             if route_km is not None else t["sms_no_route"])
    return t["sms_template"].format(name=village_name(v, lang), when=when, route=route,
                                    shelter=shelter or t["sms_no_shelter"])


def sms_short_text(v, shelter, lang: str) -> str:
    """A short alert that fits few SMS messages, for when only text messages get through."""
    t = T[lang]
    lo, hi = fmt_date(v["isolated_from_earliest"], lang), fmt_date(v["first_isolated"], lang)
    when = (t["sms_when_range"] if pd.notna(v["last_connected"]) else t["sms_when_before"]).format(lo=lo, hi=hi)
    leave = t["sms_leave_before"].format(d=fmt_date(v["safe_exit_date"], lang)) if pd.notna(v["safe_exit_date"]) else ""
    return t["sms_short_template"].format(name=village_name(v, lang), when=when,
                                          shelter=shelter or t["sms_no_shelter"], exit=leave)


def build_card(v, r, shelters, reg: regions.Region, lang: str, t: dict, supply: int, health=None) -> dict:
    """The evacuation card for one village. `r` is its exit-route row(s) for the chosen date."""
    route_km = r["length_m"].iloc[0] / 1000 if len(r) else None
    shelter = r["shelter_name"].iloc[0] if len(r) else None
    outcome = v["outcome"]
    isolated = outcome == "isolated"
    kind = "isolated" if isolated else "unknown" if outcome in ("uncertain", "boat_dependent") else "ok"
    status = (t["status_isolated"] if isolated else t["status_unknown"] if outcome == "uncertain"
              else t["boat_dependent"] if outcome == "boat_dependent" else t["status_ok"])
    facts = [(t["pop"], "-" if pd.isna(v["population"]) else local_num(f"{int(v['population']):,}", lang))]
    if isolated:
        rng = (f"{fmt_date(v['isolated_from_earliest'], lang)} – {fmt_date(v['first_isolated'], lang)}"
               if pd.notna(v["last_connected"]) else f"≤ {fmt_date(v['first_isolated'], lang)}")
        facts += [(t["isolation"], rng), (t["safe_exit"], fmt_date(v["safe_exit_date"], lang)),
                  (t["deadline_label"], fmt_date(v["aid_deadline"], lang))]
    svg = ""
    if route_km is not None:
        coords = [(x, y) for x, y, *_ in r.geometry.iloc[0].coords]
        svg = evac_card.route_svg((v.geometry.x, v.geometry.y), coords,
                                  [(s.geometry.x, s.geometry.y, s.name) for s in shelters.itertuples()],
                                  village_name(v, lang))
        go = tf(t, "go_route_last" if isolated else "go_route", s=shelter, km=local_num(f"{route_km:.1f}", lang))
        walk = tf(t, "walk", h=local_num(f"{evac_card.walk_hours(route_km):.1f}", lang))
    else:
        go, walk = (t["go_none"] if isolated else t["go_ok"]), ""
    if health is None:        # no health layer given: use the hospitals and clinics in the shelter list
        health = [(s.name, s.geometry.y, s.geometry.x) for s in shelters.itertuples()
                  if str(getattr(s, "type", "")).lower() in evac_card.HEALTH_TYPES]
    nearest = evac_card.nearest_facility(v.geometry.y, v.geometry.x, health)
    health_text = (tf(t, "health_line", name=nearest[0], km=local_num(f"{nearest[1]:.1f}", lang), dir=nearest[2])
                   if nearest else t["health_none"])          # never silent: say what to do when nothing is listed
    sms = sms_short_text(v, shelter, lang) if isolated else ""
    return {"id": v["village_id"], "name": village_name(v, lang), "status": status, "status_kind": kind, "health": health_text,
            "facts": facts, "go": go, "walk": walk, "svg": svg, "lat": v.geometry.y, "lon": v.geometry.x,
            "bag": [i.format(n=local_num(supply, lang)) for i in t["bag_items"]],
            "contacts": ([(c.get(f"name_{lang}") or c["name"], c["number"]) for c in reg.emergency_contacts]
                         or [(t["contacts_112"], "112")]),
            "sms": sms, "sms_parts": t["sms_len"].format(n=local_num(evac_card.sms_parts(sms), lang)) if sms else "",
            "tips": t["card_tip_list"]}


def made_note(t: dict, obs_day: str, supply: int, lang: str) -> str:
    return tf(t, "card_made", d=fmt_date(pd.Timestamp.now(), lang), o=fmt_date(obs_day, lang),
                                 n=local_num(supply, lang))


def build_overview(villages, status, lang: str) -> dict | None:
    """Every village's status on every radar date, for the offline pack's flood replay slider."""
    st_ = status.dropna(subset=["date"]).drop_duplicates(["village_id", "date"])
    dates = sorted(set(st_["date"]))
    if not dates:
        return None
    lookup = {(r.village_id, r.date): r.status for r in st_.itertuples()}
    codes = {v: [lookup.get((v, d), "uncertain") for d in dates] for v in villages["village_id"]}
    peak = max(range(len(dates)), key=lambda i: sum(c[i] == "isolated" for c in codes.values()))
    return {"villages": [{"id": v["village_id"], "name": village_name(v, lang), "lat": v.geometry.y,
                          "lon": v.geometry.x, "pop": 0 if pd.isna(v["population"]) else int(v["population"])}
                         for _, v in villages.iterrows()],
            "dates": [fmt_date(d, lang) for d in dates], "status": codes, "start": peak}


@st.cache_data(show_spinner=False)
def pack_html(app_dir: str, region_id: str, obs_day: str, lang: str, supply: int) -> str:
    """The offline pack: every village's evacuation card in one self-contained HTML file."""
    meta, villages, status, shelters, routes, _cut, _opt = load(app_dir)
    reg = regions.load(region_id)
    t = texts(lang, reg)
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(supply, unit="D")
    ranked = villages.sort_values(["urgency_rank", "name"], na_position="last")
    clinics = load_health(app_dir, package_stamp(app_dir))
    cards = [build_card(v, route_for_date(routes, v["village_id"], pd.Timestamp(obs_day)), shelters, reg, lang, t, supply, clinics)
             for _, v in ranked.iterrows()]
    places = [(s.name, s.geometry.y, s.geometry.x) for s in shelters.itertuples()]
    return evac_card.offline_pack_html(cards, t, lang, f"{t['title']} - {reg.name}",
                                       made_note(t, obs_day, supply, lang), places, supply,
                                       build_overview(villages, status, lang))


def responder_csv(villages: pd.DataFrame, routes, day: pd.Timestamp) -> str:
    """Isolated villages by urgency, with dates as ISO text, for officials to sort, print or share."""
    def iso(d):
        return "" if pd.isna(d) else pd.Timestamp(d).date().isoformat()

    rows = []
    for _, v in villages[villages["outcome"] == "isolated"].sort_values(["urgency_rank", "name"]).iterrows():
        r = route_for_date(routes, v["village_id"], day)
        rows.append({"rank": int(v["urgency_rank"]), "village": v["name"], "population": v["population"],
                     "isolated_from": iso(v["isolated_from_earliest"]), "isolated_by": iso(v["first_isolated"]),
                     "last_safe_exit": iso(v["safe_exit_date"]), "aid_deadline": iso(v["aid_deadline"]),
                     "last_route_to": r["shelter_name"].iloc[0] if len(r) else "",
                     "last_route_km": round(r["length_m"].iloc[0] / 1000, 1) if len(r) else "",
                     "lat": round(v.geometry.y, 5), "lon": round(v.geometry.x, 5)})
    return chr(0xFEFF) + pd.DataFrame(rows).to_csv(index=False)


def package_stamp(app_dir: str) -> tuple:
    """Changes whenever a file in the package is added, removed or rewritten."""
    return tuple(sorted((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in Path(app_dir).iterdir() if f.is_file()))


@st.cache_data(show_spinner=False)
def validated(app_dir: str, stamp: tuple) -> dict:
    """validate_app_dataset reads every flood image (about 0.8 s), so do it once per package version."""
    return validate_app_dataset(app_dir)


@st.cache_data(show_spinner=False)
def load_health(app_dir: str, stamp: tuple = ()) -> list:
    """Hospitals and clinics of a package (health.geojson), or None to fall back on the shelter list."""
    found = health_layer.read(app_dir)
    return found or None


class WorldMap(folium.MacroElement):
    """The offline world base map (Natural Earth, app/static/world). Each file is fetched only when the map is zoomed
    into the range that uses it, and each feature appears at the zoom Natural Earth recommends. Names are shown in
    the user's language where Natural Earth has them. Needs the panes sw_land, sw_lines and sw_labels."""

    _template = Template("""{% macro script(this, kwargs) %}
(function () {
  var map = {{ this._parent.get_name() }}, BASE = '{{ this.base }}', LANG = '{{ this.lang }}';
  window.__swMap = map;           // handy for tests and for debugging in the browser console
  map.setMaxBounds([[-85, -180], [85, 180]]); map.options.maxBoundsViscosity = 1.0;       // stay on the map of the world
  function far() { map.getContainer().classList.toggle('sw-far', map.getZoom() < 9); }
  map.on('zoomend', far); far();
  var st = document.createElement('style');
  st.textContent = '.sw-label{font:600 11px/1.1 "Noto Sans","Segoe UI",Arial,sans-serif;color:#3b3a36;white-space:nowrap;pointer-events:none;' +
    'text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff}.sw-country{font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:#6b665b;transform:translate(-50%,-50%)}' +
    '.sw-far .leaflet-tooltip{display:none !important}' +
    '.sw-city{transform:translate(6px,-50%)}.sw-city.cap{font-weight:800}.sw-dot{position:absolute;width:5px;height:5px;border-radius:50%;background:#444;border:1px solid #fff;transform:translate(-50%,-50%)}';
  document.head.appendChild(st);
  // [file, first zoom, last zoom, how to draw it]
  var SPEC = {
    land: ['land.geojson', 0, 12], lakes: ['lakes.geojson', 0, 10], rivers: ['rivers.geojson', 3, 10],
    countries: ['countries.geojson', 0, 12], admin1: ['admin1_lines.geojson', 3, 8], places: ['places.geojson', 2, 12]
  };
  var layers = {}, loading = {}, labelMarkers = [], placeMarkers = [];
  function buckets(data, style, pane) {
    var b = {};
    data.features.forEach(function (f) { var z = (f.properties && f.properties.z) || 0; (b[z] = b[z] || []).push(f); });
    var out = {};
    Object.keys(b).forEach(function (z) {
      out[z] = L.geoJson({type: 'FeatureCollection', features: b[z]}, {style: function () { return style; }, pane: pane, interactive: false});
    });
    return out;
  }
  function label(text, lat, lon, cls) {
    var el = document.createElement('div'); el.className = 'sw-label ' + cls; el.textContent = text;
    if (cls === 'sw-city' || cls.indexOf('sw-city') === 0) { var dot = document.createElement('span'); dot.className = 'sw-dot'; el.appendChild(dot); }
    return L.marker([lat, lon], {icon: L.divIcon({html: el, className: '', iconSize: [0, 0]}), pane: 'sw_labels', interactive: false, keyboard: false});
  }
  function build(name, data) {
    if (name === 'land') layers.land = buckets(data, {fillColor: '#f2efe9', fillOpacity: 1, color: '#bdb7aa', weight: 0.6}, 'sw_land');
    if (name === 'lakes') layers.lakes = buckets(data, {fillColor: '#cfe3f1', fillOpacity: 1, color: '#9fc0d8', weight: 0.5}, 'sw_land');
    if (name === 'rivers') layers.rivers = buckets(data, {color: '#8fb8d8', weight: 1.1, opacity: 0.9, fill: false}, 'sw_land');
    if (name === 'countries') {
      layers.countries = buckets(data, {fill: false, color: '#8e8a80', weight: 1}, 'sw_lines');
      data.features.forEach(function (f) { var p = f.properties; if (p.label_x == null) return;
        var m = label(p['name_' + LANG] || p.name, p.label_y, p.label_x, 'sw-country'); m._lo = p.min_label || 0; m._hi = p.max_label || 99; labelMarkers.push(m); });
    }
    if (name === 'admin1') layers.admin1 = buckets(data, {color: '#b9b3a7', weight: 0.7, dashArray: '3 4', fill: false}, 'sw_lines');
    if (name === 'places') data.features.forEach(function (f) { var p = f.properties, c = f.geometry.coordinates;
      var m = label(p.name, c[1], c[0], 'sw-city' + (p.capital ? ' cap' : '')); m._z = p.z; m._ll = [c[1], c[0]]; placeMarkers.push(m); });
  }
  function load(name) {
    if (layers[name] || loading[name] || name === 'admin1' && false) return;
    loading[name] = true;
    fetch(BASE + SPEC[name][0]).then(function (r) { return r.json(); }).then(function (d) { build(name, d); sync(); }).catch(function () { loading[name] = false; });
  }
  function toggle(l, on) { if (on && !map.hasLayer(l)) l.addTo(map); if (!on && map.hasLayer(l)) map.removeLayer(l); }
  function sync() {
    var z = map.getZoom(), bounds = map.getBounds().pad(0.3);
    Object.keys(SPEC).forEach(function (n) { if (z >= SPEC[n][1] && z <= SPEC[n][2]) load(n); });
    Object.keys(layers).forEach(function (n) {
      var inRange = z >= SPEC[n][1] && z <= SPEC[n][2];
      Object.keys(layers[n]).forEach(function (bz) { toggle(layers[n][bz], inRange && +bz <= z); });
    });
    labelMarkers.forEach(function (m) { toggle(m, z >= m._lo && z <= m._hi); });
    placeMarkers.forEach(function (m) { toggle(m, z >= SPEC.places[1] && z <= SPEC.places[2] && z >= m._z && bounds.contains(m._ll)); });
  }
  map.on('zoomend moveend', sync);
  sync();
})();
{% endmacro %}""")

    def __init__(self, lang: str):
        super().__init__()
        self._name = "WorldMap"
        self.base = WORLD_URL
        self.lang = lang if lang.isalpha() else "en"


def add_world_map(m: folium.Map, lang: str) -> None:
    """Sea, land, borders, rivers, lakes and city names for the offline map, if the files are in app/static/world."""
    if not (WORLD_DIR / "land.geojson").exists():
        return
    folium.map.CustomPane("sw_sea", z_index=150).add_to(m)
    folium.map.CustomPane("sw_land", z_index=160).add_to(m)
    folium.map.CustomPane("sw_lines", z_index=250).add_to(m)
    folium.map.CustomPane("sw_labels", z_index=620).add_to(m)
    folium.raster_layers.ImageOverlay(solid_png_uri(SEA), bounds=[[-85, -180], [85, 180]], opacity=1, interactive=False,
                                      pane="sw_sea").add_to(m)
    WorldMap(lang).add_to(m)


class RawGeoJson(folium.MacroElement):
    """A GeoJSON layer from JSON text that is already serialised. folium.GeoJson parses the data and walks every
    coordinate to compute bounds on each rerun (about 0.5 s for a road network); this does neither."""

    _template = Template("""{% macro script(this, kwargs) %}
        L.geoJson({{ this.data }}, {style: function () { return {{ this.style }}; }, interactive: false})
            .addTo({{ this._parent.get_name() }});
    {% endmacro %}""")

    def __init__(self, data_json: str, style: dict):
        super().__init__()
        self._name = "RawGeoJson"
        self.data = data_json
        self.style = json.dumps(style)


@st.cache_data(show_spinner=False)
def load_basemap(app_dir: str) -> dict:
    """The offline base map as ready-to-send JSON text: roads as [(class, json)], weakest class first,
    and the study-area outline. Both are None / empty if this flood's package lacks the files."""
    roads_file, area_file = Path(app_dir) / "roads.geojson", Path(app_dir) / "study_area.geojson"
    roads = []
    if roads_file.exists():
        feats = json.loads(roads_file.read_text(encoding="utf-8"))["features"]
        roads = [(f["properties"]["c"], json.dumps(f, separators=(",", ":")))
                 for f in sorted(feats, key=lambda f: -f["properties"]["c"])]
    return {"roads": roads, "area": area_file.read_text(encoding="utf-8") if area_file.exists() else None}


def add_vector_basemap(m: folium.Map, base: dict) -> None:
    """Draw the study-area outline and the roads (weakest class first, so main roads end up on top)."""
    if base.get("area"):
        RawGeoJson(base["area"], {"color": "#7d7a70", "weight": 2, "dashArray": "6 6", "fill": False}).add_to(m)
    for c, data in base.get("roads") or []:
        colour, weight = ROAD_STYLE[c]
        RawGeoJson(data, {"color": colour, "weight": weight, "opacity": 0.9, "lineCap": "round"}).add_to(m)


@st.cache_data(show_spinner=False)
def cut_roads_geojson(app_dir: str, obs_day: str) -> dict:
    """The roads cut on one radar date as ready-made GeoJSON text, built once per date."""
    cut = load(app_dir)[5]
    day = cut[cut["date"] == obs_day]
    from shapely.geometry import MultiLineString, mapping
    lines = [ln for geom in day.geometry for ln in (geom.geoms if hasattr(geom, "geoms") else [geom])]
    if not lines:
        return {"json": '{"type":"FeatureCollection","features":[]}', "n": 0}
    # one multi-part shape instead of thousands of SVG paths: the same picture, far faster to draw
    feature = {"type": "Feature", "properties": {}, "geometry": mapping(MultiLineString(lines))}
    return {"json": json.dumps(feature, separators=(",", ":")), "n": len(lines)}


def solid_png_uri(rgb: tuple[int, int, int]) -> str:
    """A 1x1 PNG of one colour as a data URI. Stretched over the map it gives a plain paper background."""
    import base64
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"\x00" + bytes(rgb))) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


def tip(text) -> str:
    """Map tooltips are rendered as HTML, and village names come from OpenStreetMap: escape them."""
    return html.escape(str(text))


def basemap_layers(env=None) -> list[dict]:
    """Base map tiles. The defaults (Esri imagery, OpenStreetMap) suit demos only: their terms do not
    allow heavy public traffic. Set SAFEWINDOW_TILE_URL (and SAFEWINDOW_TILE_ATTR) to your own provider."""
    env = os.environ if env is None else env
    if env.get("SAFEWINDOW_TILE_URL"):
        return [{"tiles": env["SAFEWINDOW_TILE_URL"], "attr": env.get("SAFEWINDOW_TILE_ATTR", ""), "name": "Base map"}]
    return [{"tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
             "attr": "Satellite imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
             "name": "Satellite"},
            {"tiles": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
             "attr": "&copy; OpenStreetMap contributors", "name": "Street map"}]


def use_local_leaflet(m: folium.Map) -> folium.Map:
    """Serve Leaflet from this app instead of a public CDN, so the map also loads with no internet."""
    if (LEAFLET_DIR / "leaflet.js").exists():
        m.default_js = [("leaflet", f"{LEAFLET_URL}/leaflet.js"), ("leaflet_paths", f"{LEAFLET_URL}/safewindow-paths.js")]
        m.default_css = [("leaflet_css", f"{LEAFLET_URL}/leaflet.css")]
    return m


def nearest_village(villages: gpd.GeoDataFrame, lat: float, lng: float, max_m: float = 400):
    dx = (villages.geometry.x - lng) * 111_320 * math.cos(math.radians(lat))
    dy = (villages.geometry.y - lat) * 110_540
    d = (dx ** 2 + dy ** 2) ** 0.5
    i = d.idxmin()
    return villages.loc[i, "village_id"] if d[i] <= max_m else None


def route_for_date(routes: pd.DataFrame, village_id: str, day: pd.Timestamp) -> pd.DataFrame:
    """Return only shelter routes that existed on or before the selected map date."""
    selected = routes[routes["village_id"] == village_id].copy()
    if "date" not in selected.columns:
        return selected
    selected["date"] = pd.to_datetime(selected["date"], errors="coerce")
    return selected[selected["date"] <= day]


def is_default_data_dir(paths: config.Paths) -> bool:
    """Return whether the selected data directory is the project's live default."""
    return not os.environ.get("SAFEWINDOW_DATA_DIR")


# --- page --------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="SafeWindow", page_icon="🛶", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(RESPONSIVE_CSS, unsafe_allow_html=True)
    paths = config.get_paths()
    # Without SAFEWINDOW_DATA_DIR the viewer can switch between every built flood.
    packages = flood_packages() if is_default_data_dir(paths) else []
    # One main column on every device: flood and language share the first row (stacked on a phone).
    c_flood, c_lang = st.columns([3, 2]) if len(packages) > 1 else (None, st.container())
    if len(packages) > 1:
        folders = {f"{regions.load(rid).name} ({folder.name})": folder for rid, folder in packages}
        with c_flood:
            # one word per language used by any listed flood, e.g. "Flood / বন্যা"
            codes = dict.fromkeys(c for rid, _ in packages for c in regions.load(rid).languages if c in T)
            label = " / ".join(dict.fromkeys(T[c]["flood"].capitalize() for c in codes)) or "Flood"
            choice = st.selectbox(label, list(folders), key="flood")
        paths = config.Paths(folders[choice])
    if not (paths.app / "meta.json").exists():
        if is_default_data_dir(paths):
            st.error("No live app data has been built. Run `python pipeline/10_build_live_data.py` "
                     "after configuring Earth Engine credentials.")
        else:
            st.error(f"No app data in {paths.app}. Run `python scripts/run_engine.py`.")
        st.stop()
    validation = validated(str(paths.app), package_stamp(str(paths.app)))
    if not validation["valid"]:
        st.error("The generated SafeWindow dataset failed validation.")
        for error in validation["errors"]:
            st.warning(error)
        st.stop()
    meta, villages, status, shelters, routes, cut, opt = load(str(paths.app))
    # Labels, languages and agencies follow the flood being shown.
    reg = regions.load(meta["region"]) if meta.get("region") and len(packages) > 1 else config.REGION

    with c_lang:
        langs = app_languages(reg)
        by_name = {T[code]["language_name"]: code for code in langs}
        lang = by_name[st.radio(" / ".join(T[code]["language"] for code in langs), list(by_name), horizontal=True)]
    t = texts(lang, reg)

    if t.get("dir") == "rtl":       # written text flows right to left; sliders and map controls keep their layout
        st.markdown("<style>.stMarkdown, [data-testid='stCaptionContainer'], [data-testid='stAlert'], h1, h2, h3,"
                    " [data-testid='stWidgetLabel'], [data-testid='stMetric'], [data-testid='stExpander'] summary"
                    " {direction: rtl; text-align: right}</style>", unsafe_allow_html=True)
    if t.get("draft"):
        st.warning(t["draft_notice"])
    st.title(f"🛶 {t['title']}")
    st.caption(t["tagline"])
    if meta.get("data_label"):
        st.warning(f"⚠️ {meta['data_label']}")
    if meta.get("region", reg.id) != reg.id:
        st.error(f"This data was built for region {meta['region']!r}, but SAFEWINDOW_REGION is "
                 f"{reg.id!r}: labels, languages and agencies may not match the data.")
    if is_default_data_dir(paths):
        st.caption(t["source_caption"])

    with st.expander(t["settings"]):        # secondary controls stay out of the way on a small screen
        lo, hi = meta["supply_days_range"]
        supply = st.slider(t["supply"], lo, hi, meta["default_supply_days"], help=t["supply_help"])
        lowdata = st.toggle(t["lowdata"], value=OFFLINE, disabled=OFFLINE, help=t["lowdata_help"]) or OFFLINE

    # Survival Clock depends on the slider, so deadlines are recomputed here
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(supply, unit="D")

    # --- date slider ---
    obs = pd.to_datetime(meta["dates"])
    days = pd.date_range(meta["app_start"], meta["app_end"]).date
    iso_counts = status[status["status"] == "isolated"].groupby("date").size()
    peak = pd.Timestamp(iso_counts.idxmax()).date() if len(iso_counts) else days[0]
    day = st.select_slider(t["date"], options=list(days), value=min(max(peak, days[0]), days[-1]),
                           format_func=lambda d: fmt_date(d, lang))
    past = obs[obs <= pd.Timestamp(day)]
    obs_day = (past.max() if len(past) else obs.min()).strftime("%Y-%m-%d")
    st.caption(tf(t, "showing" if len(past) else "no_obs", 
        d=fmt_date(obs_day, lang), src=meta["sources"].get(obs_day, "")))
    if meta["unknown_pct"].get(obs_day, 0) >= 5:
        st.caption(tf(t, "unknown_note", p=local_num(round(meta["unknown_pct"][obs_day]), lang)))

    st_day = status[status["date"] == obs_day].set_index("village_id")["status"]
    villages["status_now"] = villages["village_id"].map(st_day).fillna("uncertain")
    iso_now = villages[villages["status_now"] == "isolated"]
    st.markdown("**" + tf(t, "isolated_count_one" if len(iso_now) == 1 else "isolated_count", n=local_num(len(iso_now), lang), d=fmt_date(obs_day, lang),
                p=local_num(f"{int(iso_now['population'].sum()):,}", lang)) + "**")

    # --- selected village (from selectbox or map click) ---
    ranked = villages.sort_values(["urgency_rank", "name"], na_position="last")
    ids = [None] + ranked["village_id"].tolist()
    label = dict(zip(villages["village_id"], villages["name"]))
    if st.session_state.get("village") not in ids:     # e.g. a village of the previously viewed flood
        st.session_state.village = None
    if "village" not in st.session_state:
        st.session_state.village = None

    col_pick = st.container()       # filled below, but shown above the map: picking a village comes first
    col_map = st.container()
    with col_map:
        b = meta["flood_bounds"][obs_day]
        centre = [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2]
        if lowdata:     # no tile downloads: a plain paper layer, the flood image, then the vector base map
            m = folium.Map(location=centre, zoom_start=12, tiles=None, control_scale=True)
            add_world_map(m, lang)
            folium.map.CustomPane("sw_bg", z_index=200).add_to(m)
            folium.map.CustomPane("sw_flood", z_index=300).add_to(m)
            pad = 0.6
            folium.raster_layers.ImageOverlay(      # an image, because vector shapes cannot take a pane here
                solid_png_uri((0xF2, 0xEF, 0xE9)), bounds=[[b[0][0] - pad, b[0][1] - pad], [b[1][0] + pad, b[1][1] + pad]],
                opacity=1, interactive=False, pane="sw_bg").add_to(m)
        else:
            base, *extra = basemap_layers()
            m = folium.Map(location=centre, zoom_start=12, tiles=base["tiles"], attr=base["attr"], control_scale=True)
            for layer in extra:
                folium.TileLayer(tiles=layer["tiles"], attr=layer["attr"], name=layer["name"],
                                 overlay=True, control=True).add_to(m)
        folium.raster_layers.ImageOverlay(
            str(paths.app / "flood" / f"{obs_day.replace('-', '')}.png"), bounds=b, opacity=0.75,
            name="Flood analysis (Sentinel-1/other sources)", interactive=False,
            **({"pane": "sw_flood"} if lowdata else {})).add_to(m)
        if lowdata:
            add_vector_basemap(m, load_basemap(str(paths.app)))
        cut_now = cut_roads_geojson(str(paths.app), obs_day)
        if cut_now["n"]:
            RawGeoJson(cut_now["json"], {"color": "#7a1020", "weight": 2, "opacity": 0.7}).add_to(m)
        sel = st.session_state.village
        if sel is not None:
            r = route_for_date(routes, sel, pd.Timestamp(obs_day))
            if len(r):
                folium.GeoJson(r[["geometry"]], name="Exit route (available by selected date)",
                               style_function=lambda _: {
                                   "color": "#0b8a3e", "weight": 6, "opacity": 0.9, "dashArray": "8 6"}).add_to(m)
        for s in shelters.itertuples():
            folium.Marker([s.geometry.y, s.geometry.x], tooltip=f"🏫 {tip(s.name)}",
                          icon=folium.DivIcon(html=SHELTER_ICON, icon_size=(18, 18),
                                              icon_anchor=(9, 9))).add_to(m)
        local_names = {row["village_id"]: village_name(row, lang) for _, row in villages.iterrows()}
        for v in villages.itertuples():
            pop = 0 if pd.isna(v.population) else v.population
            name = f"{evac_card.STATUS_SYMBOLS[v.status_now]} {tip(local_names[v.village_id])}"   # not colour alone
            tooltip = (folium.Tooltip(name, permanent=True, direction="right", offset=(8, 0), style=LABEL_STYLE)
                       if lowdata and len(villages) <= LABEL_LIMIT else f"{name} · {t[v.status_now]}")
            folium.CircleMarker(
                [v.geometry.y, v.geometry.x], radius=5 + min(pop, 8000) / 1200,
                color="#222" if v.village_id == sel else "white", weight=3 if v.village_id == sel else 1,
                fill=True, fill_color=STATUS_COLOR[v.status_now], fill_opacity=0.95,
                tooltip=tooltip).add_to(m)
        use_local_leaflet(m)
        folium.LayerControl(collapsed=True).add_to(m)
        out = st_folium(m, height=560, use_container_width=True, returned_objects=["last_object_clicked"],
                        key="map")
        click = (out or {}).get("last_object_clicked")
        if click and click != st.session_state.get("last_click"):
            st.session_state.last_click = click
            hit = nearest_village(villages, click["lat"], click["lng"])
            if hit and hit != st.session_state.village:
                st.session_state.village = hit
                st.rerun()

    with col_pick:
        choice = st.selectbox(t["pick"], ids, index=ids.index(st.session_state.village),
                              format_func=lambda i: t["none"] if i is None else label[i])
        if choice != st.session_state.village:
            st.session_state.village = choice
            st.rerun()

    st.markdown(legend_html(t), unsafe_allow_html=True)

    st.subheader(t["urgent"])
    top = ranked[ranked["outcome"] == "isolated"].head(15)
    st.dataframe(pd.DataFrame({
        t["rank"]: top["urgency_rank"].astype(int),
        t["village"]: top["name"],
        t["pop"]: ["-" if pd.isna(p_) else local_num(f"{int(p_):,}", lang) for p_ in top["population"]],
        t["isolated_when"]: [f"{fmt_date(a, lang)}–{fmt_date(b_, lang)}" if pd.notna(c) else f"≤ {fmt_date(b_, lang)}"
                             for a, b_, c in zip(top["isolated_from_earliest"], top["first_isolated"],
                                                 top["last_connected"])],
        t["deadline"]: [fmt_date(d, lang) for d in top["aid_deadline"]],
    }), hide_index=True, width="stretch")
    st.download_button(t["csv_dl"], responder_csv(villages, routes, pd.Timestamp(obs_day)),
                       file_name=f"safewindow_responder_{reg.id}.csv", mime="text/csv")

    if st.session_state.village is not None:
        village_panel(villages, routes, shelters, reg, st.session_state.village, pd.Timestamp(day), obs_day,
                      supply, lang, t, load_health(str(paths.app), package_stamp(str(paths.app))))

    with st.expander(t["offline_title"]):
        st.markdown(t["offline_help"])
        st.download_button(t["dl_pack"], pack_html(str(paths.app), reg.id, obs_day, lang, supply),
                           file_name=f"safewindow_pack_{reg.id}_{lang}.html", mime="text/html")

    with st.expander(t["stages_title"]):
        for key in ("before", "during", "after"):
            st.markdown(f"**{t['stage_' + key + '_title']}**")
            st.markdown("\n".join(f"- {line}" for line in t["stage_" + key]))

    with st.expander(t["how"]):
        st.markdown(t["how_text"])

    charts(opt, meta, pd.Timestamp(day), lang, t, reg)

    c1, c2 = st.columns(2)
    if "sens" in opt:
        with c1.expander(t["sens"]):
            st.dataframe(opt["sens"], hide_index=True)
    if "valid" in opt or "roads" in opt:
        with c2.expander(t["valid"]):
            if "roads" in opt:
                st.caption(t["roads_note"])
                for r in opt["roads"].itertuples():
                    st.markdown(f"**{r.event_date}** · [{r.source}]({r.url})  \n> {r.quote}  \n"
                                f"{t['before']} ({r.last_observation_before}): `{r.route_before}` · "
                                f"{t['after']} ({r.first_observation_after}): `{r.route_after}`")
            if "valid" in opt:
                st.dataframe(opt["valid"], hide_index=True)

    with st.expander(t["limits"]):
        st.markdown(t["limits_text"])

    st.caption(CREDITS)


def village_panel(villages, routes, shelters, reg, vid, day: pd.Timestamp, obs_day: str, supply: int, lang, t, health=None):
    v = villages[villages["village_id"] == vid].iloc[0]
    r = route_for_date(routes, vid, day)
    route_km = r["length_m"].iloc[0] / 1000 if len(r) else None
    shelter = r["shelter_name"].iloc[0] if len(r) else None

    st.markdown("---")
    st.subheader(f"{t['panel']}: {village_name(v, lang)}")
    a, b, c, d = st.columns(4)
    a.metric(t["pop"], "-" if pd.isna(v["population"]) else local_num(f"{int(v['population']):,}", lang))
    if v["outcome"] == "isolated":
        rng = (f"{fmt_date(v['isolated_from_earliest'], lang)} – {fmt_date(v['first_isolated'], lang)}"
               if pd.notna(v["last_connected"]) else f"≤ {fmt_date(v['first_isolated'], lang)}")
        b.metric(t["isolation"], rng)
        c.metric(t["safe_exit"], fmt_date(v["safe_exit_date"], lang))
        d.metric(t["deadline_label"], fmt_date(v["aid_deadline"], lang))
        if route_km is not None:
            st.success("🛣️ " + tf(t, "route", km=local_num(f"{route_km:.1f}", lang), s=shelter))
        else:
            st.info(t["no_exit"])
        if day >= v["isolated_from_earliest"]:
            left = (v["aid_deadline"] - day).days
            msg = (tf(t, "days_left", n=local_num(left, lang), d=fmt_date(day, lang)) if left >= 0 else
                   tf(t, "deadline_passed", n=local_num(-left, lang), d=fmt_date(day, lang)))
            (st.error if left <= 2 else st.warning)("⏳ " + msg)
        else:
            st.info(tf(t, "not_yet", d=fmt_date(day, lang)))
        st.markdown(f"**{t['sms']}**")
        st.code(sms_text(v, route_km, shelter, lang), language=None, wrap_lines=True)
        short = sms_short_text(v, shelter, lang)
        st.markdown(f"**{t['sms_short_label']}**")
        st.code(short, language=None, wrap_lines=True)
        st.caption(t["sms_len"].format(n=local_num(evac_card.sms_parts(short), lang)))
    else:
        b.caption(t["isolation"])          # st.metric clips long text with "...", so show the status as wrapping text
        b.markdown("**" + (t[v["outcome"]] if v["outcome"] in t else t["never"]) + "**")
        if v["outcome"] == "connected_when_seen":
            st.caption(tf(t, "seen_detail", c=local_num(int(v.get("n_dates_connected", 0)), lang),
                                               u=local_num(int(v.get("n_dates_uncertain", 0)), lang)))

    if v["outcome"] == "uncertain":
        st.info(t["uncertain_note"])

    card = build_card(v, r, shelters, reg, lang, t, supply, health)
    st.download_button(t["dl_card"], evac_card.village_card_html(card, t, lang, made_note(t, obs_day, supply, lang)),
                       file_name=f"safewindow_{vid}_{lang}.html", mime="text/html", key=f"card_{vid}")


def charts(opt, meta, day: pd.Timestamp, lang, t, reg):
    c1, c2 = st.columns(2)
    rule = alt.Chart(pd.DataFrame({"date": [day]})).mark_rule(color="#d7263d", strokeWidth=2).encode(x="date:T")
    obs = alt.Chart(pd.DataFrame({"date": pd.to_datetime(meta["dates"])})).mark_tick(
        color="#555", thickness=2, size=10).encode(x="date:T")
    if "rain" in opt:
        r = opt["rain"].copy()
        r["date"] = pd.to_datetime(r["date"])
        r = r[(r["date"] >= meta["app_start"]) & (r["date"] <= meta["app_end"])]
        long = r.melt("date", var_name="box", value_name="mm")
        long["box"] = [rain_label(reg, c.removesuffix("_mm"), lang) for c in long["box"]]
        bars = alt.Chart(long).mark_bar(opacity=0.85).encode(
            x=alt.X("date:T", title=None), xOffset="box:N",
            y=alt.Y("mm:Q", title="mm/day"),
            color=alt.Color("box:N", title=None, scale=alt.Scale(range=["#1f4e9c", "#7fb3e6"]),
                            legend=alt.Legend(orient="top")),
            tooltip=["date:T", "box:N", "mm:Q"])
        c1.markdown(f"**{t['rain']}**")
        c1.altair_chart((bars + rule).properties(height=220), width="stretch")
    if "modis" in opt:
        md = opt["modis"].copy()
        md["date"] = pd.to_datetime(md["date"])
        md = md[(md["date"] >= meta["app_start"]) & (md["date"] <= meta["app_end"])]
        line = alt.Chart(md).mark_area(color="#1e6ee6", opacity=0.35, line=True).encode(
            x=alt.X("date:T", title=None), y=alt.Y("flooded_km2:Q", title="km²"),
            tooltip=["date:T", "flooded_km2:Q", "unknown_pct:Q"])
        c2.markdown(f"**{t['modis']}**")
        c2.altair_chart((line + rule + obs).properties(height=220), width="stretch")


if __name__ == "__main__":
    main()
