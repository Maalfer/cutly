"""ripple_delete, auto-cut, dry_run y summary: edición por tramos con las capas recolocadas."""

import pytest
from sqlmodel import Session

from cutly.db.models import Transcript
from cutly.db.session import get_engine
from cutly.schema.ops import OpError, ripple_delete
from cutly.schema.project import ProjectDoc, TextLayer, TimelineClip

API = "/api/v1"


def doc_with(*clips, layers=()):
    return ProjectDoc(media_id="m_x", timeline=list(clips), layers=list(layers))


def text(id, start, end):
    return TextLayer(id=id, start=start, end=end, text="x")


def test_ripple_inside_one_clip_splits_it_and_shifts_layers():
    d = doc_with(
        TimelineClip(id="c1", source_in=10, source_out=20),
        layers=[text("antes", 0, 2), text("dentro", 4, 5), text("cruza", 3, 8), text("despues", 7, 9)],
    )
    ripple_delete(d, 3.0, 6.0)  # quita 3 s del resultado
    assert [(c.source_in, c.source_out) for c in d.timeline] == [(10, 13), (16, 20)]
    assert d.duration == pytest.approx(7.0)
    got = {x.id: (x.start, x.end) for x in d.layers}
    assert "dentro" not in got  # estaba entera dentro del tramo
    assert got["antes"] == (0, 2) and got["cruza"] == (3, 5) and got["despues"] == (4, 6)


def test_ripple_across_clips_and_with_speed():
    d = doc_with(
        TimelineClip(id="c1", source_in=0, source_out=4),  # sale 0-4
        TimelineClip(id="c2", source_in=100, source_out=108, speed=2.0),  # sale 4-8
    )
    ripple_delete(d, 3.0, 5.0)
    c1, c2 = d.timeline
    assert (c1.source_in, c1.source_out) == (0, 3)
    assert (c2.source_in, c2.source_out) == (102, 108) and c2.transition_in is None  # 1 s de salida = 2 s de origen
    assert d.duration == pytest.approx(6.0)


def test_ripple_whole_clip_and_errors():
    d = doc_with(TimelineClip(id="c1", source_in=0, source_out=2), TimelineClip(id="c2", source_in=5, source_out=9))
    ripple_delete(d, 0.0, 2.0)
    assert [c.id for c in d.timeline] == ["c2"]
    with pytest.raises(OpError):
        ripple_delete(d, 1.0, 1.0)


@pytest.fixture
def project(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()["media_id"]
    words = [
        {"w": "hola", "start": 0.5, "end": 0.8, "p": 1},
        {"w": "amigos", "start": 0.9, "end": 1.2, "p": 1},
        {"w": "eh", "start": 1.3, "end": 1.5, "p": 1},
        {"w": "vamos", "start": 2.3, "end": 2.6, "p": 1},  # pausa de 0,8 s antes
    ]
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=mid, segments=[{"id": 0, "start": 0.5, "end": 2.6, "text": "x", "words": words}]))
        s.commit()
    p = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0.0, "source_out": 2.9}).json()
    writer.post(f"{API}/projects/{p['id']}/layers", json={"layer": {"type": "text", "id": "t1", "start": 2.3, "end": 2.8, "text": "Vamos"}})
    return p["id"]


def test_ripple_op_dry_run_and_summary(writer, project):
    ops = {"ops": [{"op": "ripple_delete", "start": 1.0, "end": 2.0}]}
    dry = writer.post(f"{API}/projects/{project}/ops", params={"dry_run": "true"}, json=ops).json()
    assert dry["dry_run"] and dry["duration_after"] == pytest.approx(1.9)
    assert writer.get(f"{API}/projects/{project}/summary").json()["duration"] == pytest.approx(2.9)  # nada guardado
    r = writer.post(f"{API}/projects/{project}/ops", json=ops).json()
    assert r["duration"] == pytest.approx(1.9)
    s = writer.get(f"{API}/projects/{project}/summary").json()
    layer = next(x for x in s["layers"] if x["id"] == "t1")
    assert (layer["start"], layer["end"]) == (1.3, 1.8) and len(s["clips"]) == 2 and s["clips"][1]["out_start"] == 1.0
    bad = writer.post(f"{API}/projects/{project}/ops", params={"dry_run": "true"}, json={"ops": [{"op": "ripple_delete", "start": 50, "end": 60}]})
    assert bad.status_code == 422


