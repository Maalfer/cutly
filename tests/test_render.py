import json
import re
import subprocess
from pathlib import Path

import pytest
from sqlmodel import Session

from cutly.db.models import Transcript
from cutly.db.session import get_engine
from cutly.schema.project import (
    Anim,
    Animations,
    IconLayer,
    ProjectDoc,
    Rect,
    Reframe,
    SubtitleLayer,
    TextLayer,
    TimelineClip,
)
from cutly.services.render import ass as A
from cutly.services.render.graph import (
    MediaInfo,
    RenderOpts,
    atempo_chain,
    build_measure_command,
    build_plan,
    gain_from_loudness,
    safe_path,
)

API = "/api/v1"


def test_ass_escape_neutralizes_injection():
    assert "{" not in A.ass_escape("{\\pos(0,0)}hola") and "\\" not in A.ass_escape("a\\Nb\\h")
    assert A.ass_escape("línea1\nlínea2") == "línea1 línea2"
    assert A.ass_color("#FF8000") == "&H000080FF" and A.ass_color("#FF800080").startswith("&H7F")
    assert A.ass_time(3661.5) == "1:01:01.50"


def test_time_map_speed_and_gaps():
    tm = A.build_time_map(
        [TimelineClip(source_in=10, source_out=20, speed=2), TimelineClip(source_in=100, source_out=104)]
    )
    words = [
        {"w": "a", "start": 10, "end": 10.4},
        {"w": "x", "start": 50, "end": 51},
        {"w": "b", "start": 101, "end": 102},
    ]
    assert A.map_words(words, tm) == [(0.0, pytest.approx(0.2), "a"), (6.0, 7.0, "b")]  # "x" cae fuera: se descarta


def test_group_cues_breaks_on_pause_and_sentence():
    ws = [(0, 0.3, "Hola"), (0.35, 0.6, "amigos."), (0.7, 1.0, "Hoy"), (3.0, 3.3, "otra"), (3.4, 3.6, "vez")]
    assert [[w[2] for w in c] for c in A.group_cues(ws, 4)] == [["Hola", "amigos."], ["Hoy"], ["otra", "vez"]]


def test_atempo_chain_and_loudness_parsing():
    assert atempo_chain(1) == "" and atempo_chain(1.5) == "atempo=1.5"
    assert atempo_chain(4) == "atempo=2.0,atempo=2" and atempo_chain(0.25) == "atempo=0.5,atempo=0.5"
    assert gain_from_loudness("  I:         -20.0 LUFS\n  Peak:  -3 dBFS", -14) == 6.0
    assert gain_from_loudness("  I:         -70.0 LUFS", -14) is None  # silencio: no amplificar
    assert gain_from_loudness("I:  -40 LUFS", -14) == 20.0  # tope de ganancia
    assert gain_from_loudness("sin datos", -14) is None


def test_safe_path_rejects_filter_metacharacters():
    for bad in ["/tmp/a'b.png", "/tmp/a:b", "/tmp/a,b", "/tmp/a;b", "/tmp/a b"]:
        with pytest.raises(ValueError):
            safe_path(bad)


def _media():
    return MediaInfo("/tmp/x.mp4", 1920, 1080, True)


def test_graph_structure(tmp_path):
    doc = ProjectDoc(
        media_id="m",
        timeline=[TimelineClip(source_in=1, source_out=5), TimelineClip(source_in=20, source_out=23, speed=1.5)],
        reframe=Reframe(mode="stack", facecam=Rect(x=0.7, y=0, w=0.3, h=0.3), game=Rect(x=0, y=0, w=0.7, h=1)),
        layers=[
            SubtitleLayer(end=6, z=50),
            TextLayer(end=3, text="Hola", z=10),
            IconLayer(start=1, end=3, asset="icons/star", z=20, animations=Animations(enter=Anim(name="slide_up"))),
        ],
    )
    words = [{"w": "hola", "start": 2.0, "end": 2.4}, {"w": "mundo", "start": 2.5, "end": 2.9}]
    plan = build_plan(doc, _media(), words, RenderOpts(workdir=tmp_path), norm_gain_db=5)
    g = plan.graph
    assert (
        plan.inputs.count("-ss") == 2 and "-start_number" in plan.inputs
    )  # un trozo por clip + icono animado (secuencia)
    assert "concat=n=2:v=1:a=1[vc0][ac]" in g and "vstack" in g and "atempo=1.5" in g
    assert (
        "volume=5dB" in g and "alimiter=limit=0.7499" in g and "loudnorm" not in g
    )  # normalización medida, no loudnorm
    # orden por z: texto (10) → ass, icono (20) → overlay, subtítulos (50) → ass
    assert g.index("ass=") < g.index("overlay=") < g.rindex("ass=")
    assert plan.duration == pytest.approx(4 + 2) and (plan.width, plan.height) == (1080, 1920)
    assert len(list(tmp_path.glob("layers*.ass"))) == 2


