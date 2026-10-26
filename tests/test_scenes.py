import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from cutly.schema.project import ProjectDoc, SceneLayer
from cutly.schema.scene import Scene
from cutly.services.scene import templates as TP
from cutly.services.scene.engine import Player

API = "/api/v1"


def small_scene(**over) -> dict:
    sc = {
        "objects": [
            {"type": "node", "id": "a", "kind": "computer", "x": 300, "y": 450, "label": "A", "at": 0},
            {"type": "node", "id": "b", "kind": "server", "x": 1300, "y": 450, "label": "B", "at": 0.2},
            {"type": "link", "a": "a", "b": "b", "gap": 80, "at": 0.4, "enter": "draw"},
            {"type": "dot", "id": "p", "path": ["a", "b"], "at": 0.8, "travel": 1.0, "shape": "packet", "label": "#1"},
            {"type": "text", "text": "Hola **mundo**", "x": 800, "y": 120, "at": 0.1, "enter": "type", "fixed": True},
        ],
    }
    sc.update(over)
    return sc


# --- esquema -----------------------------------------------------------------------------------------------------


def test_scene_rejects_unknown_references_with_actionable_message():
    bad = small_scene()
    bad["objects"][2]["b"] = "zzz"
    with pytest.raises(ValidationError, match="zzz.*Ids disponibles"):
        Scene.model_validate(bad)


def test_scene_rejects_duplicate_ids_and_extra_fields_and_control_chars():
    dup = small_scene()
    dup["objects"][1]["id"] = "a"
    with pytest.raises(ValidationError, match="repetidos"):
        Scene.model_validate(dup)
    extra = small_scene()
    extra["objects"][0]["colour"] = "#fff"
    with pytest.raises(ValidationError):
        Scene.model_validate(extra)
    ctl = small_scene()
    ctl["objects"][4]["text"] = "mal\x07"
    with pytest.raises(ValidationError, match="control"):
        Scene.model_validate(ctl)
    with pytest.raises(ValidationError, match="`until`"):
        Scene.model_validate({"objects": [{"type": "node", "at": 2, "until": 1}]})


def test_scene_layer_needs_template_or_scene():
    with pytest.raises(ValidationError, match="template"):
        SceneLayer(end=5)
    assert SceneLayer(end=5, template="title_card").scene is None
    doc = ProjectDoc.model_validate({"media_id": "m", "layers": [{"type": "scene", "end": 5, "scene": small_scene()}]})
    assert doc.layers[0].type == "scene"


# --- motor -------------------------------------------------------------------------------------------------------


def test_frames_are_stateless_and_deterministic():
    sc = Scene.model_validate(small_scene())
    a = Player(sc, 480, 270)
    b = Player(sc, 480, 270)
    f1 = a.frame(1.2)
    a.frame(0.1)
    a.frame(2.0)
    assert np.array_equal(f1, b.frame(1.2)) and np.array_equal(f1, a.frame(1.2))  # no depende del orden de llamada


def test_objects_appear_at_their_time_and_transparent_background():
    sc = Scene.model_validate({"background": {"style": "transparent"}, "objects": small_scene()["objects"][:2]})
    pl = Player(sc, 480, 270)
    assert pl.frame(0.0)[..., 3].max() < 40  # nada todavía (la entrada empieza en 0)
    early, late = pl.frame(0.3), pl.frame(1.5)
    assert early[..., 3].max() > 100 and (late[..., 3] > 0).sum() > (early[..., 3] > 0).sum()  # B aparece a los 0,2 s


def test_dot_moves_along_path_and_camera_follows():
    sc = Scene.model_validate(
        small_scene(
            camera=[{"t": 0, "zoom": 1}, {"t": 1, "follow": "p", "zoom": 2}, {"t": 2, "follow": "p", "zoom": 2}]
        )
    )
    pl = Player(sc, 480, 270)
    pos0 = pl._positions(0.9)["p"]
    pos1 = pl._positions(1.3)["p"]
    assert pos1[0] > pos0[0]  # avanza hacia B
    x, y, z = pl._camera(1.6, pl._positions(1.6))
    assert z == pytest.approx(2.0, abs=0.05) and 300 < x < 1300


