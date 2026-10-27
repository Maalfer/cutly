"""Efectos compilados solo sobre su ventana (clips largos): mismo resultado, sin perder ni duplicar fotogramas."""

import re
import subprocess

import pytest

from cutly.registry import effects as R
from cutly.schema.project import EffectLayer, ProjectDoc, Rect, TimelineClip
from cutly.services.render import graph as G
from cutly.services.render.graph import MediaInfo, RenderOpts, build_plan, ffmpeg_command


def _render(doc, tmp_path, src, name):
    opts = RenderOpts(workdir=tmp_path / name)
    plan = build_plan(doc, MediaInfo(str(src), 640, 360, True), [], opts)
    g = tmp_path / f"{name}.txt"
    g.write_text(plan.graph)
    out = tmp_path / f"{name}.mp4"
    r = subprocess.run(ffmpeg_command(plan, g, out, opts), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert plan.warnings == [], plan.warnings
    return out, plan.graph


def _frames(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return int(r.stdout.strip())


def _duration(video, kind):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", kind, "-show_entries", "stream=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return float(r.stdout.strip())


def _ssim(a, b, t):
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-ss", str(t), "-i", str(a), "-ss", str(t), "-i", str(b), "-frames:v", "1", "-lavfi", "ssim", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return float(re.search(r"All:([0-9.]+)", r.stderr).group(1))


def _doc(*layers):
    doc = ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=0, source_out=3)])
    doc.layers += list(layers)
    return doc


@pytest.mark.parametrize("effect,params,region", [
    ("zoom_punch", {"envelope": "in_out"}, None),
    ("whip_pan", {"envelope": "pulse"}, None),
    ("warm_flash", {"envelope": "pulse"}, None),
    ("zoom_punch", {"envelope": "in_out"}, Rect(x=0.1, y=0.1, w=0.5, h=0.5)),
])
def test_windowed_effect_matches_the_full_chain(effect, params, region, tmp_path, sample_video, monkeypatch):
    layer = EffectLayer(start=1.0, end=1.8, effect=effect, region=region, params=R.normalized_params(effect, params))
    ref, g_ref = _render(_doc(layer), tmp_path, sample_video, "ref")
    monkeypatch.setattr(G, "FX_WINDOW_MIN_DURATION", 0.0)
    win, g_win = _render(_doc(layer), tmp_path, sample_video, "win")
    assert "concat=n=3" in g_win and "concat=n=3" not in g_ref  # de verdad se ha ventaneado
    assert _frames(win) == _frames(ref)  # ni un fotograma perdido ni duplicado
    assert abs(_duration(win, "v:0") - _duration(ref, "v:0")) < 0.04
    assert abs(_duration(win, "a:0") - _duration(ref, "a:0")) < 0.1
    for t in (0.4, 1.4, 2.5):  # antes, dentro y después de la ventana
        assert _ssim(ref, win, t) > 0.985, (effect, t)


def test_many_windowed_effects_keep_sync(tmp_path, sample_video, monkeypatch):
    layers = [EffectLayer(start=0.3 + i * 0.55, end=0.7 + i * 0.55, effect="zoom_punch", params=R.normalized_params("zoom_punch", {})) for i in range(5)]
    ref, _ = _render(_doc(*layers), tmp_path, sample_video, "ref")
    monkeypatch.setattr(G, "FX_WINDOW_MIN_DURATION", 0.0)
    win, g = _render(_doc(*layers), tmp_path, sample_video, "win")
    assert g.count("concat=n=") >= 5
    assert _frames(win) == _frames(ref)


def test_short_projects_are_not_windowed(tmp_path, sample_video):
    layer = EffectLayer(start=1.0, end=1.8, effect="zoom_punch", params=R.normalized_params("zoom_punch", {}))
    _, g = _render(_doc(layer), tmp_path, sample_video, "short")
    assert "split=3" not in g
