import re
import subprocess

import pytest

from cutly.registry import effects as R
from cutly.schema.project import EffectLayer, ProjectDoc, Rect, TimelineClip
from cutly.services.render.effects_api import EffectBuildError, EffectCtx, env, validate_filters
from cutly.services.render.graph import MediaInfo, RenderOpts, build_plan, ffmpeg_command

API = "/api/v1"
CTX = EffectCtx(2.0, 3.0, 1080, 1920, 30)


def test_registry_loads_all_builtin_effects():
    names = {e.name for e in R.all_effects()}
    assert {"zoom_punch", "shake", "flash", "glitch", "vignette", "color_pulse", "progress_bar", "letterbox",
            "film_grain", "blur_focus", "slow_zoom", "negative_flash"} <= names  # fmt: skip
    assert R.errors() == {}
    for e in R.all_effects():
        assert R.validate_params(e.params_schema, {}) is not None  # los valores por defecto son válidos
        assert e.public()["example_layer"]["effect"] == e.name
        assert (e.path / "preview.js").is_file() and "export function render" in (e.path / "preview.js").read_text()
        validate_filters(R.build_filters(e, {}, CTX))


def test_param_validation_messages():
    s = R.get("zoom_punch").params_schema
    with pytest.raises(R.EffectParamError, match="mayor que el máximo"):
        R.validate_params(s, {"scale": 9})
    with pytest.raises(R.EffectParamError, match="desconocidos"):
        R.validate_params(s, {"zoom": 2})
    with pytest.raises(R.EffectParamError, match="Opciones"):
        R.validate_params(s, {"envelope": "raro"})
    with pytest.raises(R.EffectParamError, match="debe ser un número"):
        R.validate_params(s, {"scale": "1.2; drawtext"})
    with pytest.raises(R.EffectParamError, match="Quizá zoom_punch"):
        R.get("zoom_pun")


def test_filter_validator_blocks_injection():
    for bad in [
        "scale=1;movie=/etc/passwd",
        "movie=/etc/passwd",
        "scale=w=[a]",
        "scale=w=\\x",
        "drawtext=text=hi",
        "scale='1+1",
    ]:
        with pytest.raises(EffectBuildError):
            validate_filters([bad])
    assert env("hold", CTX) == "between(t,2,3)"


def _render(doc, tmp_path, src, name):
    opts = RenderOpts(workdir=tmp_path / name)
    plan = build_plan(doc, MediaInfo(str(src), 640, 360, True), [], opts)
    g = tmp_path / f"{name}.txt"
    g.write_text(plan.graph)
    out = tmp_path / f"{name}.mp4"
    r = subprocess.run(ffmpeg_command(plan, g, out, opts), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert plan.warnings == [], plan.warnings
    return out


def _frame(video, t, png):
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(png)],
        check=True,
    )
    return png


def _ssim(a, b):
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi", "ssim", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    return float(re.search(r"All:([0-9.]+)", r.stderr).group(1))


@pytest.mark.parametrize("name", [e.name for e in R.all_effects()])
def test_every_effect_renders_and_changes_only_its_window(name, tmp_path, sample_video):
    """El efecto altera el fotograma dentro de su ventana y deja intacto el resto (render exacto)."""
    base = ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=0, source_out=3)])
    ref = _render(base, tmp_path, sample_video, "ref")
    with_fx = base.model_copy(deep=True)
    params = {"strength": 0.9} if name == "flash" else {"intensity": 20} if name == "glitch" else {}
    with_fx.layers.append(EffectLayer(start=1.0, end=2.0, effect=name, params=R.normalized_params(name, params)))
    out = _render(with_fx, tmp_path, sample_video, "fx")
    inside = _ssim(_frame(ref, 1.5, tmp_path / "a.png"), _frame(out, 1.5, tmp_path / "b.png"))
    before = _ssim(_frame(ref, 0.3, tmp_path / "c.png"), _frame(out, 0.3, tmp_path / "d.png"))
    after = _ssim(_frame(ref, 2.7, tmp_path / "e.png"), _frame(out, 2.7, tmp_path / "f.png"))
    # progress_bar y letterbox/blur cambian poco o mucho según el contenido: basta con que difieran
    assert inside < 0.9995, f"{name}: no cambió nada dentro de la ventana (ssim={inside})"
    if name != "slow_zoom":  # slow_zoom vuelve a escala 1 al acabar, igual que el resto
        # fuera de la ventana solo queda ruido de recompresión; dentro, la diferencia debe ser claramente mayor
        assert before > 0.95 and after > 0.95, f"{name}: altera fuera de su ventana ({before}, {after})"
        assert inside < min(before, after) - 0.001, (
            f"{name}: dentro ({inside}) no difiere más que fuera ({before}, {after})"
        )


