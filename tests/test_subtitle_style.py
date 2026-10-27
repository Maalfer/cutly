"""Estilo de subtítulos: énfasis por palabra, espaciado, sombra y animación fade_pop (ASS)."""

import pytest
from pydantic import ValidationError

from cutly.schema.project import SubtitleLayer, SubtitleStyle
from cutly.services.render.ass import _norm_word, subtitle_events

WORDS = [(0.0, 0.5, "te"), (0.5, 1.0, "genera"), (1.0, 2.0, "Miniaturas,")]


def _events(**style):
    layer = SubtitleLayer(end=10, style=SubtitleStyle(highlight_color=None, **style))
    return subtitle_events(layer, WORDS, 1080, 1920)


def test_norm_word_ignores_case_accents_punctuation():
    assert _norm_word("¡Títulos!") == _norm_word("titulos") == "titulos"


def test_emphasis_matches_word_and_reverts_style():
    emph = [{"words": ["miniaturas"], "scale": 1.2, "color": "#FFD400", "font": "Inter ExtraBold"}]
    _, ev = _events(size=0.05, max_words_per_cue=3, emphasis=emph)
    for e in ev:
        assert "\\fs115.2" in e and "\\fnInter ExtraBold" in e and "\\1c&H0000D4FF" in e
        assert e.endswith("\\fs96.0\\fnDejaVu Sans}")  # vuelve a tamaño, color y fuente base tras la palabra
        assert "Miniaturas," in e


def test_emphasis_scale_shrinks_when_line_does_not_fit():
    emph = [{"words": ["miniaturas"], "scale": 3}]
    _, ev = _events(size=0.05, max_words_per_cue=1, emphasis=emph)
    big = max(float(e.split("\\fs")[1].split("\\")[0].split("}")[0]) for e in ev if "\\fs" in e and "Miniaturas" in e)
    assert 96 < big < 96 * 3  # ampliada, pero limitada al ancho de 1080 px


def test_letter_spacing_shadow_and_fade_pop():
    style, ev = _events(letter_spacing=0.01, shadow=0.002, shadow_blur=0.001, animation="fade_pop", max_words_per_cue=1)
    assert ",19.20,0,1," in style[0] or "19.20" in style[0]
    assert "\\fad(70,0)" in ev[0] and "\\blur" in ev[0]


def test_defaults_do_not_change_plain_output():
    _, ev = _events(max_words_per_cue=3)
    assert "\\fs" not in ev[0] and "\\fad" not in ev[0] and "\\blur" not in ev[0]


def test_emphasis_validation():
    with pytest.raises(ValidationError):
        SubtitleStyle(emphasis=[{"words": [], "scale": 1}])
    with pytest.raises(ValidationError):
        SubtitleStyle(emphasis=[{"words": ["a"], "scale": 9}])


def test_cues_never_overlap_in_time():
    words = [(0.0, 0.5, "uno"), (0.5, 1.0, "dos"), (1.02, 1.5, "tres"), (1.5, 2.0, "cuatro")]
    layer = SubtitleLayer(end=10, style=SubtitleStyle(highlight_color=None, max_words_per_cue=2))
    _, ev = subtitle_events(layer, words, 1080, 1920)
    spans = []
    for e in ev:
        parts = e.split(",")
        spans.append((parts[1], parts[2], "tres" in e or "cuatro" in e))
    first_cue_end = max(sp[1] for sp in spans if not sp[2])
    second_cue_start = min(sp[0] for sp in spans if sp[2])
    assert first_cue_end <= second_cue_start
