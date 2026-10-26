import io
import subprocess

import pytest
from PIL import Image
from sqlmodel import Session

from cutly.db.models import Transcript
from cutly.db.session import get_engine
from cutly.schema.project import (
    Box,
    IconLayer,
    ProjectDoc,
    Rect,
    Reframe,
    SubtitleLayer,
    TextLayer,
    TimelineClip,
)
from cutly.services.verify import audio as audio_mod
from cutly.services.verify.checks import check_audio, check_cuts, check_faces, check_layers, run_checks
from cutly.services.verify.geometry import Frame, layer_rect, source_rect_to_output

API = "/api/v1"


def doc_with(*layers, dur=10.0, **kw):
    return ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=0, source_out=dur)], layers=list(layers), **kw)


# --- geometría ----------------------------------------------------------------------------------------------------------


def test_layer_rects_and_reframe_mapping():
    txt = TextLayer(end=5, text="Hola mundo", box=Box(x=0.5, y=0.2, w=0.8))
    r = layer_rect(txt, 1080, 1920)
    assert r and 0.1 < r[0] < 0.5 < r[2] < 0.95 and r[1] < 0.2 < r[3]
    icon = IconLayer(end=5, asset="icons/star", box=Box(x=0.5, y=0.5, w=0.2))
    ri = layer_rect(icon, 1080, 1920)
    assert ri and abs((ri[3] - ri[1]) - (ri[2] - ri[0]) * 1080 / 1920) < 1e-6  # cuadrado en píxeles
    # 16:9 → 9:16 con recorte centrado: una cara en el centro del original queda en el centro de la salida
    fr = Frame(1920, 1080, 1080, 1920)
    out = source_rect_to_output((0.45, 0.4, 0.55, 0.6), Reframe(), fr)
    assert len(out) == 1 and 0.3 < (out[0][0] + out[0][2]) / 2 < 0.7
    # una cara fuera de la ventana de recorte no aparece
    assert source_rect_to_output((0.0, 0.4, 0.05, 0.6), Reframe(), fr) == []
    # stack: la facecam del original aparece en la banda superior
    rf = Reframe(mode="stack", facecam=Rect(x=0.7, y=0, w=0.3, h=0.3), game=Rect(x=0, y=0, w=0.7, h=1), stack_split=0.4)
    out = source_rect_to_output((0.8, 0.05, 0.9, 0.2), rf, fr)
    assert out and out[0][3] <= 0.4 + 1e-6


# --- comprobaciones -----------------------------------------------------------------------------------------------------


def codes(issues):
    return [i.code for i in issues]


def test_layer_checks_find_composition_problems():
    d = doc_with(
        TextLayer(end=5, text="Se sale", box=Box(x=1.0, y=0.5, w=0.6), id="off"),
        TextLayer(end=5, text="Abajo del todo", box=Box(x=0.5, y=0.93, w=0.8), id="ui"),
        TextLayer(start=1, end=4, text="Pisa", box=Box(x=0.5, y=0.5, w=0.5), id="a"),
        TextLayer(start=2, end=4, text="Pisado", box=Box(x=0.5, y=0.5, w=0.5), id="b"),
        TextLayer(end=5, text="x" * 400, box=Box(x=0.5, y=0.2, w=0.3), id="long"),
        TextLayer(end=15, text="Fuera de tiempo", box=Box(x=0.5, y=0.3), id="late"),
    )
    got = {(i.code, i.layer_id) for i in check_layers(d, 1080, 1920)}
    assert ("off_screen", "off") in got and ("platform_ui_zone", "ui") in got and ("layers_overlap", "a") in got
    assert ("text_long", "long") in got and ("layer_timing", "late") in got
    assert "no_subtitles" in codes(check_layers(d, 1080, 1920))
    clean = doc_with(SubtitleLayer(end=10), TextLayer(end=3, text="Hola", box=Box(x=0.5, y=0.1, w=0.8)))
    assert [i.code for i in check_layers(clean, 1080, 1920) if i.severity != "info"] == []


WORDS = [{"w": w, "start": s, "end": e} for w, s, e in [
    ("Hola", 0.0, 0.4), ("amigos.", 0.45, 1.0), ("Hoy", 1.5, 1.8), ("vamos", 1.85, 2.3), ("a", 2.35, 2.45), ("ver", 2.5, 2.9),
    ("cómo", 2.95, 3.3), ("se", 3.35, 3.5), ("instala.", 3.55, 4.2), ("Gracias", 5.0, 5.6)]]  # fmt: skip


def test_cut_checks():
    mk = lambda a, b: ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=a, source_out=b)])  # noqa: E731
    assert check_cuts(mk(1.45, 4.3), WORDS) == []  # empieza en frase y termina en punto
    mid_word = check_cuts(mk(1.6, 4.3), WORDS)
    assert "cut_mid_word" in codes(mid_word) and "«Hoy»" in mid_word[0].message
    assert "cut_starts_mid_sentence" in codes(check_cuts(mk(2.47, 4.3), WORDS))  # tras «a», sin punto
    ends = check_cuts(mk(1.45, 3.4), WORDS)
    assert any(i.code == "cut_mid_word" for i in ends)  # 3.4 cae dentro de «se»
    ends2 = check_cuts(mk(1.45, 2.92), WORDS)  # corta entre «ver» y «cómo» sin cerrar frase
    assert "cut_ends_mid_sentence" in codes(ends2) and "set_clip_range" in (ends2[0].suggestion or "")