def test_fixed_objects_ignore_the_camera():
    objs = [{"type": "text", "text": "FIJO", "x": 800, "y": 450, "size": 80, "fixed": True, "enter": "none"}]
    a = Player(
        Scene.model_validate({"objects": objs, "handheld": 0, "background": {"style": "transparent"}}), 480, 270
    ).frame(1.0)
    b = Player(
        Scene.model_validate(
            {
                "objects": objs,
                "handheld": 0,
                "background": {"style": "transparent"},
                "camera": [{"t": 0, "x": 200, "y": 100, "zoom": 3}],
            }
        ),
        480,
        270,
    ).frame(1.0)
    assert a[..., 3].max() > 200 and np.array_equal(a, b)


def test_scramble_is_deterministic_and_changes_text():
    from cutly.services.scene.text import scramble_text

    s = scramble_text("contraseña secreta", 0.8, 5, 3)
    assert s == scramble_text("contraseña secreta", 0.8, 5, 3) and s != "contraseña secreta" and s[10] == " "


# --- plantillas --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TP.REGISTRY))
@pytest.mark.parametrize("orient", ["wide", "tall"])
def test_every_template_builds_and_renders_at_any_duration(name, orient):
    t = TP.get_template(name)
    for dur in (t.min_duration, t.recommended, 40.0):
        sc = TP.build_template(name, {"orient": orient}, dur)
        assert (sc.world.w, sc.world.h) == ((900, 1600) if orient == "tall" else (1600, 900))
        w = 240 if orient == "tall" else 400
        pl = Player(sc, w, round(w * sc.world.h / sc.world.w))
        for f in (0.05, 0.5, 0.97):
            fr = pl.frame(dur * f)
            assert fr.shape[2] == 4 and fr[..., 3].max() > 0


def test_template_params_are_validated_with_helpful_errors():
    with pytest.raises(TP.TemplateError, match="desconocidos.*domain"):
        TP.build_template("dns_lookup", {"dominio": "x"}, 10)
    with pytest.raises(TP.TemplateError, match="no existe.*Disponibles"):
        TP.build_template("nope", {}, 10)
    with pytest.raises(TP.TemplateError, match="orient"):
        TP.build_template("title_card", {"orient": "diagonal"}, 5)
    with pytest.raises(TP.TemplateError, match="al menos 2"):
        TP.build_template("flow_steps", {"steps": [{"kind": "server"}]}, 8)


def test_url_anatomy_splits_any_url():
    parts = TP._url_parts("https://sub.ejemplo.com:8443/a/b?x=1&y=2#frag")
    assert [p[1] for p in parts] == ["Esquema", "Dominio", "Puerto", "Ruta", "Parámetros", "Fragmento"]
    assert "".join(p[0] for p in parts) == "https://sub.ejemplo.com:8443/a/b?x=1&y=2#frag"


def test_template_scene_scales_with_duration():
    short = TP.build_template("packet_network", {}, 10)
    long = TP.build_template("packet_network", {}, 30)
    last = lambda s: max(o.at for o in s.objects)  # noqa: E731
    assert last(long) == pytest.approx(last(short) * 3, rel=0.02)