def test_draft_scales_output_and_no_audio_source(tmp_path):
    doc = ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=0, source_out=3)])
    plan = build_plan(doc, MediaInfo("/tmp/x.mp4", 1920, 1080, False), [], RenderOpts(workdir=tmp_path, draft=True))
    assert (plan.width, plan.height) == (360, 640) and "anullsrc" in plan.graph
    cmd = build_measure_command(doc, MediaInfo("/tmp/x.mp4", 1920, 1080, True), tmp_path)
    assert "-vn" in cmd and "ebur128" in (tmp_path / "measure.txt").read_text()


def test_effect_layers_are_applied_and_unknown_ones_warn(tmp_path):
    from cutly.schema.project import EffectLayer

    doc = ProjectDoc(
        media_id="m",
        timeline=[TimelineClip(source_in=0, source_out=3)],
        layers=[EffectLayer(end=2, effect="zoom_punch")],
    )
    plan = build_plan(doc, _media(), [], RenderOpts(workdir=tmp_path))
    assert plan.warnings == [] and "eval=frame" in plan.graph  # el efecto del registro entra en el grafo
    doc.layers = [EffectLayer(end=2, effect="no_existe")]
    plan = build_plan(doc, _media(), [], RenderOpts(workdir=tmp_path))
    assert any(
        "no_existe" in w and "ignorado" in w for w in plan.warnings
    )  # un efecto desconocido avisa, no rompe el render


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {s["codec_type"]: s for s in json.loads(out)["streams"]}


def test_render_end_to_end_via_api(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    with Session(get_engine()) as s:
        words = [{"w": f"palabra{i}", "start": 0.3 + i * 0.4, "end": 0.65 + i * 0.4, "p": 1} for i in range(6)]
        s.add(Transcript(media_id=mid, segments=[{"id": 0, "start": 0.3, "end": 2.7, "text": "x", "words": words}]))
        s.commit()
    p = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0.2, "source_out": 2.8}).json()
    pid = p["id"]
    assert any(layer["type"] == "subtitle" for layer in p["project"]["layers"])
    ops = [
        {
            "op": "add_layer",
            "layer": {"type": "text", "end": 2, "text": "Hola {\\evil}", "style": {"color": "#FFD400"}},
        },
        {
            "op": "add_layer",
            "layer": {
                "type": "icon",
                "start": 0.5,
                "end": 2,
                "asset": "icons/arrow-right",
                "box": {"x": 0.8, "w": 0.2},
            },
        },
        {
            "op": "add_layer",
            "layer": {"type": "shape", "end": 2, "shape": "ellipse", "fill": None, "stroke": "#FF3B30"},
        },
    ]
    assert writer.post(f"{API}/projects/{pid}/ops", json={"ops": ops}).status_code == 200

    j = writer.get(
        f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft'}).json()['job_id']}"
    ).json()
    assert j["status"] == "done", j
    res = j["result"]
    assert (res["width"], res["height"], res["quality"]) == (360, 640, "draft") and res["warnings"] == []
    r = writer.get(f"{API}/renders/{j['id']}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    out = Path(res["path"])
    st = probe(out)
    assert st["video"]["codec_name"] == "h264" and (st["video"]["width"], st["video"]["height"]) == (360, 640)
    assert st["audio"]["codec_name"] == "aac" and abs(float(st["video"]["duration"]) - 2.6) < 0.2
    assert not list(out.parent.parent.glob("tmp/*"))  # el directorio temporal se limpia
    listed = writer.get(f"{API}/projects/{pid}/renders").json()
    assert listed[0]["job_id"] == j["id"] and "path" not in (listed[0]["result"] or {})

    # render final (con la pasada de medición de volumen)
    j2 = writer.get(f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render').json()['job_id']}").json()
    assert j2["status"] == "done" and (j2["result"]["width"], j2["result"]["height"]) == (1080, 1920)
    # borrar el proyecto elimina también sus renders en disco
    assert out.exists()
    assert writer.delete(f"{API}/projects/{pid}").status_code == 200 and not out.exists()
    pid = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0.2, "source_out": 2.8}).json()["id"]
    # render de todos los proyectos del vídeo
    assert list(writer.post(f"{API}/media/{mid}/render-all", json={"quality": "draft"}).json()["jobs"]) == [pid]