def _crop(src, y, out):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-vf", f"crop=iw:ih*0.4:0:{y}", str(out)]
    subprocess.run(cmd, check=True)
    return out


def test_effect_region_limits_the_change(tmp_path, sample_video):
    base = ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=0, source_out=3)])
    ref = _render(base, tmp_path, sample_video, "ref")
    doc = base.model_copy(deep=True)
    region = Rect(x=0, y=0, w=1, h=0.4)
    doc.layers.append(EffectLayer(start=1, end=2, effect="negative_flash", region=region, params={}))
    out = _render(doc, tmp_path, sample_video, "reg")
    a, b = _frame(ref, 1.5, tmp_path / "a.png"), _frame(out, 1.5, tmp_path / "b.png")
    top = _ssim(_crop(a, 0, tmp_path / "ta.png"), _crop(b, 0, tmp_path / "tb.png"))
    bottom = _ssim(_crop(a, "ih*0.6", tmp_path / "ba.png"), _crop(b, "ih*0.6", tmp_path / "bb.png"))
    assert top < 0.5  # dentro de la región: invertido
    assert bottom > 0.95  # fuera: intacto (solo ruido de recompresión)


def test_effects_api_and_declarative_effects(writer, sample_video):
    lst = writer.get(f"{API}/effects", params={"q": "zoom"}).json()
    assert {"zoom_punch", "slow_zoom"} <= {e["name"] for e in lst["effects"]}
    d = writer.get(f"{API}/effects/zoom_punch").json()
    assert d["params_schema"]["properties"]["scale"]["maximum"] == 2.0 and d["example_layer"]["params"]["scale"] == 1.25
    assert "export function render" in writer.get(f"{API}/effects/zoom_punch/preview.js").text
    assert writer.get(f"{API}/effects/nope").status_code == 404

    good = {"name": "warm_pulse", "title": "Pulso cálido", "tags": ["color"],
            "description": "Sube el calor del color un momento",
            "params_schema": {"type": "object", "properties": {"amount": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.3}}},  # noqa: E501
            "chain": ["eq=gamma_r='1+{amount}*{env}':gamma_b='1-{amount}*{env}':eval=frame"]}  # fmt: skip
    assert writer.post(f"{API}/effects", json=good).status_code == 200
    assert "warm_pulse" in {e["name"] for e in writer.get(f"{API}/effects").json()["effects"]}
    bad = [
        {**good, "name": "zoom_punch"},  # pisa uno incluido
        {**good, "name": "x1", "chain": ["movie=/etc/passwd"]},  # filtro no permitido
        {**good, "name": "x2", "chain": ["eq=brightness=1;drawtext=text=x"]},  # metacaracteres
        {**good, "name": "x3", "chain": ["eq=brightness='{nope}'"]},  # hueco inexistente
        {**good, "name": "x6", "chain": ["colorbalance=rs='{amount}*{env}'"]},  # FFmpeg no admite expresiones ahí
        {
            **good,
            "name": "x4",
            "params_schema": {"type": "object", "properties": {"a": {"type": "number"}}},
        },  # sin límites
        {
            **good,
            "name": "x5",
            "params_schema": {"type": "object", "properties": {"a": {"type": "string", "default": "x"}}},
        },  # texto libre
    ]
    codes = [writer.post(f"{API}/effects", json=b).status_code for b in bad]
    assert codes == [409, 422, 422, 422, 422, 422, 422], codes

    # se puede usar en un proyecto y renderiza
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    pid = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 3, "subtitles": False}
    ).json()["id"]
    r = writer.post(
        f"{API}/projects/{pid}/layers",
        json={"layer": {"type": "effect", "start": 1, "end": 2, "effect": "warm_pulse", "params": {"amount": 0.5}}},
    )
    assert r.status_code == 200 and r.json()["project"]["layers"][0]["params"] == {"amount": 0.5}
    j = writer.get(
        f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft'}).json()['job_id']}"
    ).json()
    assert j["status"] == "done" and j["result"]["warnings"] == []
    assert writer.delete(f"{API}/effects/warm_pulse").status_code == 200
    assert writer.delete(f"{API}/effects/zoom_punch").status_code == 403


