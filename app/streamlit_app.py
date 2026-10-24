"""SafeWindow - Streamlit app (Step 8).

    streamlit run app/streamlit_app.py
    (set SAFEWINDOW_DATA_DIR=data_demo to view the synthetic demo)

Reads only the pre-computed files in <data>/app/ (pipeline/08_build_app_data.py),
so it stays fast and does not need the heavy GIS libraries.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import altair as alt
import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safewindow import config  # noqa: E402
from safewindow import region as regions  # noqa: E402
from safewindow.region import rain_label  # noqa: E402
from safewindow.validation import validate_app_dataset  # noqa: E402

STATUS_COLOR = {"connected": "#2e9d4f", "isolated": "#d7263d", "uncertain": "#f39c12",
                "boat_dependent": "#8a8f98"}

# App text, one file per language in locales/. A new language needs only a new
# file there and its code in the region's `languages`.
LOCALES_DIR = config.ROOT / "locales"
T = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(LOCALES_DIR.glob("*.json"))}


def app_languages(reg: regions.Region | None = None) -> list[str]:
    """The region's languages that have a locale file, English first if present."""
    langs = [lang for lang in (reg or config.REGION).languages if lang in T]
    return langs or ["en"]


def texts(lang: str, reg: regions.Region | None = None) -> dict:
    """Locale text with the region's warning agencies filled in."""
    t = dict(T[lang])
    t["limits_text"] = t["limits_text"].format(agencies=", ".join((reg or config.REGION).agencies))
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


def local_num(x, lang: str) -> str:
    digits = T[lang].get("digits")
    return str(x).translate(str.maketrans("0123456789", digits)) if digits else str(x)