def test_audio_checks():
    d = doc_with(audio={"normalize": False})
    st = {"has_audio": True, "integrated_lufs": -30.0, "true_peak_db": 1.0, "duration": 10.0,
          "silences": [{"start": 0.0, "end": 1.2, "duration": 1.2}, {"start": 4.0, "end": 6.0, "duration": 2.0}, {"start": 9.0, "end": 10.0, "duration": 1.0}]}  # fmt: skip
    got = codes(check_audio(d, st))
    assert {"loudness_off", "peak_over", "dead_air_start", "long_silence", "dead_air_end"} <= set(got)
    assert "loudness" in codes(check_audio(doc_with(), st)) and codes(check_audio(doc_with(), None)) == []
    assert codes(check_audio(doc_with(), {"has_audio": False, "silences": []})) == ["no_audio"]


def test_face_check_with_injected_detector():
    face = (0.4, 0.05, 0.6, 0.25)  # normalizada al original
    cover = TextLayer(end=10, text="Tapa", box=Box(x=0.5, y=0.12, w=0.5), id="cover")
    safe = TextLayer(end=10, text="No tapa", box=Box(x=0.5, y=0.7, w=0.5), id="safe")
    d = doc_with(cover, safe)
    out = check_faces(d, {"width": 1080, "height": 1920}, lambda t: [face])
    assert [(i.code, i.layer_id) for i in out] == [("covers_face", "cover")] and out[0].severity == "error"
    assert codes(check_faces(d, {"width": 1080, "height": 1920}, lambda t: [])) == ["no_face_detected"]
    assert check_faces(d, {"width": 1080, "height": 1920}, None) == []


def test_run_checks_summary_and_ordering():
    d = doc_with(TextLayer(end=5, text="Se sale", box=Box(x=1.1, y=0.5, w=0.6)))
    res = run_checks(d, {"width": 1080, "height": 1920}, [], None, None, has_transcript=False)
    assert res["ok"] is True and res["counts"]["warning"] >= 1
    sev = [i["severity"] for i in res["issues"]]
    assert sev == sorted(sev, key=["error", "warning", "info"].index)
    empty = ProjectDoc(media_id="m")
    assert run_checks(empty, {"width": 1, "height": 1}, [])["ok"] is False


def test_audio_stats_parsing():
    err = "[Parsed_ebur128] Summary:\n  Integrated loudness:\n    I:         -23.4 LUFS\n  Loudness range:\n    LRA:         5.2 LU\n  True peak:\n    Peak:       -1.5 dBFS\n"
    err += "[silencedetect] silence_start: 2.5\n[silencedetect] silence_end: 4.0 | silence_duration: 1.5\n[silencedetect] silence_start: 9.2\n"
    s = audio_mod.parse_stats(err, 10.0, -14, -1)
    assert (s["integrated_lufs"], s["loudness_range"], s["true_peak_db"]) == (-23.4, 5.2, -1.5)
    assert s["silences"] == [{"start": 2.5, "end": 4.0, "duration": 1.5}, {"start": 9.2, "end": 10.0, "duration": 0.8}]


# --- ventana de render y endpoints -----------------------------------------------------------------------------------------


def probe_size(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=width,height,duration",
            "-of",
            "csv=p=0",
            "-select_streams",
            "v",
            str(path),
        ],
        capture_output=True,
        text=True,
    ).stdout
    w, h, d = out.strip().split(",")
    return int(w), int(h), float(d)


@pytest.fixture
def project(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    with Session(get_engine()) as s:
        words = [{"w": f"palabra{i}", "start": 0.2 + i * 0.4, "end": 0.55 + i * 0.4, "p": 1} for i in range(6)]
        s.add(Transcript(media_id=mid, segments=[{"id": 0, "start": 0.2, "end": 2.6, "text": "x", "words": words}]))
        s.commit()
    p = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0.0, "source_out": 2.9}).json()
    writer.post(
        f"{API}/projects/{p['id']}/layers",
        json={"layer": {"type": "text", "id": "t1", "start": 1.0, "end": 2.5, "text": "Mitad", "box": {"y": 0.2}}},
    )
    return {"mid": mid, "pid": p["id"], "duration": p["duration"]}


def test_frame_endpoint_shows_layers_at_the_right_time(writer, project):
    pid = project["pid"]
    before = writer.get(f"{API}/projects/{pid}/frame", params={"t": 0.5, "quality": "preview"})
    during = writer.get(f"{API}/projects/{pid}/frame", params={"t": 1.6, "quality": "preview"})
    assert before.status_code == during.status_code == 200 and before.headers["content-type"] == "image/jpeg"
    a, b = Image.open(io.BytesIO(before.content)), Image.open(io.BytesIO(during.content))
    assert a.size == (b.size[0], b.size[1]) == (540, 960)
    # el rótulo «Mitad» (amarillo/blanco sobre y≈0.2) solo existe en el segundo: la franja difiere, el resto no
    band = (0, int(960 * 0.12), 540, int(960 * 0.28))
    ca, cb = a.crop(band), b.crop(band)
    diff = sum(abs(x - y) for p, q in zip(ca.getdata(), cb.getdata(), strict=True) for x, y in zip(p, q, strict=True))
    assert diff > 200000
    assert writer.get(f"{API}/projects/{pid}/frame", params={"t": 99}).status_code == 422
    assert "X-Job-Id" in before.headers and before.headers["x-warnings"]


