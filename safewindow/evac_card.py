"""Printable evacuation cards and the offline pack.

Everything here returns self-contained HTML (inline CSS, inline SVG, no network
requests), so a saved file opens on any phone or PC with no signal and prints
on one page per village. Text arrives already formatted and translated.

A card is a plain dict:
    id, name, status, status_kind ("isolated" | "ok" | "unknown"),
    facts [(label, value)], go (text), walk (text or ""), svg (str or ""),
    bag [str], contacts [(name, number)], sms (str), sms_parts (str), tips [str]
"""
from __future__ import annotations

import html
import json
import math

WALK_KMH = 4.0        # rough walking speed on dry road; slower in water or at night
KM_PER_DEGREE = 111.0
SMS_GSM_LIMITS = (160, 153)        # one message, then per part of a long one
SMS_UCS2_LIMITS = (70, 67)         # Bangla and other non-Latin text

FONTS = "'Noto Sans Bengali','Nirmala UI','Segoe UI',Roboto,Arial,sans-serif"
KIND_COLOR = {"isolated": "#d7263d", "ok": "#2e9d4f", "unknown": "#f39c12"}


HEALTH_TYPES = {"hospital", "clinic", "doctors", "health_post", "health_centre", "community_clinic", "healthcare"}
STATUS_SYMBOLS = {"connected": "\u2713", "isolated": "\u2715", "uncertain": "?", "boat_dependent": "~"}
ARROWS = "\u2191\u2197\u2192\u2198\u2193\u2199\u2190\u2196"      # N NE E SE S SW W NW


def compass_arrow(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """An arrow showing the direction from point 1 to point 2, readable in any language."""
    x = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    bearing = math.degrees(math.atan2(x, lat2 - lat1)) % 360
    return ARROWS[int((bearing + 22.5) // 45) % 8]


def nearest_facility(lat: float, lon: float, facilities: list[tuple[str, float, float]]):
    """(name, straight-line km, arrow) of the closest facility, or None. Not a road distance."""
    best = None
    for name, flat, flon in facilities:
        km = math.hypot((flon - lon) * math.cos(math.radians((lat + flat) / 2)), flat - lat) * KM_PER_DEGREE
        if best is None or km < best[1]:
            best = (name, km, compass_arrow(lat, lon, flat, flon))
    return best


def walk_hours(km: float) -> float:
    return km / WALK_KMH


def sms_parts(text: str) -> int:
    """How many SMS messages a text takes (GSM-7 for plain ASCII, UCS-2 otherwise)."""
    single, multi = SMS_GSM_LIMITS if text.isascii() else SMS_UCS2_LIMITS
    return 1 if len(text) <= single else math.ceil(len(text) / multi)


def _bar_km(px_per_km: float) -> float:
    """A round distance (km) whose scale bar is at least 60 px wide."""
    return next((k for k in (0.5, 1, 2, 5, 10, 20) if k * px_per_km >= 60), 20)


def route_svg(village: tuple[float, float], route: list[tuple[float, float]],
              shelters: list[tuple[float, float, str]], village_label: str,
              width: int = 640, height: int = 420) -> str:
    """A small offline map: the village, its road route and the shelters in view.

    Points are (lon, lat). The route is a dashed green line; shelters are blue squares.
    """
    pts = [village, *route]
    lon0, lon1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lat0, lat1 = min(p[1] for p in pts), max(p[1] for p in pts)
    pad_lon, pad_lat = max((lon1 - lon0) * 0.12, 0.002), max((lat1 - lat0) * 0.12, 0.002)
    lon0, lon1, lat0, lat1 = lon0 - pad_lon, lon1 + pad_lon, lat0 - pad_lat, lat1 + pad_lat
    kx = math.cos(math.radians((lat0 + lat1) / 2))
    span_x, span_y = (lon1 - lon0) * kx, lat1 - lat0
    margin = 40
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)   # px per degree of latitude
    off_x, off_y = (width - span_x * scale) / 2, (height - span_y * scale) / 2

    def xy(lon: float, lat: float) -> tuple[float, float]:
        return off_x + (lon - lon0) * kx * scale, height - off_y - (lat - lat0) * scale

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{html.escape(village_label)}" style="width:100%;height:auto;background:#f4f7f2;'
           f'border:1px solid #c9d3c4;border-radius:6px">']
    if len(route) >= 2:
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(*p) for p in route))
        out.append(f'<polyline points="{d}" fill="none" stroke="#0b8a3e" stroke-width="5" '
                   f'stroke-dasharray="10 7" stroke-linecap="round" stroke-linejoin="round"/>')
    for lon, lat, name in shelters:
        if lon0 <= lon <= lon1 and lat0 <= lat <= lat1:
            x, y = xy(lon, lat)
            out.append(f'<rect x="{x - 8:.1f}" y="{y - 8:.1f}" width="16" height="16" fill="#1e6ee6" '
                       f'stroke="#fff" stroke-width="2"/><text x="{x + 12:.1f}" y="{y + 5:.1f}" font-size="14" '
                       f'font-family="{FONTS}" fill="#10325f">{html.escape(name)}</text>')
    vx, vy = xy(*village)
    out.append(f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="9" fill="#d7263d" stroke="#fff" stroke-width="2"/>'
               f'<text x="{vx + 13:.1f}" y="{vy - 9:.1f}" font-size="14" font-weight="bold" '
               f'font-family="{FONTS}" fill="#7a1020">{html.escape(village_label)}</text>')
    px_per_km = scale / KM_PER_DEGREE
    km = _bar_km(px_per_km)
    bx, by = 16, height - 16
    out.append(f'<path d="M {bx} {by} h {km * px_per_km:.1f}" stroke="#333" stroke-width="3"/>'
               f'<text x="{bx}" y="{by - 7}" font-size="13" font-family="{FONTS}" fill="#333">{km:g} km</text>')
    out.append(f'<text x="{width - 22}" y="22" font-size="14" font-family="{FONTS}" text-anchor="middle" '
               f'fill="#333">N</text><path d="M {width - 22} 28 l -6 14 h 12 z" fill="#333"/></svg>')
    return "".join(out)


