"""Capa `audio`: efectos de sonido sintetizados y su mezcla en el render."""

import re
import subprocess

import pytest
from pydantic import ValidationError

from cutly.schema.project import AudioLayer, ProjectDoc, TimelineClip
from cutly.services.audio.sfx import CATALOG, sfx_path
from cutly.services.render.graph import MediaInfo, RenderOpts, build_plan, ffmpeg_command


def _render(doc, tmp_path, src, name):
    opts = RenderOpts(workdir=tmp_path / name, draft=True)
    plan = build_plan(doc, MediaInfo(str(src), 640, 360, True), [], opts)
    g = tmp_path / f"{name}.txt"
    g.write_text(plan.graph)
    out = tmp_path / f"{name}.mp4"
    r = subprocess.run(ffmpeg_command(plan, g, out, opts), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert plan.warnings == [], plan.warnings
    return out


def _mean_db(video, t, dur):
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-ss", str(t), "-t", str(dur), "-i", str(video), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )  # fmt: skip
    return float(re.search(r"mean_volume: (-?[0-9.]+) dB", r.stderr).group(1))


@pytest.mark.parametrize("name", list(CATALOG))
def test_every_sfx_is_generated_with_its_catalog_duration(name, tmp_path):
    import wave

    with wave.open(str(sfx_path(name, tmp_path)), "rb") as w:
        assert w.getnchannels() == 2 and w.getframerate() == 48000
        assert abs(w.getnframes() / 48000 - CATALOG[name].duration) < 0.01


def test_unknown_sfx_rejected():
    with pytest.raises(ValidationError):
        AudioLayer(start=0, end=1, sfx="trompeta")
    with pytest.raises(KeyError):
        sfx_path("trompeta", None)


def test_sfx_is_mixed_only_in_its_window(tmp_path, sample_video):
    base = ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=0, source_out=3)])
    ref = _render(base, tmp_path, sample_video, "ref")
    doc = base.model_copy(deep=True)
    doc.layers.append(AudioLayer(start=1.0, end=1.9, sfx="hit", gain_db=0))
    out = _render(doc, tmp_path, sample_video, "mix")
    assert _mean_db(out, 1.0, 0.9) > _mean_db(ref, 1.0, 0.9) + 0.5  # el golpe se oye encima de la voz
    assert abs(_mean_db(out, 2.3, 0.5) - _mean_db(ref, 2.3, 0.5)) < 0.3  # fuera de su ventana, igual
    assert abs(_mean_db(out, 0.1, 0.6) - _mean_db(ref, 0.1, 0.6)) < 0.3


def test_several_sfx_and_trimmed_by_layer_end(tmp_path, sample_video):
    doc = ProjectDoc(media_id="m", timeline=[TimelineClip(source_in=0, source_out=3)])
    doc.layers += [AudioLayer(start=0.5, end=0.7, sfx="whoosh", gain_db=-6), AudioLayer(start=2.0, end=2.2, sfx="pop")]
    out = _render(doc, tmp_path, sample_video, "multi")
    assert out.stat().st_size > 0
