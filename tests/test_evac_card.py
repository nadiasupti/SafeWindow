import re

import pandas as pd
import pytest

from app.streamlit_app import RAW_LOCALES, T, build_card, pack_html, responder_csv, route_for_date, sms_short_text, texts
from safewindow import config, evac_card
from safewindow import region as regions
from safewindow.region import parse

ROUTE = [(91.318, 24.887), (91.320, 24.888), (91.330, 24.900)]
SHELTERS = [(91.330, 24.900, "Pangaon clinic"), (95.0, 30.0, "Far away")]


def card(**over):
    base = {"id": "v1", "name": "Boromuha", "status": "Cut off", "status_kind": "isolated",
            "facts": [("Population", "1,000")], "go": "Go to Pangaon clinic: 3.0 km by road.",
            "walk": "About 0.8 hours on foot.", "svg": evac_card.route_svg((91.318, 24.887), ROUTE, SHELTERS, "Boromuha"),
            "bag": ["Water"], "contacts": [("National Emergency Service", "999")], "sms": "Cut off soon.",
            "sms_parts": "SMS length: 1 message(s)", "tips": ["Leave early."]}
    return {**base, **over}


def test_sms_parts_counts_latin_and_bangla_differently():
    assert evac_card.sms_parts("a" * 160) == 1 and evac_card.sms_parts("a" * 161) == 2
    assert evac_card.sms_parts("ক" * 70) == 1 and evac_card.sms_parts("ক" * 71) == 2
    assert evac_card.sms_parts("ক" * 134) == 2 and evac_card.sms_parts("ক" * 135) == 3


def test_walk_time_uses_four_km_per_hour():
    assert evac_card.walk_hours(6.0) == 1.5


def test_route_svg_draws_route_village_and_only_nearby_shelters():
    svg = evac_card.route_svg((91.318, 24.887), ROUTE, SHELTERS, "Boromuha")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "<polyline" in svg and "Pangaon clinic" in svg and "Boromuha" in svg
    assert "Far away" not in svg                       # outside the map window


def test_route_svg_handles_a_single_point():
    assert "<svg" in evac_card.route_svg((91.3, 24.9), [], [], "Village")


def test_card_escapes_text():
    html = evac_card.card_section(card(name="<script>alert(1)</script>"), texts("en"))
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_card_without_sms_or_contacts_still_helps():
    html = evac_card.card_section(card(sms="", sms_parts="", contacts=[], svg=""), texts("en"))
    assert "Message to send by SMS" not in html
    assert "local disaster-management office" in html


def test_pack_is_self_contained_and_lists_every_village():
    cards = [card(id=f"v{i}", name=f"Village {i}") for i in range(3)]
    html = evac_card.offline_pack_html(cards, texts("en"), "en", "Pack", "note")
    for i in range(3):
        assert f"id='v-v{i}'" in html and f"href='#v-v{i}'" in html
    external = re.findall(r"(?:src|href)=['\"]https?://|url\(|@import|<link|<script[^>]+src", html)
    assert external == []                                  # nothing is fetched from the network


def test_region_emergency_contacts():
    contacts = regions.load("sunamganj_2022").emergency_contacts
    assert contacts[0]["number"] == "999" and contacts[0]["name_bn"] == "জাতীয় জরুরি সেবা"
    raw = {"id": "x", "area": {"admin_names": ["a"]}, "crs": "EPSG:32646",
           "dates": {"flood": ["2022-05-01", "2022-06-01"], "dry_reference": ["2022-02-01", "2022-03-01"]}}
    assert parse(raw, config.ROOT / "x.yaml").emergency_contacts == []
    with pytest.raises(ValueError, match="emergency_contacts"):
        parse({**raw, "emergency_contacts": [{"name": "No number"}]}, config.ROOT / "x.yaml")


def test_short_sms_is_short_and_mentions_the_exit_day():
    v = {"name": "Boromuha", "name_bn": "বড়মুহা", "isolated_from_earliest": pd.Timestamp("2022-05-19"),
         "first_isolated": pd.Timestamp("2022-05-23"), "last_connected": pd.Timestamp("2022-05-18"),
         "safe_exit_date": pd.Timestamp("2022-05-18")}
    en = sms_short_text(v, "Pangaon clinic", "en")
    assert en.isascii() and len(en) <= 160 and "Leave before 18 May." in en
    assert "Leave before" not in sms_short_text({**v, "safe_exit_date": pd.NaT}, None, "en")