STATUS_COLORS = {"connected": "#2e9d4f", "isolated": "#d7263d", "uncertain": "#f39c12", "boat_dependent": "#8a8f98"}
LABEL_LIMIT = 30          # above this many villages the overview map drops the text labels


def overview_svg(villages: list[dict], shelters: list[tuple[str, float, float]], title: str,
                 width: int = 640, height: int = 480) -> str:
    """One map of every village and shelter (no tiles). Villages are links to their card and are
    recoloured by the pack's date slider through their data-v attribute."""
    pts = [(v["lon"], v["lat"]) for v in villages] + [(lon, lat) for _, lat, lon in shelters]
    lon0, lon1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lat0, lat1 = min(p[1] for p in pts), max(p[1] for p in pts)
    pad_lon, pad_lat = max((lon1 - lon0) * 0.06, 0.002), max((lat1 - lat0) * 0.06, 0.002)
    lon0, lon1, lat0, lat1 = lon0 - pad_lon, lon1 + pad_lon, lat0 - pad_lat, lat1 + pad_lat
    kx = math.cos(math.radians((lat0 + lat1) / 2))
    span_x, span_y = (lon1 - lon0) * kx, lat1 - lat0
    margin = 24
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)
    off_x, off_y = (width - span_x * scale) / 2, (height - span_y * scale) / 2

    def xy(lon: float, lat: float) -> tuple[float, float]:
        return off_x + (lon - lon0) * kx * scale, height - off_y - (lat - lat0) * scale

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{html.escape(title)}" style="width:100%;height:auto;background:#f4f7f2;'
           f'border:1px solid #c9d3c4;border-radius:6px">']
    for name, lat, lon in shelters:
        x, y = xy(lon, lat)
        out.append(f'<rect x="{x - 6:.1f}" y="{y - 6:.1f}" width="12" height="12" fill="#1e6ee6" stroke="#fff" '
                   f'stroke-width="2"><title>{html.escape(name)}</title></rect>')
    labels = []
    for v in villages:
        x, y = xy(v["lon"], v["lat"])
        r = 6 + min(v.get("pop") or 0, 20000) / 2500
        vid, name = html.escape(str(v["id"]), quote=True), html.escape(v["name"])
        # an invisible, larger circle makes a fingertip-sized tap target around each village
        out.append(f'<a href="#v-{vid}"><circle cx="{x:.1f}" cy="{y:.1f}" r="{max(r + 8, 16):.1f}" fill="transparent" '
                   f'pointer-events="all"/><circle data-v="{vid}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#8a8f98" '
                   f'stroke="#fff" stroke-width="2"><title>{name}</title></circle></a>')
        if len(villages) <= LABEL_LIMIT:
            labels.append(f'<text x="{x + r + 3:.1f}" y="{y + 4:.1f}" font-size="12" font-family="{FONTS}" fill="#222" '
                          f'stroke="#fff" stroke-width="3" paint-order="stroke" pointer-events="none" data-l="{vid}">{name}</text>')
    out.extend(labels)          # drawn last so no label hides a village, and none can swallow a tap
    out.append("</svg>")
    return "".join(out)


