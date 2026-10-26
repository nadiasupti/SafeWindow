import pytest

from app.streamlit_app import CREDITS, LEAFLET_DIR, LEAFLET_URL, RESPONSIVE_CSS, basemap_layers, legend_html, texts, tip, use_local_leaflet
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("make_deploy_bundle", Path(__file__).resolve().parent.parent / "scripts" / "make_deploy_bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def fake_repo(root: Path, floods=("live", "flood_b")) -> Path:
    for rel, text in {"app/streamlit_app.py": "x", "app/floodnet_app.py": "torch", "safewindow/__init__.py": "",
                      "safewindow/a.py": "", "locales/en.json": "{}", "regions/r.yaml": "id: r", "requirements.txt": "streamlit",
                      ".streamlit/config.toml": "[server]", "LICENSE": "MIT",
                      "app/static/vendor/leaflet/leaflet.js": "L"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for f in floods:
        (root / "data" / f / "app").mkdir(parents=True)
        (root / "data" / f / "app" / "meta.json").write_text("{}")
        (root / "data" / f / "raw").mkdir()
        (root / "data" / f / "raw" / "huge.tif").write_text("x" * 1000)
    return root


def test_tooltips_cannot_inject_html():
    assert tip("<img src=x onerror=alert(1)>") == "&lt;img src=x onerror=alert(1)&gt;"
    assert tip("Dholkotob & Co") == "Dholkotob &amp; Co"


def test_basemap_defaults_and_override():
    default = basemap_layers({})
    assert len(default) == 2 and "arcgisonline" in default[0]["tiles"]
    custom = basemap_layers({"SAFEWINDOW_TILE_URL": "https://tiles.example/{z}/{x}/{y}.png", "SAFEWINDOW_TILE_ATTR": "Example"})
    assert custom == [{"tiles": "https://tiles.example/{z}/{x}/{y}.png", "attr": "Example", "name": "Base map"}]


def test_bundle_has_the_runtime_files_and_leaves_out_raw_data(tmp_path):
    root = fake_repo(tmp_path / "repo")
    info = bundle.build(tmp_path / "out", root=root)
    out = tmp_path / "out"
    assert info["floods"] == ["flood_b", "live"]
    for rel in ("app/streamlit_app.py", "safewindow/a.py", "locales/en.json", "regions/r.yaml", "requirements.txt",
                ".streamlit/config.toml", "Dockerfile", "data/live/app/meta.json", "LICENSE"):
        assert (out / rel).exists(), rel
    assert not (out / "app" / "floodnet_app.py").exists()          # the experimental torch app is not shipped
    assert not any(out.rglob("huge.tif"))                          # raw satellite data stays out
    docker = (out / "Dockerfile").read_text()
    assert '"app/streamlit_app.py"' in docker and "USER app" in docker      # runs the app as a non-root user


def test_bundle_can_pick_floods_and_rebuilds_cleanly(tmp_path):
    root = fake_repo(tmp_path / "repo")
    bundle.build(tmp_path / "out", ["live"], root=root)
    assert not (tmp_path / "out" / "data" / "flood_b").exists()
    bundle.build(tmp_path / "out", ["flood_b"], root=root)         # an earlier bundle is replaced
    assert (tmp_path / "out" / "data" / "flood_b").exists() and not (tmp_path / "out" / "data" / "live").exists()


def test_bundle_refuses_foreign_folders_and_unknown_floods(tmp_path):
    root = fake_repo(tmp_path / "repo")
    (tmp_path / "mine").mkdir()
    (tmp_path / "mine" / "precious.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        bundle.build(tmp_path / "mine", root=root)
    assert (tmp_path / "mine" / "precious.txt").exists()           # nothing was deleted
    with pytest.raises(ValueError, match="no built app package"):
        bundle.build(tmp_path / "out", ["nope"], root=root)


def test_a_failed_rebuild_keeps_the_previous_bundle(tmp_path):
    root = fake_repo(tmp_path / "repo")
    bundle.build(tmp_path / "out", ["live"], root=root)
    (root / "locales" / "en.json").unlink()
    (root / "locales").rmdir()                                      # the copy of locales/ will now fail
    with pytest.raises(FileNotFoundError):
        bundle.build(tmp_path / "out", ["live"], root=root)
    assert (tmp_path / "out" / "data" / "live" / "app" / "meta.json").exists()   # old bundle restored
    assert not (tmp_path / "out.previous").exists()


def test_a_typo_in_floods_does_not_destroy_the_existing_bundle(tmp_path):
    root = fake_repo(tmp_path / "repo")
    bundle.build(tmp_path / "out", ["live"], root=root)
    with pytest.raises(ValueError, match="no built app package"):
        bundle.build(tmp_path / "out", ["lvie"], root=root)
    assert (tmp_path / "out" / "data" / "live" / "app" / "meta.json").exists()


def test_data_credits_name_the_licences_that_require_attribution():
    assert "OpenStreetMap contributors" in CREDITS and "ODbL" in CREDITS and "WorldPop" in CREDITS


def test_bundle_ships_the_local_map_library_and_offline_launchers(tmp_path):
    out = tmp_path / "out"
    bundle.build(out, root=fake_repo(tmp_path / "repo"))
    assert (out / "app" / "static" / "vendor" / "leaflet" / "leaflet.js").exists()
    bat = (out / "run_offline.bat").read_bytes()
    assert b"SAFEWINDOW_OFFLINE=1" in bat and b"--no-index" in bat and b"\r\n" in bat      # Windows line endings
    sh = (out / "run_offline.sh").read_text()
    assert "SAFEWINDOW_OFFLINE=1" in sh and "--no-index" in sh and "wheels" in sh
    assert not (out / "wheels").exists()                            # only with --wheels


def test_wheels_flag_downloads_every_package(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(bundle.subprocess, "run", lambda cmd, check: calls.append(cmd))
    bundle.build(tmp_path / "out", root=fake_repo(tmp_path / "repo"), wheels=True)
    assert calls and calls[0][1:4] == ["-m", "pip", "download"] and "-d" in calls[0]


def test_a_failed_wheel_download_restores_the_previous_bundle(tmp_path, monkeypatch):
    import subprocess
    root = fake_repo(tmp_path / "repo")
    bundle.build(tmp_path / "out", ["live"], root=root)

    def offline(cmd, check):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(bundle.subprocess, "run", offline)
    with pytest.raises(subprocess.CalledProcessError):
        bundle.build(tmp_path / "out", ["flood_b"], root=root, wheels=True)
    assert (tmp_path / "out" / "data" / "live" / "app" / "meta.json").exists()


def test_the_map_uses_leaflet_from_this_app_not_a_cdn():
    import folium
    m = use_local_leaflet(folium.Map(location=[0, 0], tiles=None))
    urls = [u for _, u in m.default_js] + [u for _, u in m.default_css]
    assert urls and all(u.startswith(LEAFLET_URL) for u in urls) and not any("http" in u for u in urls)


def test_every_local_map_file_exists_and_the_image_folder_is_set_explicitly():
    import folium
    m = use_local_leaflet(folium.Map(location=[0, 0], tiles=None))
    for _, url in [*m.default_js, *m.default_css]:
        assert (LEAFLET_DIR / url.rsplit("/", 1)[1]).is_file(), url
    paths = (LEAFLET_DIR / "safewindow-paths.js").read_text()
    assert "imagePath" in paths and f"{LEAFLET_URL}/images/" in paths
    for image in ("marker-icon.png", "marker-shadow.png", "layers.png"):
        assert (LEAFLET_DIR / "images" / image).is_file()
    assert (LEAFLET_DIR / "LICENSE").is_file()                       # Leaflet's BSD licence travels with it


def test_the_stylesheet_covers_phones_tablets_and_very_wide_screens():
    css = RESPONSIVE_CSS
    assert "clamp(300px, 62vh, 760px)" in css and "streamlit_folium.st_folium" in css      # map height follows the screen
    assert "max-width: 640px" in css and "pointer: coarse" in css and "prefers-reduced-motion" in css
    assert "max-width: 1400px" in css                                                       # lines stay readable on a huge monitor
    assert "min-height: 44px" in css and "scale(1.5)" in css                                # finger-sized controls


def test_the_legend_wraps_on_a_narrow_screen_and_keeps_every_status():
    html = legend_html(texts("en"))
    assert "nowrap" not in html and "max-width:100%" in html
    for symbol in ("\u2713", "\u2715", "?", "~"):
        assert symbol in html
    assert all(texts("en")[k] in html for k in ("connected", "isolated", "uncertain", "boat_dependent", "flood", "no_data"))


def test_cards_and_the_pack_scale_with_system_text_and_suit_dark_phones():
    from safewindow import evac_card
    css = evac_card._CSS
    assert "font-size:1.0625rem" in css and "font-size:17px" not in css                    # large-text settings work
    assert "prefers-color-scheme:dark" in css and "safe-area-inset" in css
    assert css.count("min-height:44px") >= 3                                                # buttons, summaries, number box
    page = evac_card._page("en", "t", "<p>x</p>")
    assert "viewport-fit=cover" in page and "color-scheme" in page
