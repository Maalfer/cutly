"""`/scenes/lint`: validación rápida de escenas `code` (necesita Chromium; se salta solo si no está)."""

from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="playwright no está instalado (extra opcional scene-js)")
if not Path("/usr/bin/chromium").is_file():
    pytest.skip("no hay un Chromium del sistema en esta máquina", allow_module_level=True)

from cutly.services.scene_js.lint import lint_scene  # noqa: E402

PAGE = """<!doctype html><html><body style="margin:0;background:#000"><canvas id=c></canvas><script>
const c=document.getElementById('c'),x=c.getContext('2d');c.width=innerWidth;c.height=innerHeight;
let t=0,last=performance.now();
function f(now){{t+=(now-last)/1000;last=now;{body}requestAnimationFrame(f);}}requestAnimationFrame(f);
</script></body></html>"""

GOOD = "x.fillStyle='#123';x.fillRect(0,0,c.width,c.height);x.fillStyle='#fff';x.font=(c.width*0.05)+'px sans-serif';x.fillText('Hola',40+t*40,300);"


def codes(body: str, **kw) -> set[str]:
    r = lint_scene(PAGE.format(body=body), 540, 960, kw.pop("duration", 3), **kw)
    return {i.code for i in r.issues}


def test_good_scene_is_clean():
    assert codes(GOOD) == set()


def test_js_error_midway_is_reported():
    assert "js_error" in codes(GOOD + "if(t>1)null.boom();")


def test_blank_scene_is_error():
    assert "blank" in codes("x.clearRect(0,0,c.width,c.height);")


def test_static_scene_warns():
    assert "static" in codes("x.fillStyle='#345';x.fillRect(0,0,c.width,c.height);x.fillStyle='#fff';x.fillRect(10,10,50,50);")


def test_clock_violations():
    cs = codes(GOOD + "Date.now();setTimeout(()=>{},10);")
    assert {"date_now", "timers"} <= cs


def test_small_and_overflowing_text():
    cs = codes(GOOD + "x.font='10px sans-serif';x.fillText('pequeño',20,500);"
               "x.font=(c.width*0.06)+'px sans-serif';x.fillText('Un texto larguísimo que no cabe en pantalla',-80,600);")
    assert {"small_text", "text_overflow"} <= cs


def test_static_source_checks():
    r = lint_scene(PAGE.format(body=GOOD + "fetch('http://x.es');"), 540, 960, 2)
    assert any(i.code == "network_api" and i.severity == "error" for i in r.issues)
    assert not r.as_dict()["ok"]


def test_syntax_error_is_load_error_or_js_error():
    r = lint_scene("<html><body><script>let = ;</script></body></html>", 540, 960, 2)
    assert any(i.severity == "error" for i in r.issues)


def test_params_are_exposed():
    body = GOOD + "if(CUTLY_PARAMS.boom)null.x;"
    assert "js_error" in codes(body, params={"boom": True})
    assert "js_error" not in codes(body, params={})


# --- API / kit / parámetros en el render real --------------------------------------------------------------


def test_lint_endpoint(writer):
    r = writer.post("/api/v1/scenes/lint", json={"code": PAGE.format(body=GOOD), "width": 540, "height": 960, "duration": 3})
    assert r.status_code == 200 and r.json()["ok"] is True
    bad = writer.post("/api/v1/scenes/lint", json={"code": PAGE.format(body="x.clearRect(0,0,9,9);"), "width": 540, "height": 960, "duration": 3})
    assert bad.json()["ok"] is False and any(i["code"] == "blank" for i in bad.json()["issues"])


def test_code_kit_and_base_template_is_lint_clean(writer):
    kit = writer.get("/api/v1/scenes/code-kit").json()
    assert kit["rules"] and "CUTLY_PARAMS" in kit["base_html"]
    r = lint_scene(kit["base_html"], 1080, 1920, 12)
    assert not r.issues, [i.message for i in r.issues]
    r2 = lint_scene(kit["base_html"], 1920, 1080, 12, {"title": "T" * 30})
    assert not [i for i in r2.issues if i.severity == "error"]


def test_live_doc_injects_params(writer):
    r = writer.post("/api/v1/scenes/live-doc", data={"code": "<html><head></head><body>x</body></html>", "params": '{"a": "</script>"}'})
    assert r.status_code == 200 and "window.CUTLY_PARAMS" in r.text and "</script>\"" not in r.text.split("CUTLY_PARAMS")[1].split(";")[0]


def test_words_exposed_and_kit_uses_them():
    words = [{"w": "primero", "start": 1.0, "end": 1.4}, {"w": "Cupón", "start": 2.0, "end": 2.5}]
    body = GOOD + "if(CUTLY_WORDS.length!==2||saidAt)null.x;"  # saidAt no existe aquí: solo comprueba CUTLY_WORDS
    assert "js_error" in codes(GOOD + "if(CUTLY_WORDS.length===2)null.x;", words=words)
    assert "js_error" not in codes(GOOD + "if(CUTLY_WORDS.length===2)null.x;")
    r = lint_scene(open("src/cutly/services/scene_js/kit/base.html").read(), 1080, 1920, 12,
                   {"recapWords": ["primero", "cupon", "nada"]}, words=words)  # fmt: skip
    assert not [i for i in r.issues if i.severity == "error"]


def test_live_doc_injects_words(writer):
    r = writer.post("/api/v1/scenes/live-doc", data={"code": "<html><head></head><body>x</body></html>",
                                                    "words": '[{"w":"hola","start":1,"end":2}]'})  # fmt: skip
    assert r.status_code == 200 and "CUTLY_WORDS = Object.freeze([{" in r.text and "hola" in r.text