_CSS = f"""
*{{box-sizing:border-box}}
body{{font-family:{FONTS};margin:0;background:#eef1ec;color:#1b1f1a;line-height:1.45;font-size:1.0625rem}}
main{{max-width:800px;margin:0 auto;padding:12px}}
.card{{background:#fff;border:1px solid #c9d3c4;border-radius:10px;padding:18px;margin:14px 0}}
.band{{color:#fff;border-radius:8px;padding:10px 14px;font-weight:700;font-size:1.15em}}
h1{{font-size:1.5em;margin:.2em 0}} h2{{font-size:1.1em;margin:1.1em 0 .3em;border-bottom:2px solid #dde5d8}}
dl{{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:.4em 0}}
dt{{color:#4b5a47}} dd{{margin:0;font-weight:700}}
.go{{background:#e8f5ec;border-inline-start:6px solid #0b8a3e;padding:10px 14px;border-radius:6px;font-weight:700}}
.nogo{{background:#fdf0f1;border-inline-start:6px solid #d7263d;padding:10px 14px;border-radius:6px;font-weight:700}}
ul{{margin:.3em 0;padding-inline-start:1.2em}} li{{margin:.2em 0}}
.sms{{font-family:Consolas,monospace;background:#f4f4f0;border:1px dashed #999;padding:8px;border-radius:6px;word-break:break-word}}
.note{{font-size:.85em;color:#555}}
.idx li{{list-style:none;margin:6px 0}} .idx a{{display:block;padding:10px 12px;background:#fff;border:1px solid #c9d3c4;
 border-radius:8px;text-decoration:none;color:#10325f;font-weight:700}}
input[type=range]{{width:100%;height:44px;margin:6px 0;accent-color:#d7263d}}
input[type=number]{{min-height:44px;padding:6px 8px;font-size:1em;border:2px solid #9bb0c9;border-radius:8px}}
summary{{min-height:44px;display:flex;align-items:center;cursor:pointer}}
button{{min-height:44px;padding:8px 14px;cursor:pointer}}
input[type=search]{{width:100%;padding:12px;font-size:1em;border:2px solid #9bb0c9;border-radius:8px}}
.warn{{background:#fff7e0;border:1px solid #f0c96a;border-radius:8px;padding:10px 14px}}
@media print{{body{{background:#fff;font-size:12pt}} .noprint{{display:none}} main{{max-width:none;padding:0}}
 .card{{border:none;padding:0;margin:0;page-break-after:always}} svg{{max-height:11cm}}}}
main{{padding-inline:max(12px,env(safe-area-inset-left),env(safe-area-inset-right));
 padding-bottom:max(12px,env(safe-area-inset-bottom))}}
@media (max-width:360px){{body{{font-size:1rem}} .card{{padding:12px}} .band{{font-size:1.05em}} h1{{font-size:1.3em}}}}
@media (min-width:1100px){{main{{max-width:900px}} body{{font-size:1.125rem}}}}
@media screen and (prefers-color-scheme:dark){{
 body{{background:#121614;color:#e6ebe4}} .card{{background:#1b2120;border-color:#34413b}} h2{{border-color:#34413b}}
 dt{{color:#a9b8a4}} .note{{color:#b5c0b1}} .go{{background:#16301f;color:#e6ebe4}} .nogo{{background:#3a1d22;color:#e6ebe4}}
 .sms{{background:#222a28;border-color:#5a6b62}} .warn{{background:#3a3217;border-color:#7a6a28;color:#f1e7bd}}
 .idx a{{background:#1b2120;border-color:#34413b;color:#9cc2ff}}
 input[type=search],input[type=number]{{background:#1b2120;color:#e6ebe4;border-color:#4a6a8a}}
 button{{background:#2a3330;color:#e6ebe4;border:1px solid #4a5a52;border-radius:8px}}
 summary b{{color:#e6ebe4}}}}
@page{{size:A4;margin:12mm}}
"""