def test_ops_validate_effects_assets_and_fonts(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    pid = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 3, "subtitles": False}
    ).json()["id"]

    def add(layer):
        return writer.post(f"{API}/projects/{pid}/layers", json={"layer": layer})

    r = add({"type": "effect", "end": 2, "effect": "zoom_pun"})
    assert r.status_code == 422 and "zoom_punch" in r.json()["detail"]
    r = add({"type": "effect", "end": 2, "effect": "zoom_punch", "params": {"scale": 5}})
    assert r.status_code == 422 and "máximo" in r.json()["detail"]
    r = add({"type": "icon", "end": 2, "asset": "icons/arow-right"})
    assert r.status_code == 422 and "icons/arrow-right" in r.json()["detail"]
    r = add({"type": "text", "end": 2, "text": "x", "style": {"font": "Comic Papyrus"}})
    assert r.status_code == 422 and "Poppins" in r.json()["detail"]
    ok = add({"type": "effect", "end": 2, "effect": "zoom_punch", "params": {"scale": 1.3}})
    assert (
        ok.status_code == 200 and ok.json()["project"]["layers"][0]["params"]["focus_x"] == 0.5
    )  # normalizado con defaults
    assert add({"type": "text", "end": 2, "text": "x", "style": {"font": "Poppins"}}).status_code == 200


def test_envelopes_stay_finite_far_from_their_window(tmp_path):
    """Regresión: un destello lejano (p. ej. a los 88 s) oscurecía TODO el vídeo: exp() se desbordaba fuera de la
    ventana y 0*inf = NaN. Cualquier envolvente debe valer 0 y ser finita en todo el vídeo."""
    far = EffectCtx(88.0, 88.28, 360, 640, 30)
    for kind in ("hold", "pulse", "in_out", "decay", "ramp"):
        expr = env(kind, far)
        out = tmp_path / f"{kind}.txt"
        # se evalúa con el propio FFmpeg sobre t = 0..1 s (muy lejos de la ventana) y debe dar exactamente 0
        r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':d=0.5:s=8000", "-f", "f32le", str(out)],  # noqa: E501
                           capture_output=True, text=True)  # fmt: skip
        assert r.returncode == 0, r.stderr
        import struct

        vals = struct.unpack(f"{out.stat().st_size // 4}f", out.read_bytes())
        assert vals and all(v == 0.0 for v in vals), f"{kind}: {set(vals)}"


def test_far_flash_does_not_darken_the_video(tmp_path):
    base = "testsrc2=size=160x284:rate=10:duration=1"

    def yavg(vf):
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-v",
            "info",
            "-f",
            "lavfi",
            "-i",
            base,
            "-vf",
            f"{vf},signalstats,metadata=print:key=lavfi.signalstats.YAVG",
            "-f",
            "null",
            "-",
        ]
        out = subprocess.run(cmd, capture_output=True, text=True).stderr
        return float(re.findall(r"YAVG=([0-9.]+)", out)[0])

    chain = ",".join(R.build_filters(R.get("flash"), {}, EffectCtx(88.0, 88.28, 160, 284, 10)))
    assert abs(yavg(chain) - yavg("null")) < 1.0