def test_render_requires_clips_and_ready_state(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    p = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 2}).json()
    cid = p["project"]["timeline"][0]["id"]
    writer.post(f"{API}/projects/{p['id']}/ops", json={"ops": [{"op": "delete_clip", "clip_id": cid}]})
    r = writer.post(f"{API}/projects/{p['id']}/render")
    assert r.status_code == 422 and "add_clip" in r.json()["detail"]
    assert writer.get(f"{API}/renders/j_nope/download").status_code == 404


def _lufs(path):
    r = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-i",
            str(path),
            "-vn",
            "-af",
            "ebur128=peak=true:framelog=quiet",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    return float(re.findall(r"I:\s+(-?[0-9.]+)\s+LUFS", r.stderr)[-1]), float(
        re.findall(r"Peak:\s+(-?[0-9.]+)\s+dBFS", r.stderr)[-1]
    )


def test_render_really_normalizes_audio_to_target(writer, sample_video):
    """Regresión: el handler de render perdió la pasada de medición y NINGÚN render normalizaba el audio."""
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    pid = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 2.8, "subtitles": False}
    ).json()["id"]
    original, _ = _lufs(sample_video)
    assert original < -18  # la fuente de prueba es bastante más baja que -14

    def render_lufs(target):
        writer.post(
            f"{API}/projects/{pid}/ops",
            json={"ops": [{"op": "set_audio", "patch": {"target_lufs": target, "normalize": True}}]},
        )
        j = writer.get(
            f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft'}).json()['job_id']}"
        ).json()
        assert j["status"] == "done" and j["result"]["warnings"] == [], j
        return _lufs(j["result"]["path"])

    lufs, peak = render_lufs(-14)
    assert abs(lufs - (-14)) < 1.5 and peak <= -0.9, (lufs, peak)  # llega al objetivo y respeta el pico
    quiet, _ = render_lufs(-20)
    assert abs(quiet - (-20)) < 1.5 and quiet < lufs - 4
    writer.post(f"{API}/projects/{pid}/ops", json={"ops": [{"op": "set_audio", "patch": {"normalize": False}}]})
    j = writer.get(
        f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft'}).json()['job_id']}"
    ).json()
    assert abs(_lufs(j["result"]["path"])[0] - original) < 1.5  # sin normalizar, no se toca


def test_normalized_audio_never_exceeds_true_peak_even_with_spiky_material(writer, tmp_path):
    """Regresión: con el limitador justo en −1 dB, AAC y los picos entre muestras daban +0,6 dBFS en un directo real.
    Señal con crestas fuertes (voz baja + chasquidos): al subirla a −14 LUFS los picos exigen el limitador."""
    src = tmp_path / "spiky.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=4",
         "-f", "lavfi", "-i", "aevalsrc='0.03*sin(2*PI*220*t)+0.9*lt(mod(t,0.4),0.0006)':s=48000:d=4",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src)],
        check=True,
    )  # fmt: skip
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=src.read_bytes()).json()["media_id"]
    pid = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 3.5, "subtitles": False}
    ).json()["id"]
    j = writer.get(
        f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft'}).json()['job_id']}"
    ).json()
    assert j["status"] == "done", j
    lufs, peak = _lufs(j["result"]["path"])
    assert peak <= -0.9, f"pico {peak} dBFS por encima del límite (volumen {lufs} LUFS)"