def _draft(L: dict) -> str:
    return f"<div class='warn'>{html.escape(L['draft_notice'])}</div>" if L.get("draft") else ""


def card_section(card: dict, L: dict) -> str:
    """One village's card as an HTML fragment (an <article>)."""
    e = html.escape
    color = KIND_COLOR.get(card["status_kind"], "#555")
    facts = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in card["facts"])
    go_class = "go" if card["status_kind"] != "isolated" or card["svg"] else "nogo"
    walk = f"<div class='note'>{e(card['walk'])}</div>" if card["walk"] else ""
    svg = f"<h2>{e(L['card_map'])}</h2>{card['svg']}" if card["svg"] else ""
    bag = "".join(f"<li>{e(i)}</li>" for i in card["bag"])
    tips = "".join(f"<li>{e(i)}</li>" for i in card["tips"])
    contacts = ("".join(f"<li><b>{e(n)}</b>: {e(num)}</li>" for n, num in card["contacts"])
                or f"<li>{e(L['contacts_none'])}</li>")
    return (
        f"<article class='card' id='v-{e(str(card['id']))}'>"
        f"<div class='band' style='background:{color}'>{e(L['card_title'])} · {e(card['name'])}</div>"
        f"<p><b>{e(card['status'])}</b></p><dl>{facts}</dl>"
        f"<h2>{e(L['card_go'])}</h2><div class='{go_class}'>{e(card['go'])}</div>{walk}{svg}"
        + (f"<h2>{e(L['card_health'])}</h2><div class='note' style='font-size:1em'>{e(card['health'])}</div>"
           if card.get("health") else "")
        + f"<h2>{e(L['card_bag'])}</h2><ul>{bag}</ul>"
        f"<h2>{e(L['card_contacts'])}</h2><ul>{contacts}</ul>"
        f"<h2>{e(L['card_tips'])}</h2><ul>{tips}</ul>"
        + (f"<h2>{e(L['card_sms'])}</h2><div class='sms'>{e(card['sms'])}</div>"
           f"<div class='note'>{e(card['sms_parts'])}</div>" if card["sms"] else "")
        + "</article>")


