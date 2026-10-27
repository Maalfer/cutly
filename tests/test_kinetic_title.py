"""Títulos cinéticos: construcción de la capa y validación (sin arrancar el navegador)."""

import pytest
from pydantic import ValidationError

from cutly.schema.project import SceneLayer
from cutly.services.scene_js.kinetic import KIT, STYLES, TitleSpec, build_title_layer


def _spec(**kw):
    return TitleSpec.model_validate({"start": 1, "end": 5, "lines": [{"text": "11 Skills"}], **kw})


def test_layer_is_transparent_full_frame_code_scene():
    layer = build_title_layer(_spec(lines=[{"text": "11 Skills", "style": "title"}, {"text": "a la vez", "style": "kicker"}]))
    assert isinstance(layer, SceneLayer) and layer.transparent and layer.code == KIT.read_text()
    assert (layer.start, layer.end, layer.params["duration"]) == (1, 5, 4.0)
    first, second = layer.params["lines"]
    assert first["font"] == STYLES["title"]["font"] and second["in"] == "tracking" and second["text"] == "a la vez"


def test_overrides_win_over_style_and_alias_in():
    layer = build_title_layer(_spec(lines=[{"text": "hola", "style": "title", "size": 90, "in": "rise", "color": "#ff0000"}]))
    ln = layer.params["lines"][0]
    assert ln["size"] == 90 and ln["in"] == "rise" and ln["color"] == "#ff0000"


def test_explicit_color_replaces_style_gradient_only_when_requested():
    ln = build_title_layer(_spec(lines=[{"text": "x", "style": "title", "gradient": "#000000 #333333"}])).params["lines"][0]
    assert ln["gradient"] == "#000000 #333333"


def test_validation_errors():
    with pytest.raises(ValidationError):
        _spec(lines=[])
    with pytest.raises(ValidationError):
        _spec(lines=[{"text": "x", "gradient": "rojo"}])
    with pytest.raises(ValidationError):
        _spec(lines=[{"text": "x", "in": "volar"}])
    with pytest.raises(ValidationError):
        _spec(lines=[{"text": "x", "nope": 1}])


def test_transparent_requires_code():
    with pytest.raises(ValidationError):
        SceneLayer(end=3, template="title_card", transparent=True)
