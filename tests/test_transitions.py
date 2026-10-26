import subprocess

import pytest
from pydantic import ValidationError

from cutly.schema.project import ProjectDoc, TimelineClip, Transition, timeline_duration, timeline_starts
from cutly.services.render import ass as A
from cutly.services.render.graph import MediaInfo, RenderOpts, build_plan, slice_timeline

API = "/api/v1"


def clips(*specs):
    return [
        TimelineClip(source_in=a, source_out=b, transition_in=Transition(name=n, dur=d) if n else None)
        for a, b, n, d in specs
    ]


def test_duration_and_starts_account_for_overlap():
    tl = clips((0, 4, None, 0), (10, 14, "fade", 0.5), (20, 22, None, 0))
    assert timeline_starts(tl) == [0.0, 3.5, 7.5]
    assert timeline_duration(tl) == 9.5  # 4 + 4 + 2 - 0.5
    assert ProjectDoc(media_id="m", timeline=tl).duration == 9.5
    assert timeline_duration([]) == 0.0


def test_transition_validation():
    with pytest.raises(ValidationError, match="primer clip"):
        ProjectDoc(media_id="m", timeline=clips((0, 4, "fade", 0.3)))
    with pytest.raises(ValidationError, match="mitad del clip más corto"):
        ProjectDoc(media_id="m", timeline=clips((0, 4, None, 0), (5, 6, "dissolve", 0.8)))
    with pytest.raises(ValidationError):
        Transition(name="no_existe", dur=0.3)
    with pytest.raises(ValidationError):
        Transition(name="fade", dur=5)


def test_subtitle_time_map_uses_overlapped_starts():
    tl = clips((0, 4, None, 0), (10, 14, "fade", 0.5))
    words = [{"w": "uno", "start": 10.2, "end": 10.6}]
    assert A.map_words(words, A.build_time_map(tl)) == [(pytest.approx(3.7), pytest.approx(4.1), "uno")]


def test_slice_timeline_keeps_or_drops_transitions():
    doc = ProjectDoc(media_id="m", timeline=clips((0, 4, None, 0), (10, 14, "fade", 0.5)))
    both = slice_timeline(doc, 0, 7.5)
    assert both[1].transition_in is not None
    only_second = slice_timeline(doc, 3.7, 7.5)
    assert len(only_second) == 2 and only_second[1].transition_in is None  # el primero casi no aparece: sin transición
    assert slice_timeline(doc, 5, 7)[0].id == doc.timeline[1].id


def _plan(tl, audio=True, tmp=None):
    doc = ProjectDoc(media_id="m", timeline=tl)
    return build_plan(doc, MediaInfo("/tmp/x.mp4", 640, 360, True), [], RenderOpts(workdir=tmp, with_audio=audio))


def test_graph_uses_xfade_acrossfade_and_mixes_with_cuts(tmp_path):
    g = _plan(clips((0, 4, None, 0), (10, 14, "slideleft", 0.5), (20, 24, None, 0)), tmp=tmp_path).graph
    assert "xfade=transition=slideleft:duration=0.5:offset=3.5" in g
    assert (
        "acrossfade=d=0.5" in g and "concat=n=2:v=1:a=0" in g and "concat=n=2:v=0:a=1" in g
    )  # el segundo empalme es un corte
    plain = _plan(clips((0, 4, None, 0), (10, 14, None, 0)), tmp=tmp_path).graph
    assert (
        "xfade" not in plain and "concat=n=2:v=1:a=1[vc0][ac]" in plain
    )  # sin transiciones: concat único (más barato)
    assert "[aout]" not in _plan(clips((0, 4, None, 0), (10, 14, "fade", 0.5)), audio=False, tmp=tmp_path).graph


def test_set_transition_op_and_render(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    p = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 1.4, "subtitles": False}
    ).json()
    pid, c1 = p["id"], p["project"]["timeline"][0]["id"]
    r = writer.post(
        f"{API}/projects/{pid}/ops", json={"ops": [{"op": "add_clip", "source_in": 1.5, "source_out": 2.9}]}
    ).json()
    c2 = r["project"]["timeline"][1]["id"]
    assert r["duration"] == 2.8
    bad = writer.post(
        f"{API}/projects/{pid}/ops",
        json={"ops": [{"op": "set_transition", "clip_id": c1, "transition": {"name": "fade", "dur": 0.3}}]},
    )
    assert bad.status_code == 422 and "primer clip" in bad.json()["detail"]
    ok = writer.post(
        f"{API}/projects/{pid}/ops",
        json={"ops": [{"op": "set_transition", "clip_id": c2, "transition": {"name": "fade", "dur": 0.4}}]},
    ).json()
    assert abs(ok["duration"] - 2.4) < 1e-6 and ok["project"]["timeline"][1]["transition_in"] == {
        "name": "fade",
        "dur": 0.4,
    }
    j = writer.get(
        f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft'}).json()['job_id']}"
    ).json()
    assert j["status"] == "done" and j["result"]["warnings"] == [], j
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration",
            "-of",
            "csv=p=0",
            j["result"]["path"],
        ],
        capture_output=True,
        text=True,
    ).stdout
    durs = {line.split(",")[0]: float(line.split(",")[1]) for line in out.split() if "," in line}
    assert abs(durs["video"] - 2.4) < 0.15 and abs(durs["audio"] - 2.4) < 0.2, durs  # 1.4 + 1.4 - 0.4
    # quitarla devuelve la duración completa y deshacer la recupera
    gone = writer.post(
        f"{API}/projects/{pid}/ops", json={"ops": [{"op": "set_transition", "clip_id": c2, "transition": None}]}
    ).json()
    assert gone["duration"] == 2.8
    assert abs(writer.post(f"{API}/projects/{pid}/undo").json()["duration"] - 2.4) < 1e-6
    # un frame en mitad de la transición se puede pedir y sale
    assert writer.get(f"{API}/projects/{pid}/frame", params={"t": 1.2, "quality": "draft"}).status_code == 200