def _page(lang: str, title: str, body: str, direction: str = "ltr") -> str:
    return (f"<!doctype html><html lang='{html.escape(lang)}' dir='{'rtl' if direction == 'rtl' else 'ltr'}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><meta name='color-scheme' content='light dark'>"
            f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>")


def village_card_html(card: dict, L: dict, lang: str, made_note: str) -> str:
    """A single village's card as a complete page, ready to save or print."""
    body = (_draft(L) + card_section(card, L)
            + f"<p class='note'>{html.escape(made_note)}</p><div class='warn'>{html.escape(L['card_disclaimer'])}</div>"
            + f"<p class='noprint'><button onclick='window.print()' style='font-size:1em;padding:10px 16px'>"
              f"{html.escape(L['print'])}</button></p>")
    return _page(lang, f"{L['card_title']} - {card['name']}", body, L.get("dir", "ltr"))


_PACK_KEYS = ("finding", "find_fail", "found", "calc_result", "help_body", "no_loc", "no_village", "isolated_count",
              "isolated_count_one")

_PACK_JS = """
var D=__DATA__,V=D.villages,LB=D.labels,DAYS=D.days;
function $(i){return document.getElementById(i)}
function fmt(s,o,iso){for(var k in o){var v=iso&&D.rtl?String.fromCharCode(8296)+o[k]+String.fromCharCode(8297):o[k];s=s.split('{'+k+'}').join(v)}return s}
function people(){return Math.max(1,parseInt($('ppl').value)||1)}
function calc(){var p=people();$('calc').textContent=fmt(LB.calc_result,{p:p,d:DAYS,w:p*DAYS*3,m:p*DAYS*3})}
function dist(a,b,c,d){var r=Math.PI/180,x=(d-b)*r*Math.cos((a+c)*r/2),y=(c-a)*r;return Math.sqrt(x*x+y*y)*6371}
function here(cb){if(!navigator.geolocation){cb(null);return}
 navigator.geolocation.getCurrentPosition(function(p){cb(p.coords)},function(){cb(null)},{enableHighAccuracy:true,timeout:15000})}
function nearest(c){var b=null,bd=1e9;V.forEach(function(v){var d=dist(c.latitude,c.longitude,v.lat,v.lon);if(d<bd){bd=d;b=v}});return b?{v:b,km:bd}:null}
function findMe(){$('found').textContent=LB.finding;here(function(c){
 if(!c){$('found').textContent=LB.find_fail;return}
 var n=nearest(c);
 if(n){$('found').textContent=fmt(LB.found,{name:n.v.name,km:n.km.toFixed(1)},true);location.hash='v-'+n.v.id}})}
function current(){var h=location.hash.replace('#v-','');for(var i=0;i<V.length;i++){if(V[i].id===h)return V[i]}return null}
function helpSms(){var v=current();here(function(c){
 if(!v&&c){var n=nearest(c);if(n)v=n.v}
 var loc=c?c.latitude.toFixed(5)+','+c.longitude.toFixed(5):LB.no_loc;
 go('sms:?&body='+encodeURIComponent(fmt(LB.help_body,{name:v?v.name:LB.no_village,p:people(),loc:loc})))})}
function go(u){location.href=u}
function f(q){q=q.toLowerCase();document.querySelectorAll('.idx li').forEach(function(li){
 li.style.display=li.textContent.toLowerCase().indexOf(q)<0?'none':''})}
var O=D.overview;
function loc(x){x=String(x);return D.digits?x.replace(/[0-9]/g,function(d){return D.digits.charAt(+d)}):x}
function paint(i){if(!O)return;var iso=0,pop=0;
 document.querySelectorAll('circle[data-v]').forEach(function(c){
  var id=c.getAttribute('data-v'),s=(O.status[id]||[])[i]||'uncertain';
  c.setAttribute('fill',O.colors[s]||'#8a8f98');if(s==='isolated'){iso++;pop+=(O.pop[id]||0)}});
 document.querySelectorAll('text[data-l]').forEach(function(x){var id=x.getAttribute('data-l'),s=(O.status[id]||[])[i]||'uncertain';
  x.textContent=(O.symbols[s]||'')+' '+O.names[id]});
 $('dlabel').textContent=O.dates[i];
 $('icount').textContent=fmt(iso===1?LB.isolated_count_one:LB.isolated_count,{n:loc(iso),d:O.dates[i],p:loc(pop.toLocaleString('en-US'))},true)}
calc();if(O)paint(O.start);
"""


def _json_for_script(obj) -> str:
    """JSON safe to place inside a <script> block (no '<' can close the tag)."""
    return json.dumps(obj, ensure_ascii=False).replace("<", chr(92) + "u003c")


def offline_pack_html(cards: list[dict], L: dict, lang: str, title: str, made_note: str,
                      shelters: list[tuple[str, float, float]] | None = None, supply_days: int = 7,
                      overview: dict | None = None) -> str:
    """Every village's card in one file, with search, GPS village finder, a supplies
    calculator and an SMS help button. Works with no network."""
    e = html.escape
    index = "".join(f"<li><a href='#v-{e(str(c['id']))}'>{e(c['name'])}</a></li>" for c in cards)
    data = {"villages": [{"id": str(c["id"]), "name": c["name"], "lat": c["lat"], "lon": c["lon"]}
                         for c in cards if c.get("lat") is not None],
            "labels": {k: L[k] for k in _PACK_KEYS}, "days": supply_days, "digits": L.get("digits"),
            "rtl": L.get("dir") == "rtl"}
    replay = ""
    if overview and overview["villages"]:
        data["overview"] = {"dates": overview["dates"], "status": overview["status"], "start": overview["start"],
                            "pop": {str(v["id"]): int(v.get("pop") or 0) for v in overview["villages"]},
                            "colors": STATUS_COLORS, "symbols": STATUS_SYMBOLS,
                            "names": {str(v["id"]): v["name"] for v in overview["villages"]}}
        legend = " ".join(f"<span style='color:{STATUS_COLORS[k]}'>&#9679;</span> {STATUS_SYMBOLS[k]} {e(L[k])}&nbsp;&nbsp;"
                          for k in ("connected", "isolated", "uncertain", "boat_dependent"))
        top = max(len(overview["dates"]) - 1, 0)
        replay = (f"<div class='card noprint'><h2>{e(L['overview_title'])}</h2><div class='note'>{e(L['overview_help'])}</div>"
                  f"<input type='range' id='dsl' min='0' max='{top}' value='{overview['start']}' "
                  f"oninput='paint(+this.value)' style='width:100%;margin:10px 0'>"
                  f"<div><b id='dlabel'></b></div><div id='icount' class='note'></div>"
                  f"{overview_svg(overview['villages'], shelters or [], L['overview_title'])}"
                  f"<div class='note' style='margin-top:6px'>{legend}</div></div>")
    script = "<script>" + _PACK_JS.replace("__DATA__", _json_for_script(data)) + "</script>"
    tools = (f"<div class='card noprint'>"
             f"<button onclick='findMe()' style='font-size:1em;padding:10px 16px'>{e(L['pack_find'])}</button>"
             f"<div id='found' class='note'></div>"
             f"<h2>{e(L['calc_title'])}</h2><label>{e(L['calc_people'])} "
             f"<input id='ppl' type='number' min='1' value='5' oninput='calc()' style='width:6em;font-size:1em'></label>"
             f"<div id='calc' class='go'></div>"
             f"<h2>{e(L['help_title'])}</h2>"
             f"<button onclick='helpSms()' style='font-size:1em;padding:10px 16px'>{e(L['help_btn'])}</button>"
             f"<div class='note'>{e(L['help_note'])}</div></div>")
    stages = "".join(
        f"<details{' open' if key == 'before' else ''}><summary><b>{e(L['stage_' + key + '_title'])}</b></summary>"
        f"<ul>{''.join(f'<li>{e(i)}</li>' for i in L['stage_' + key])}</ul></details>"
        for key in ("before", "during", "after"))
    stages = f"<div class='card noprint'><h2>{e(L['stages_title'])}</h2>{stages}</div>"
    places = ""
    if shelters:
        rows = "".join(f"<li>{e(n)}: {la:.5f}, {lo:.5f}</li>" for n, la, lo in shelters)
        places = f"<details class='card noprint'><summary><b>{e(L['shelters_title'])}</b></summary><ul>{rows}</ul></details>"
    body = (f"<h1>{e(title)}</h1>{_draft(L)}<div class='warn'>{e(L['pack_howto'])}</div>"
            f"<p class='note'>{e(made_note)}</p>{replay}{tools}{stages}"
            f"<div class='noprint'><input type='search' placeholder='{e(L['pack_search'])}' oninput='f(this.value)'>"
            f"<ul class='idx' style='padding:0'>{index}</ul></div>{places}"
            + "".join(card_section(c, L) for c in cards)
            + f"<div class='warn'>{e(L['card_disclaimer'])}</div>{script}")
    return _page(lang, title, body, L.get("dir", "ltr"))