@pytest.mark.parametrize("lang", sorted(T))
def test_real_data_cards_and_pack(lang):
    from app.streamlit_app import load
    app_dir = config.get_paths().app
    if not (app_dir / "meta.json").exists():
        pytest.skip("no built app data")
    meta, villages, _s, shelters, routes, _c, _o = load(str(app_dir))
    reg = config.REGION
    t = texts(lang, reg)
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(7, unit="D")
    day = pd.Timestamp(meta["app_end"])
    iso = villages[villages["outcome"] == "isolated"].iloc[0]
    c = build_card(iso, route_for_date(routes, iso["village_id"], day), shelters, reg, lang, t, 7)
    assert c["go"].startswith(t["go_route_last"].split("{")[0])   # an isolated village's route may be cut now
    assert c["status_kind"] == "isolated" and c["sms"] and c["bag"] and len(c["bag"]) == len(T["en"]["bag_items"])
    assert all("{" not in b for b in c["bag"])             # every placeholder was filled
    page = evac_card.village_card_html(c, t, lang, "note")
    assert "<!doctype html>" in page and c["name"] in page
    pack = pack_html(str(app_dir), reg.id, meta["app_end"], lang, 7)
    assert pack.count("<article") == len(villages)


def test_pack_embeds_data_safely_and_has_the_offline_tools():
    cards = [card(id="v1", name="</script><img src=x>", lat=24.9, lon=91.3)]
    html = evac_card.offline_pack_html(cards, texts("en"), "en", "Pack", "note",
                                       [("Clinic </script>", 24.9, 91.3)], supply_days=7)
    script = html[html.index("<script>"):]
    assert script.count("</script>") == 1                       # a village name cannot close the script tag
    assert "\u003c/script>" in script
    for hook in ("findMe()", "helpSms()", "calc()", "navigator.geolocation", "sms:?&body="):
        assert hook in html
    assert "24.90000, 91.30000" in html                        # shelter coordinates are listed


def test_responder_csv_lists_isolated_villages_by_rank():
    from app.streamlit_app import load
    app_dir = config.get_paths().app
    if not (app_dir / "meta.json").exists():
        pytest.skip("no built app data")
    meta, villages, _s, _sh, routes, _c, _o = load(str(app_dir))
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(7, unit="D")
    text = responder_csv(villages, routes, pd.Timestamp(meta["app_end"]))
    lines = text.lstrip(chr(0xFEFF)).strip().splitlines()
    assert lines[0].startswith("rank,village,population,isolated_from")
    assert len(lines) - 1 == int((villages["outcome"] == "isolated").sum())
    ranks = [int(line.split(",")[0]) for line in lines[1:]]
    assert ranks == sorted(ranks)


def _fields(text: str) -> set[str]:
    from string import Formatter
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def test_every_translation_uses_the_same_placeholders_as_english():
    """A mismatched {placeholder} would crash the app in that language."""
    en = RAW_LOCALES["en"]
    for lang, raw in RAW_LOCALES.items():
        assert set(raw) <= set(en), f"{lang}: unknown keys {set(raw) - set(en)}"
        for key, value in raw.items():
            if en[key] is None:                       # optional settings such as date_format
                continue
            if isinstance(value, str):
                supplied = {"sms_template": {"name", "when", "route", "shelter"}, "sms_route": {"km", "shelter"}}
                if lang != "en" and key in ("sms_template", "sms_route"):
                    # other languages name the shelter in the template, so these two differ from English on purpose
                    assert _fields(value) <= supplied[key], f"{lang}.{key}: uses a placeholder the code does not supply"
                    continue
                assert _fields(value) == _fields(en[key]), f"{lang}.{key}: placeholders differ"
            elif isinstance(value, list) and key in ("bag_items", "card_tip_list", "stage_before", "stage_during", "stage_after"):
                assert len(value) == len(en[key]), f"{lang}.{key}: list length differs"
                for a, b in zip(value, en[key]):
                    assert _fields(a) == _fields(b), f"{lang}.{key}: placeholders differ"
        if lang != "en":
            assert raw.get("draft") is True or lang == "bn", f"{lang}: unreviewed translations must be marked draft"
            assert len(raw["months"]) == 12


