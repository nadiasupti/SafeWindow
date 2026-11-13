"""Reading shelters and health facilities from an OpenStreetMap extract (a tiny file written here)."""
import pytest

osmium = pytest.importorskip("osmium")

from safewindow import health, osm_pbf  # noqa: E402
from safewindow.places import SHELTER_COLS  # noqa: E402


@pytest.fixture()
def pbf(tmp_path):
    path = tmp_path / "t.osm.pbf"
    with osmium.SimpleWriter(str(path)) as w:
        w.add_node(osmium.osm.mutable.Node(id=1, location=(85.0, 26.7), tags={"amenity": "school", "name": "Hill School"}))
        w.add_node(osmium.osm.mutable.Node(id=2, location=(85.1, 26.8), tags={"amenity": "hospital", "name:en": "Bara Hospital", "name": "x"}))
        w.add_node(osmium.osm.mutable.Node(id=3, location=(10.0, 10.0), tags={"amenity": "hospital", "name": "Far Away"}))
        w.add_node(osmium.osm.mutable.Node(id=4, location=(85.0, 26.6), tags={"amenity": "bench"}))
        for i, (lo, la) in enumerate([(85.2, 26.6), (85.22, 26.6), (85.22, 26.62), (85.2, 26.62)], start=10):
            w.add_node(osmium.osm.mutable.Node(id=i, location=(lo, la)))
        w.add_way(osmium.osm.mutable.Way(id=20, nodes=[10, 11, 12, 13, 10], tags={"amenity": "clinic", "healthcare": "clinic"}))
    return path


BBOX = (84.7, 26.55, 85.25, 26.95)


def test_elements_inside_bbox_only(pbf):
    ids = {e["id"] for e in osm_pbf.elements(pbf, BBOX)}
    assert ids == {1, 2, 20}              # the far hospital and the bench are left out


def test_way_gets_its_centre(pbf):
    way = next(e for e in osm_pbf.elements(pbf, BBOX) if e["id"] == 20)
    assert way["center"]["lat"] == pytest.approx(26.608, abs=0.02) and way["center"]["lon"] == pytest.approx(85.208, abs=0.02)


def test_shelter_frame_has_pipeline_columns(pbf):
    frame = osm_pbf.shelter_frame(osm_pbf.elements(pbf, BBOX))
    assert list(frame.columns) == SHELTER_COLS
    assert set(frame["type"]) == {"school", "hospital", "clinic"}
    assert (frame["source"] == "OpenStreetMap").all() and (frame["verified"] == "").all()


def test_health_fetch_builds_package(pbf, tmp_path):
    got = health.build(tmp_path, object(), None, BBOX, fetch=osm_pbf.health_fetch(pbf))
    assert got == {"source": "osm", "n": 2}
    names = {n for n, _, _ in health.read(tmp_path)}
    assert len(names) == 2 and "Bara Hospital" in names