def test_filmstrip_and_frames_job(writer, project):
    pid = project["pid"]
    r = writer.get(f"{API}/projects/{pid}/filmstrip", params={"count": 4, "cols": 2, "quality": "draft"})
    assert r.status_code == 200
    sheet = Image.open(io.BytesIO(r.content))
    assert sheet.size[0] == 2 * 270 and sheet.size[1] > 400  # 2 columnas de 270 px, 2 filas
    jid = writer.post(f"{API}/projects/{pid}/frames", json={"times": [0.3, 1.5], "quality": "draft"}).json()["job_id"]
    j = writer.get(f"{API}/jobs/{jid}").json()
    assert (
        j["status"] == "done"
        and [f["file"] for f in j["result"]["frames"]] == ["f0.jpg", "f1.jpg"]
        and j["result"]["sheet"] == "sheet.jpg"
    )
    assert writer.get(f"{API}/frames/{jid}/f1.jpg").status_code == 200
    assert writer.get(f"{API}/frames/{jid}/../../etc.jpg").status_code in (404, 422)
    assert writer.get(f"{API}/frames/{jid}/evil.sh").status_code == 404
    assert writer.post(f"{API}/projects/{pid}/frames", json={"times": [50]}).status_code == 422


def test_source_frame_with_grid(writer, project):
    r = writer.get(f"{API}/media/{project['mid']}/frame", params={"t": 1, "grid": True, "width": 400})
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).width == 400
    plain = writer.get(f"{API}/media/{project['mid']}/frame", params={"t": 1, "grid": False, "width": 400})
    assert r.content != plain.content  # la rejilla cambia la imagen


def test_partial_render_window(writer, project):
    pid = project["pid"]
    j = writer.get(
        f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft', 'start': 1.0, 'end': 2.0}).json()['job_id']}"
    ).json()
    assert j["status"] == "done", j
    assert abs(j["result"]["duration"] - 1.0) < 0.05
    assert abs(probe_size(j["result"]["path"])[2] - 1.0) < 0.2
    assert writer.post(f"{API}/projects/{pid}/render", json={"start": 5, "end": 6}).status_code == 422


def test_project_transcript_in_output_time_and_audio_stats(writer, project):
    pid = project["pid"]
    txt = writer.get(f"{API}/projects/{pid}/transcript").text
    assert "palabra0 palabra1" in txt and txt.startswith("[0:00.20")
    data = writer.get(f"{API}/projects/{pid}/transcript", params={"format": "json"}).json()
    assert data["phrases"][0]["words"][0] == {"w": "palabra0", "start": 0.2, "end": 0.55}
    st = writer.get(f"{API}/projects/{pid}/audio-stats").json()
    assert (
        st["has_audio"] and st["integrated_lufs"] < -10 and st["normalization_gain_db"] > 0 and st["true_peak_db"] < 0
    )


def test_checks_endpoint_end_to_end(writer, project):
    pid = project["pid"]
    r = writer.get(f"{API}/projects/{pid}/checks", params={"wait": 60})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["counts"]) == {"error", "warning", "info"} and isinstance(body["issues"], list) and "audio" in body
    assert any(i["code"] == "loudness" for i in body["issues"])  # el audio se midió de verdad
    job = writer.post(f"{API}/projects/{pid}/checks").json()["job_id"]
    assert writer.get(f"{API}/jobs/{job}").json()["status"] == "done"


def test_text_measurement_uses_the_real_font_like_libass():
    """Regresión: con un factor fijo por fuente, un título Anton que cabe en una línea se estimaba en dos y daba falsos
    positivos (cara tapada, fuera de pantalla). libass fija ascendente+descendente = Fontsize, no el em."""
    from cutly.services.verify.geometry import text_metrics

    w, h, lines = text_metrics("CÓMO INSTALAR APPS EN LINUX", "Anton", 0.047, True, 0.94, 1080, 1920, False)
    assert lines == 1 and 0.55 < w < 0.9 and h < 0.1
    _, _, cta = text_metrics("COMENTA\nLINUX", "Anton", 0.078, True, 0.8, 1080, 1920, False)
    assert cta == 2
    _, _, many = text_metrics("palabra " * 80, "Poppins", 0.04, False, 0.5, 1080, 1920, True)
    assert many > 6  # un texto largo en una caja estrecha sí ocupa muchas líneas
    # sin fuente localizable se usa la estimación por factor, sin romper
    assert text_metrics("Hola", "Fuente Inexistente", 0.05, False, 0.8, 1080, 1920)[2] == 1