def test_draft_languages_show_a_notice_on_cards_and_packs():
    t = texts("ne")
    assert t["draft"] and "मस्यौदा" in t["draft_notice"]
    page = evac_card.village_card_html(card(), t, "ne", "note")
    assert t["draft_notice"] in page
    assert texts("en")["draft_notice"] not in evac_card.village_card_html(card(), texts("en"), "en", "note")


def test_dates_follow_the_language_format():
    from app.streamlit_app import fmt_date
    assert fmt_date("2022-06-16", "es") == "16 de junio" and fmt_date("2022-06-16", "fr") == "16 juin"
    assert fmt_date("2022-06-16", "ne") == "१६ जुन"


def test_a_region_without_contacts_falls_back_to_the_international_number():
    from app.streamlit_app import load
    app_dir = config.get_paths().app
    if not (app_dir / "meta.json").exists():
        pytest.skip("no built app data")
    meta, villages, _s, shelters, routes, _c, _o = load(str(app_dir))
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(7, unit="D")
    bare = regions.Region(**{**config.REGION.__dict__, "emergency_contacts": []})
    v = villages.iloc[0]
    c = build_card(v, route_for_date(routes, v["village_id"], pd.Timestamp(meta["app_end"])), shelters, bare, "en", texts("en", bare), 7)
    assert c["contacts"][0][1] == "112"


def _villages(n=3):
    return [{"id": f"v{i}", "name": f"Village {i}", "lat": 24.8 + i * 0.01, "lon": 91.3 + i * 0.01, "pop": 1000 * (i + 1)}
            for i in range(n)]


def test_overview_map_links_every_village_and_keeps_taps_clear():
    svg = evac_card.overview_svg(_villages(), [("Clinic", 24.85, 91.33)], "All villages")
    for i in range(3):
        assert f'href="#v-v{i}"' in svg and f'data-v="v{i}"' in svg
    assert svg.count("<a ") == 3 and 'fill="transparent"' in svg           # a bigger invisible tap target
    assert svg.count('pointer-events="none"') == 3                         # labels cannot swallow a tap
    assert svg.rindex("<text") > svg.rindex("<circle")                     # labels are drawn above the villages


def test_overview_map_drops_labels_for_big_regions_and_escapes_names():
    many = _villages(evac_card.LABEL_LIMIT + 1)
    assert "<text" not in evac_card.overview_svg(many, [], "t")
    nasty = [{"id": 'a"b', "name": "<b>x</b>", "lat": 1.0, "lon": 1.0, "pop": 0}]
    svg = evac_card.overview_svg(nasty, [("<i>s</i>", 1.001, 1.001)], "t")
    assert "<b>x" not in svg and "&lt;b&gt;x" in svg and "<i>s" not in svg and 'href="#v-a&quot;b"' in svg


def test_pack_replay_embeds_every_date_and_stays_offline():
    over = {"villages": _villages(), "dates": ["16 May", "23 May"], "start": 1,
            "status": {"v0": ["connected", "isolated"], "v1": ["uncertain", "isolated"], "v2": ["connected", "connected"]}}
    html = evac_card.offline_pack_html([card(id=v["id"], name=v["name"], lat=v["lat"], lon=v["lon"]) for v in _villages()],
                                       texts("en"), "en", "Pack", "note", [("Clinic", 24.85, 91.33)], 7, over)
    assert "id='dsl'" in html and "max='1'" in html and "value='1'" in html and "function paint" in html
    assert '"dates": ["16 May", "23 May"]' in html and '"v0": ["connected", "isolated"]' in html
    external = re.findall(r"(?:src|href)=['\"]https?://|url\(|@import|<link|<script[^>]+src", html)
    assert external == []


def test_the_pack_still_builds_without_replay_data():
    html = evac_card.offline_pack_html([card(lat=1.0, lon=1.0)], texts("en"), "en", "Pack", "note")
    assert "id='dsl'" not in html and "findMe()" in html