def test_auto_cut_proposes_then_applies_in_one_undoable_step(writer, project):
    prop = writer.post(f"{API}/projects/{project}/auto-cut", json={}).json()
    assert prop["dry_run"] and prop["count"] >= 2
    reasons = " | ".join(c["reason"] for c in prop["cuts"])
    assert "silencio inicial" in reasons and "muletilla" in reasons
    assert writer.get(f"{API}/projects/{project}/summary").json()["duration"] == pytest.approx(2.9)
    done = writer.post(f"{API}/projects/{project}/auto-cut", json={"dry_run": False}).json()
    assert not done["dry_run"] and done["duration_after"] < 2.0
    s = writer.get(f"{API}/projects/{project}/summary").json()
    assert s["duration"] == pytest.approx(done["duration_after"], abs=0.01)
    # una sola entrada de historial: un undo lo devuelve todo
    assert writer.post(f"{API}/projects/{project}/undo").json()["duration"] == pytest.approx(2.9)
    none = writer.post(f"{API}/projects/{project}/auto-cut", json={"fillers": [], "trim_edges": False, "silence_min": 5}).json()
    assert none["count"] == 0


def test_autopilot_plans_then_applies_one_undoable_step(writer, project):
    plan = writer.post(f"{API}/projects/{project}/autopilot", json={"punch_ins": True}).json()
    assert plan["dry_run"] and plan["ok"] and any("cortes" in s for s in plan["steps"])
    assert writer.get(f"{API}/projects/{project}/summary").json()["duration"] == pytest.approx(2.9)  # solo plan
    done = writer.post(f"{API}/projects/{project}/autopilot", json={"dry_run": False, "subtitle_preset": "subtitle:bold_caps_pop"}).json()
    assert not done["dry_run"] and done["duration_after"] < 2.0
    s = writer.get(f"{API}/projects/{project}/summary").json()
    assert any(x["type"] == "subtitle" for x in s["layers"])
    assert writer.post(f"{API}/projects/{project}/undo").json()["duration"] == pytest.approx(2.9)
    bad = writer.post(f"{API}/projects/{project}/autopilot", json={"subtitle_preset": "subtitle:nope"})
    assert bad.status_code == 422


def test_repeats_and_pacing(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()["media_id"]
    words = [
        {"w": "es", "start": 0.2, "end": 0.4, "p": 1}, {"w": "que", "start": 0.45, "end": 0.6, "p": 1},
        {"w": "es", "start": 0.7, "end": 0.9, "p": 1}, {"w": "que", "start": 0.95, "end": 1.1, "p": 1},
        {"w": "vamos", "start": 1.2, "end": 1.6, "p": 1},
    ]
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=mid, segments=[{"id": 0, "start": 0.2, "end": 1.6, "text": "x", "words": words}]))
        s.commit()
    pid = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0.0, "source_out": 2.9}).json()["id"]
    cuts = writer.post(f"{API}/projects/{pid}/auto-cut", json={"trim_edges": False, "silence_min": 9}).json()["cuts"]
    assert any("repetición «es que»" in c["reason"] for c in cuts)
    assert not writer.post(f"{API}/projects/{pid}/auto-cut", json={"trim_edges": False, "silence_min": 9, "repeats": False}).json()["cuts"]
    r = writer.get(f"{API}/projects/{pid}/pacing", params={"max_static": 2})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["words"] == 5 and p["static_spans"] and "hook_says" in p


def test_autopilot_pro_style_uses_trails_and_whoosh(writer, project):
    plan = writer.post(f"{API}/projects/{project}/autopilot", json={"pro": True, "max_static": 0.5}).json()
    assert plan["ok"], plan
    done = writer.post(f"{API}/projects/{project}/autopilot", json={"pro": True, "max_static": 0.5, "dry_run": False}).json()
    types = [(x["type"], x.get("label")) for x in writer.get(f"{API}/projects/{project}/summary").json()["layers"]]
    layers = writer.get(f"{API}/projects/{project}").json()["project"]["layers"]
    effects = {x["effect"] for x in layers if x["type"] == "effect"}
    assert "zoom_punch" not in effects, (effects, types)
    if any("whoosh" in s for s in done["steps"]):
        assert any(x["type"] == "audio" and x["sfx"] == "whoosh_fast" for x in layers)
