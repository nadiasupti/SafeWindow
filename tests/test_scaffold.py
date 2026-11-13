from datetime import date

import pytest

from safewindow import region as regions
from safewindow import scaffold

ARGS = dict(region_id="lagos_2026", name="Lagos, Nigeria: 2026 flood", bbox=(3.2, 6.4, 3.7, 6.7), iso3="nga",
            country="Nigeria", flood_start=date(2026, 7, 1), flood_end=date(2026, 8, 15))


def test_scaffold_writes_a_region_the_loader_accepts(tmp_path):
    out = scaffold.build(**ARGS, dry_start=date(2026, 1, 10), dry_end=date(2026, 2, 20), languages=["en", "fr"],
                         agencies=["NEMA", "NIHSA"], contacts=[("Emergency", "112")], out_dir=tmp_path)
    region = regions.load(str(out["yaml"]))
    assert region.id == "lagos_2026" and region.iso3 == "NGA" and region.languages == ["en", "fr"]
    assert region.agencies == ["NEMA", "NIHSA"] and region.emergency_contacts == [{"name": "Emergency", "number": "112"}]
    assert region.boundary_file == out["aoi"] and out["aoi"].exists()
    assert not out["warnings"]
    assert out["commands"][0].startswith('$env:SAFEWINDOW_REGION="lagos_2026"')
    assert any("08_build_app_data" in c for c in out["commands"])


def test_missing_dry_reference_defaults_with_a_warning(tmp_path):
    out = scaffold.build(**ARGS, out_dir=tmp_path)
    assert regions.load(str(out["yaml"])).dry_end == "2026-06-30"
    assert out["warnings"] and "dry" in out["warnings"][0]
    assert regions.load(str(out["yaml"])).agencies == [scaffold.DEFAULT_AGENCY]


def test_scaffold_refuses_to_overwrite(tmp_path):
    scaffold.build(**ARGS, out_dir=tmp_path)
    with pytest.raises(FileExistsError):
        scaffold.build(**ARGS, out_dir=tmp_path)


@pytest.mark.parametrize("change,message", [
    ({"region_id": "Lagos 2026"}, "lowercase"),
    ({"bbox": (3.7, 6.4, 3.2, 6.7)}, "west < east"),
    ({"bbox": (3.2, 6.4, 3.7, 96.0)}, "bbox"),
    ({"iso3": "NG"}, "3-letter"),
    ({"flood_start": date(2026, 9, 1)}, "after flood end"),
])
def test_scaffold_rejects_bad_input_and_writes_nothing(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        scaffold.build(**{**ARGS, **change}, out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unknown_language_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="no locale file"):
        scaffold.build(**ARGS, languages=["en", "xx"], out_dir=tmp_path)