def fmt_date(d, lang: str) -> str:
    if d is None or pd.isna(d):
        return "-"
    d = pd.Timestamp(d)
    months = T[lang].get("months")
    if months:
        return f"{local_num(d.day, lang)} {months[d.month - 1]}"
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
    st.set_page_config(page_title="SafeWindow", page_icon="🛶", layout="wide")
    paths = config.get_paths()
    # Without SAFEWINDOW_DATA_DIR the viewer can switch between every built flood.
    packages = flood_packages() if is_default_data_dir(paths) else []
    if len(packages) > 1:
        folders = {f"{regions.load(rid).name} ({folder.name})": folder for rid, folder in packages}
        with st.sidebar:
            choice = st.selectbox("Flood / বন্যা", list(folders), key="flood")
        paths = config.Paths(folders[choice])
    if not (paths.app / "meta.json").exists():
        if is_default_data_dir(paths):
            st.error("No live app data has been built. Run `python pipeline/10_build_live_data.py` "
                     "after configuring Earth Engine credentials.")
        else:
            st.error(f"No app data in {paths.app}. Run `python scripts/run_engine.py`.")
        st.stop()
    validation = validate_app_dataset(paths.app)
    if not validation["valid"]:
        st.error("The generated SafeWindow dataset failed validation.")
        for error in validation["errors"]:
            st.warning(error)
        st.stop()
    meta, villages, status, shelters, routes, cut, opt = load(str(paths.app))
    # Labels, languages and agencies follow the flood being shown.
    reg = regions.load(meta["region"]) if meta.get("region") and len(packages) > 1 else config.REGION

    with st.sidebar:
        langs = app_languages(reg)
        by_name = {T[code]["language_name"]: code for code in langs}
        lang = by_name[st.radio(" / ".join(T[code]["language"] for code in langs), list(by_name), horizontal=True)]
        t = texts(lang, reg)
        lo, hi = meta["supply_days_range"]
        supply = st.slider(t["supply"], lo, hi, meta["default_supply_days"], help=t["supply_help"])
        st.markdown("---")
        for k, c in STATUS_COLOR.items():
            st.markdown(f"<span style='color:{c};font-size:1.2em'>●</span> {t[k]}", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#1e6ee6'>■</span> {t['flood']} &nbsp; "
                    f"<span style='color:#8c8c8c'>■</span> {t['no_data']}", unsafe_allow_html=True)
        with st.expander(t["limits"]):
            st.markdown(t["limits_text"])

    st.title(f"🛶 {t['title']}")
    st.caption(t["tagline"])
    if meta.get("data_label"):
        st.warning(f"⚠️ {meta['data_label']}")
    if meta.get("region", reg.id) != reg.id:
        st.error(f"This data was built for region {meta['region']!r}, but SAFEWINDOW_REGION is "
                 f"{reg.id!r}: labels, languages and agencies may not match the data.")
    if is_default_data_dir(paths):
        st.caption(t["source_caption"])

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
    st.caption((t["showing"] if len(past) else t["no_obs"]).format(
        d=fmt_date(obs_day, lang), src=meta["sources"].get(obs_day, "")))
    if meta["unknown_pct"].get(obs_day, 0) >= 5:
        st.caption(t["unknown_note"].format(p=local_num(round(meta["unknown_pct"][obs_day]), lang)))

    st_day = status[status["date"] == obs_day].set_index("village_id")["status"]
    villages["status_now"] = villages["village_id"].map(st_day).fillna("uncertain")
    iso_now = villages[villages["status_now"] == "isolated"]
    st.markdown("**" + t["isolated_count"].format(n=local_num(len(iso_now), lang), d=fmt_date(obs_day, lang),
                p=local_num(f"{int(iso_now['population'].sum()):,}", lang)) + "**")

    # --- selected village (from selectbox or map click) ---
    ranked = villages.sort_values(["urgency_rank", "name"], na_position="last")
    ids = [None] + ranked["village_id"].tolist()
    label = dict(zip(villages["village_id"], villages["name"]))
    if st.session_state.get("village") not in ids:     # e.g. a village of the previously viewed flood
        st.session_state.village = None
    if "village" not in st.session_state:
        st.session_state.village = None

    col_map, col_side = st.columns([2.2, 1])
    with col_map:
        b = meta["flood_bounds"][obs_day]
        centre = [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2]
        m = folium.Map(
            location=centre,
            zoom_start=12,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Satellite imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
            control_scale=True,
        )
        folium.TileLayer(
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr="&copy; OpenStreetMap contributors",
            name="Street map",
            overlay=True,
            control=True,
        ).add_to(m)
        folium.raster_layers.ImageOverlay(
            str(paths.app / "flood" / f"{obs_day.replace('-', '')}.png"), bounds=b, opacity=0.75,
            name="Flood analysis (Sentinel-1/other sources)", interactive=False).add_to(m)
        cut_now = cut[cut["date"] == obs_day]
        if len(cut_now):
            folium.GeoJson(cut_now[["geometry"]], name="Cut roads",
                           style_function=lambda _: {"color": "#7a1020", "weight": 2, "opacity": 0.7}).add_to(m)
        sel = st.session_state.village
        if sel is not None:
            r = route_for_date(routes, sel, pd.Timestamp(obs_day))
            if len(r):
                folium.GeoJson(r[["geometry"]], name="Exit route (available by selected date)",
                               style_function=lambda _: {
                                   "color": "#0b8a3e", "weight": 6, "opacity": 0.9, "dashArray": "8 6"}).add_to(m)
        for s in shelters.itertuples():
            folium.Marker([s.geometry.y, s.geometry.x], tooltip=f"🏫 {s.name}",
                          icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(m)
        for v in villages.itertuples():
            pop = 0 if pd.isna(v.population) else v.population
            folium.CircleMarker(
                [v.geometry.y, v.geometry.x], radius=5 + min(pop, 8000) / 1200,
                color="#222" if v.village_id == sel else "white", weight=3 if v.village_id == sel else 1,
                fill=True, fill_color=STATUS_COLOR[v.status_now], fill_opacity=0.95,
                tooltip=f"{v.name} · {t[v.status_now]}").add_to(m)
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

    with col_side:
        st.subheader(t["urgent"])
        top = ranked[ranked["outcome"] == "isolated"].head(15)
        st.dataframe(pd.DataFrame({
            t["rank"]: top["urgency_rank"].astype(int),
            t["village"]: top["name"],
            t["pop"]: top["population"],
            t["isolated_when"]: [f"{fmt_date(a, lang)}–{fmt_date(b_, lang)}" if pd.notna(c) else f"≤ {fmt_date(b_, lang)}"
                                 for a, b_, c in zip(top["isolated_from_earliest"], top["first_isolated"],
                                                     top["last_connected"])],
            t["deadline"]: [fmt_date(d, lang) for d in top["aid_deadline"]],
        }), hide_index=True, height=420)
        choice = st.selectbox(t["pick"], ids, index=ids.index(st.session_state.village),
                              format_func=lambda i: t["none"] if i is None else label[i])
        if choice != st.session_state.village:
            st.session_state.village = choice
            st.rerun()

    if st.session_state.village is not None:
        village_panel(villages, routes, st.session_state.village, pd.Timestamp(day), lang, t)

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


def village_panel(villages, routes, vid, day: pd.Timestamp, lang, t):
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
            st.success("🛣️ " + t["route"].format(km=local_num(f"{route_km:.1f}", lang), s=shelter))
        else:
            st.info(t["no_exit"])
        if day >= v["isolated_from_earliest"]:
            left = (v["aid_deadline"] - day).days
            msg = (t["days_left"].format(n=local_num(left, lang), d=fmt_date(day, lang)) if left >= 0 else
                   t["deadline_passed"].format(n=local_num(-left, lang), d=fmt_date(day, lang)))
            (st.error if left <= 2 else st.warning)("⏳ " + msg)
        else:
            st.info(t["not_yet"].format(d=fmt_date(day, lang)))
        st.markdown(f"**{t['sms']}**")
        st.code(sms_text(v, route_km, shelter, lang), language=None, wrap_lines=True)
    else:
        b.metric(t["isolation"], t[v["outcome"]] if v["outcome"] in t else t["never"])
        if v["outcome"] == "connected_when_seen":
            st.caption(t["seen_detail"].format(c=local_num(int(v.get("n_dates_connected", 0)), lang),
                                               u=local_num(int(v.get("n_dates_uncertain", 0)), lang)))

    if v["outcome"] == "uncertain":
        st.info(t["uncertain_note"])


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