def test_race_condition_fail_moment_depends_on_request_count():
    """Con más peticiones en paralelo, la cruz de «fallo» y el valor final deben aparecer más tarde
    (la ráfaga tarda más en completarse), y los textos antes/después no se solapan en el tiempo."""
    from cutly.schema.scene import Dot, Node, Text

    def fail_time(scene):
        return next(o.at for o in scene.objects if o.type == "node" and getattr(o, "kind", None) == "cross")

    few = TP.build_template("race_condition", {"requests": 3}, 8)
    many = TP.build_template("race_condition", {"requests": 10}, 8)
    assert fail_time(many) > fail_time(few)
    dots = [o for o in few.objects if isinstance(o, Dot)]
    assert len(dots) == 1 and dots[0].count == 3
    locks = [o for o in few.objects if isinstance(o, Node) and o.kind == "lock"]
    assert locks and locks[0].keys and locks[0].keys[0].t == pytest.approx(fail_time(few))
    before = next(o for o in few.objects if isinstance(o, Text) and o.text == "1 uso")
    after = next(o for o in few.objects if isinstance(o, Text) and o.text == "N usos")
    assert before.until == pytest.approx(after.at) and before.at < after.at


# --- API ----------------------------------------------------------------------------------------------------------


def test_templates_endpoint_and_example_layer_is_valid(writer):
    r = writer.get(f"{API}/scenes/templates")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["templates"]}
    assert {
        "packet_network",
        "dns_lookup",
        "tls_handshake",
        "url_anatomy",
        "flow_steps",
        "recap_cards",
        "title_card",
    } <= names
    for t in r.json()["templates"]:
        SceneLayer.model_validate(t["example_layer"])
    assert writer.get(f"{API}/scenes/templates", params={"q": "dns"}).json()["templates"][0]["name"] == "dns_lookup"
    assert writer.get(f"{API}/scenes/templates/nope").status_code == 404
    assert "objects" in writer.get(f"{API}/scenes/schema").json()["properties"]


def test_build_endpoint_expands_a_template_into_editable_json(writer):
    r = writer.post(f"{API}/scenes/build", json={"template": "title_card", "params": {"title": "Hola"}, "duration": 6})
    assert r.status_code == 200
    Scene.model_validate(r.json())
    assert writer.post(f"{API}/scenes/build", json={"duration": 6}).status_code == 422
    assert writer.post(f"{API}/scenes/build", json={"template": "title_card", "scene": {}}).status_code == 422


def test_preview_returns_png_contact_sheet(writer):
    r = writer.post(
        f"{API}/scenes/preview",
        json={"template": "flow_steps", "duration": 10, "times": [1, 3, 5, 7], "width": 320, "cols": 2},
    )
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (640, 360)
    r = writer.post(f"{API}/scenes/preview", json={"scene": small_scene(), "times": [1.2], "width": 320})
    assert Image.open(io.BytesIO(r.content)).size == (320, 180)
    bad = writer.post(f"{API}/scenes/preview", json={"scene": {"objects": [{"type": "link", "a": "x", "b": [0, 0]}]}})
    assert bad.status_code == 422 and "x" in bad.json()["detail"]
    ro = writer.post(f"{API}/scenes/preview", json={"template": "title_card"})
    assert ro.status_code == 200


# --- proyecto y render --------------------------------------------------------------------------------------------


@pytest.fixture
def media_id(writer, sample_video):
    return writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]


@pytest.fixture
def project(writer, media_id):
    r = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0.2, "source_out": 2.8, "name": "P"})
    assert r.status_code == 200, r.text
    return r.json()


def add(writer, pid, layer):
    return writer.post(f"{API}/projects/{pid}/ops", json={"ops": [{"op": "add_layer", "layer": layer}]})


def test_add_scene_layer_validates_template_and_fonts(writer, project):
    pid = project["id"]
    ok = add(
        writer,
        pid,
        {"type": "scene", "start": 0.2, "end": 2.4, "template": "flow_steps", "params": {"message": "hola"}},
    )
    assert ok.status_code == 200, ok.text
    bad = add(writer, pid, {"type": "scene", "end": 2, "template": "nope"})
    assert bad.status_code == 422 and "Disponibles" in bad.text
    badp = add(writer, pid, {"type": "scene", "end": 2, "template": "dns_lookup", "params": {"foo": 1}})
    assert badp.status_code == 422 and "desconocidos" in badp.text
    sc = small_scene()
    sc["objects"][4]["font"] = "Comic Nope"
    badf = add(writer, pid, {"type": "scene", "end": 2, "scene": sc})
    assert badf.status_code == 422 and "fuente" in badf.text


