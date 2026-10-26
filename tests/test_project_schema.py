import pytest
from pydantic import ValidationError

from cutly.schema import versioning
from cutly.schema.project import (
    CURRENT_VERSION,
    EffectLayer,
    IconLayer,
    ProjectDoc,
    Reframe,
    SubtitleLayer,
    TextLayer,
    TimelineClip,
)


def test_roundtrip_all_layer_types():
    doc = ProjectDoc.model_validate(
        {
            "media_id": "m_1",
            "timeline": [{"source_in": 10, "source_out": 40}],
            "layers": [
                {"type": "text", "end": 5, "text": "Hola\nmundo"},
                {"type": "icon", "end": 3, "asset": "icons/arrow-right", "tint": "#FF0000"},
                {"type": "image", "end": 3, "asset": "overlays/marco"},
                {"type": "shape", "end": 3, "shape": "ellipse"},
                {"type": "subtitle", "end": 30},
                {"type": "effect", "end": 2, "effect": "zoom_punch", "params": {"scale": 1.2}},
            ],
        }
    )
    assert doc.duration == 30 and doc.schema_version == CURRENT_VERSION
    assert ProjectDoc.model_validate(doc.model_dump(mode="json")) == doc


@pytest.mark.parametrize(
    "layer",
    [
        {"type": "text", "end": 5, "text": "x", "style": {"color": "red"}},  # color no hex
        {"type": "text", "end": 5, "text": "x", "style": {"color": "#FFF;drawtext=..."}},  # inyección
        {"type": "text", "end": 5, "text": "mal\x00texto"},  # control
        {"type": "icon", "end": 5, "asset": "../../etc/passwd"},  # ruta
        {"type": "icon", "end": 5, "asset": "icons/a b"},
        {"type": "text", "start": 5, "end": 2, "text": "x"},  # tiempos
        {"type": "effect", "end": 2, "effect": "Zoom Punch"},  # nombre
        {"type": "effect", "end": 2, "effect": "ok", "params": {"a": {"b": {"c": {"d": 1}}}}},  # profundidad
        {"type": "effect", "end": 2, "effect": "ok", "params": {"a": object}},
        {"type": "subtitle", "end": 5, "source": "custom"},  # sin cues
        {"type": "text", "end": 5, "text": "x", "extra_field": 1},  # campos desconocidos
        {"type": "nope", "end": 5},
    ],
)
def test_rejects_unsafe_or_invalid_layers(layer):
    with pytest.raises(ValidationError):
        ProjectDoc.model_validate({"media_id": "m", "layers": [layer]})


def test_reframe_requires_regions_and_even_output():
    with pytest.raises(ValidationError, match="facecam"):
        Reframe(mode="stack", game={"x": 0, "y": 0, "w": 1, "h": 1})
    with pytest.raises(ValidationError, match="se sale"):
        Reframe(mode="game", game={"x": 0.5, "y": 0, "w": 0.8, "h": 1})
    with pytest.raises(ValidationError, match="pares"):
        ProjectDoc.model_validate({"media_id": "m", "output": {"width": 1081, "height": 1920}})
    with pytest.raises(ValidationError, match="repetidos"):
        c = {"id": "c1", "source_in": 0, "source_out": 5}
        ProjectDoc.model_validate({"media_id": "m", "timeline": [c, c]})
    assert TimelineClip(source_in=0, source_out=10, speed=2).duration == 5
    assert isinstance(SubtitleLayer(end=3).style.highlight_color, str)
    assert TextLayer(end=3, text="a").box.y == 0.2 and IconLayer(end=1, asset="icons/x").opacity == 1
    assert EffectLayer(end=1, effect="a").params == {}


def test_schema_migration_machinery(monkeypatch):
    monkeypatch.setattr("cutly.schema.versioning.CURRENT_VERSION", 3)
    monkeypatch.setitem(versioning.MIGRATIONS, 1, lambda d: {**d, "a": 1})
    monkeypatch.setitem(versioning.MIGRATIONS, 2, lambda d: {**d, "b": d["a"] + 1})
    out, changed = versioning.migrate_doc({"schema_version": 1})
    assert changed and out == {"schema_version": 3, "a": 1, "b": 2}
    with pytest.raises(ValueError, match="más nuevo"):
        versioning.migrate_doc({"schema_version": 9})