def test_compass_arrows_point_the_right_way():
    a = evac_card.compass_arrow
    assert a(24.0, 91.0, 24.1, 91.0) == "\u2191"          # north
    assert a(24.0, 91.0, 24.0, 91.1) == "\u2192"          # east
    assert a(24.0, 91.0, 23.9, 91.0) == "\u2193"          # south
    assert a(24.0, 91.0, 24.0, 90.9) == "\u2190"          # west
    assert a(24.0, 91.0, 24.1, 91.1) == "\u2197"          # north-east


def test_nearest_facility_is_a_straight_line_choice():
    sites = [("Far hospital", 24.50, 91.00), ("Near clinic", 24.02, 91.01), ("Mid", 24.2, 91.0)]
    name, km, arrow = evac_card.nearest_facility(24.0, 91.0, sites)
    assert name == "Near clinic" and 2.0 < km < 3.0 and arrow in ("\u2191", "\u2197")
    assert evac_card.nearest_facility(24.0, 91.0, []) is None


def test_cards_name_the_nearest_hospital_or_clinic_when_the_data_has_one():
    from app.streamlit_app import load
    app_dir = config.get_paths().app
    if not (app_dir / "meta.json").exists():
        pytest.skip("no built app data")
    meta, villages, _s, shelters, routes, _c, _o = load(str(app_dir))
    villages["aid_deadline"] = villages["isolated_from_earliest"] + pd.to_timedelta(7, unit="D")
    v = villages.iloc[0]
    c = build_card(v, route_for_date(routes, v["village_id"], pd.Timestamp(meta["app_end"])), shelters, config.REGION, "en",
                   texts("en", config.REGION), 7)
    hospitals = {n for n, t_ in zip(shelters["name"], shelters["type"]) if str(t_).lower() in evac_card.HEALTH_TYPES}
    assert c["health"] and any(c["health"].startswith(h) for h in hospitals) and "straight line" in c["health"]
    page = evac_card.village_card_html(c, texts("en"), "en", "note")
    assert "Nearest hospital or clinic" in page


def test_the_pack_has_the_checklist_and_status_symbols_not_just_colours():
    over = {"villages": _villages(), "dates": ["16 May"], "start": 0,
            "status": {"v0": ["connected"], "v1": ["isolated"], "v2": ["uncertain"]}}
    html = evac_card.offline_pack_html([card(id=v["id"], name=v["name"], lat=v["lat"], lon=v["lon"]) for v in _villages()],
                                       texts("en"), "en", "Pack", "note", [], 7, over)
    for key in ("before", "during", "after"):
        assert texts("en")["stage_" + key + "_title"] in html
    assert html.count("<details") == 3 and "<details open>" in html          # "before" starts open
    assert "data-l=" in html and '"symbols"' in html and "\u2715" in html.replace("\\u2715", "\u2715")
    assert '"isolated_count_one"' in html


def test_one_village_uses_the_singular_text_in_every_language():
    for lang, raw in RAW_LOCALES.items():
        assert raw["isolated_count_one"] != raw["isolated_count"] or lang in ("bn", "hi", "ne")
    assert "1 village (" not in texts("en")["isolated_count"] and texts("en")["isolated_count_one"].startswith("{n} village (")


def test_right_to_left_languages_flip_cards_and_packs():
    ur, en = texts("ur"), texts("en")
    assert ur["dir"] == "rtl" and en["dir"] == "ltr" and texts("fr")["dir"] == "ltr"      # others inherit left-to-right
    assert "dir='rtl'" in evac_card.village_card_html(card(), ur, "ur", "note")
    assert "dir='ltr'" in evac_card.village_card_html(card(), en, "en", "note")
    pack = evac_card.offline_pack_html([card(lat=1.0, lon=1.0)], ur, "ur", "Pack", "note")
    assert "dir='rtl'" in pack and "padding-inline-start" in pack and "padding-left" not in pack


def test_urdu_uses_its_own_digits_and_months():
    from app.streamlit_app import fmt_date, local_num
    assert local_num("1,234", "ur") == "۱,۲۳۴" and fmt_date("2022-06-16", "ur") == "۱۶ جون"
