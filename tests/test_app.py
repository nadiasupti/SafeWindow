import pandas as pd

from app.streamlit_app import T, app_languages, fmt_date, is_default_data_dir, local_num, route_for_date, sms_text, texts
from safewindow import config
from safewindow.region import rain_label


def test_flood_packages_list_the_published_study_first(tmp_path):
    import json
    from app.streamlit_app import flood_packages

    def package(folder, meta):
        (tmp_path / folder / "app").mkdir(parents=True)
        (tmp_path / folder / "app" / "meta.json").write_text(meta, encoding="utf-8")

    package("a_2024", json.dumps({"region": "sunamganj_2024"}))
    package("live", json.dumps({"region": "sunamganj_2022"}))
    package("half_built", "{")                                      # unreadable meta.json
    package("unknown_region", json.dumps({"region": "no_such_region"}))
    packages = flood_packages(tmp_path)
    assert [(rid, folder.name) for rid, folder in packages] == [
        ("sunamganj_2022", "live"), ("sunamganj_2024", "a_2024")]


def test_every_locale_has_the_same_keys_as_english():
    for lang, t in T.items():
        assert set(t) == set(T["en"]), f"{lang}.json differs: {set(t) ^ set(T['en'])}"


def test_region_languages_and_agencies_reach_the_app_text():
    assert app_languages() == ["en", "bn"]
    assert "(BMD, FFWC, DDM)" in texts("en")["limits_text"]
    assert "(BMD, FFWC, DDM)" in texts("bn")["limits_text"]


def test_rain_box_labels_come_from_the_region():
    assert rain_label(config.REGION, "meghalaya_upstream", "bn") == "মেঘালয় পাহাড় (উজান)"
    assert rain_label(config.REGION, "sunamganj", "en") == "Sunamganj"
    assert rain_label(config.REGION, "sunamganj", "ur") == "Sunamganj"      # falls back to English
    assert rain_label(config.REGION, "unknown_box", "en") == "unknown_box"


def test_local_digits_and_dates():
    assert local_num("1,234", "bn") == "১,২৩৪" and local_num("1,234", "en") == "1,234"
    assert fmt_date("2022-06-16", "bn") == "১৬ জুন" and fmt_date("2022-06-16", "en") == "16 Jun"


def test_sms_uses_the_locale_template():
    v = {"name": "Boromuha", "name_bn": "বড়মুহা", "isolated_from_earliest": pd.Timestamp("2022-05-19"),
         "first_isolated": pd.Timestamp("2022-05-23"), "last_connected": pd.Timestamp("2022-05-18")}
    assert sms_text(v, 8.276, "Unnamed hospital", "en") == (
        "Provisional: Boromuha may be isolated during 19 May - 23 May. "
        "Last safe route: 8.3 km by road to Unnamed hospital. Follow official flood alerts.")
    bn = sms_text({**v, "last_connected": pd.NaT}, None, None, "bn")
    assert bn.startswith("সতর্কতা (পরীক্ষামূলক): বড়মুহা এর সড়ক যোগাযোগ ২৩ মে বা তার আগে")
    assert "নিরাপদ পথ: জানা নেই" in bn


def test_is_default_data_dir_uses_environment_selection(monkeypatch):
    paths = config.get_paths()

    monkeypatch.delenv("SAFEWINDOW_DATA_DIR", raising=False)
    assert is_default_data_dir(paths)

    monkeypatch.setenv("SAFEWINDOW_DATA_DIR", "data_demo")
    assert not is_default_data_dir(paths)


def test_route_for_date_uses_only_routes_available_on_or_before_selection():
    routes = pd.DataFrame({
        "village_id": ["v1", "v1"],
        "date": pd.to_datetime(["2022-06-07", "2022-06-14"]),
        "shelter_id": ["s1", "s2"],
        "shelter_name": ["Shelter 1", "Shelter 2"],
        "length_m": [1000, 2000],
    })

    selected = route_for_date(routes, "v1", pd.Timestamp("2022-06-10"))

    assert len(selected) == 1
    assert selected.iloc[0]["shelter_id"] == "s1"
    assert selected.iloc[0]["length_m"] == 1000