def test_scene_layer_renders_into_the_video_and_frame_endpoint(writer, project, sample_video):
    pid = project["id"]
    assert (
        add(
            writer,
            pid,
            {"type": "scene", "start": 0.4, "end": 2.4, "scene": small_scene(), "box": {"x": 0.5, "y": 0.5, "w": 1.0}},
        ).status_code
        == 200
    )
    before = writer.get(f"{API}/projects/{pid}/frame", params={"t": 0.1, "quality": "preview"})
    during = writer.get(f"{API}/projects/{pid}/frame", params={"t": 1.8, "quality": "preview"})
    assert before.status_code == during.status_code == 200
    a = np.asarray(Image.open(io.BytesIO(before.content)).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(io.BytesIO(during.content)).convert("RGB"), dtype=np.int16)
    assert np.abs(a - b).mean() > 3  # la escena cambia el fotograma

    job = writer.post(f"{API}/projects/{pid}/render", json={"quality": "draft"}).json()["job_id"]
    j = writer.get(f"{API}/jobs/{job}").json()
    assert j["status"] == "done", j
    assert j["result"]["warnings"] == []
    out = Path(j["result"]["path"])
    assert out.stat().st_size > 5_000
    # render por tramos: solo genera los fotogramas necesarios y mantiene los tiempos absolutos
    job2 = writer.post(f"{API}/projects/{pid}/render", json={"quality": "draft", "start": 1.5, "end": 2.0}).json()[
        "job_id"
    ]
    assert writer.get(f"{API}/jobs/{job2}").json()["status"] == "done"
    info = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out)], capture_output=True, text=True
        ).stdout
    )
    assert info["streams"][0]["codec_name"] == "h264"
    dur = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
            capture_output=True,
            text=True,
        ).stdout
    )
    assert dur > 2.3  # la escena acaba a los 2,4 s pero el vídeo (2,6 s) debe seguir hasta el final


def test_scene_sequence_only_generates_frames_in_window(tmp_path):
    from cutly.services.scene.sequence import render_scene_sequence

    layer = SceneLayer(start=1.0, end=9.0, scene=Scene.model_validate(small_scene()))
    warn: list[str] = []
    full = render_scene_sequence(layer, 360, 640, 10, tmp_path / "a", warn)
    part = render_scene_sequence(layer, 360, 640, 10, tmp_path / "b", warn, window=(4.0, 4.5))
    assert full and part and warn == []
    assert full.frames == 81 and part.frames < 10 and part.t0 == pytest.approx(2.9, abs=0.2)
    assert (full.x, full.y) == (0, round(640 / 2 - (360 * 900 / 1600) / 2)) or full.y > 0


def test_sequence_has_one_pixel_format_even_with_fades(tmp_path):
    """Mezclar PNG RGB y RGBA en una secuencia hace que FFmpeg corte el vídeo al acabar la secuencia."""
    from cutly.schema.project import Anim, Animations
    from cutly.services.scene.sequence import render_scene_sequence

    layer = SceneLayer(start=0, end=2, scene=Scene.model_validate(small_scene()),
                       animations=Animations(enter=Anim(name="fade", dur=0.5), exit=Anim(name="fade", dur=0.5)))  # fmt: skip
    seq = render_scene_sequence(layer, 320, 180, 10, tmp_path / "a", [])
    assert seq is not None
    assert {Image.open(tmp_path / "a" / f"f{i:05d}.png").mode for i in range(seq.frames)} == {"RGBA"}
    plain = SceneLayer(start=0, end=2, scene=Scene.model_validate(small_scene()))
    seq2 = render_scene_sequence(plain, 320, 180, 10, tmp_path / "b", [])
    assert {Image.open(tmp_path / "b" / f"f{i:05d}.png").mode for i in range(seq2.frames)} == {"RGB"}
