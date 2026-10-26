import pytest
from PIL import Image

from cutly.schema.project import (
    Anim,
    Animations,
    Box,
    IconLayer,
    Keyframe,
    Loop,
    ShapeLayer,
    TextLayer,
)
from cutly.services.render import ass as A
from cutly.services.render.animation import ease, eval_props, is_animated, sample_times
from cutly.services.render.sprite import render_sequence


def text(**anim):
    return TextLayer(start=2, end=6, text="x", animations=Animations(**anim))


@pytest.mark.parametrize(
    "name", ["linear", "ease_in", "ease_out", "ease_in_out", "ease_out_back", "ease_out_bounce", "ease_out_elastic"]
)
def test_easing_endpoints(name):
    assert ease(name, 0) == pytest.approx(0, abs=1e-6) and ease(name, 1) == pytest.approx(1, abs=1e-6)


@pytest.mark.parametrize(
    "name", ["fade", "pop", "zoom_in", "slide_up", "slide_down", "slide_left", "slide_right", "bounce", "spin_in"]
)
def test_enter_presets_start_hidden_and_rest_at_identity(name):
    lay = text(enter=Anim(name=name, dur=0.5))
    start = eval_props(lay, 0.0, 0.5, 0.5)
    rest = eval_props(lay, 1.0, 0.5, 0.5)
    assert start.opacity < 0.1 or start.scale < 0.6 or abs(start.dx) + abs(start.dy) > 0.05  # arranca "fuera"
    assert (rest.dx, rest.dy, rest.scale, rest.opacity, rest.rot) == (0, 0, 1, 1, 0)


def test_exit_mirrors_enter_and_ends_hidden():
    lay = text(exit=Anim(name="slide_up", dur=0.5))
    assert eval_props(lay, 1.0, 0.5, 0.5).dy == 0
    end = eval_props(lay, 4.0, 0.5, 0.5)
    assert end.opacity == 0 and end.dy > 0.05  # sale hacia abajo y se desvanece, simétrica a la entrada


def test_keyframes_interpolate_from_base_and_hold():
    lay = IconLayer(end=4, asset="icons/star", animations=Animations(keyframes=[
        Keyframe(t=1, x=0.8, scale=2, easing="linear"), Keyframe(t=2, x=0.2, easing="linear")]))  # fmt: skip
    dx = [eval_props(lay, t, 0.5, 0.5).dx for t in (0, 0.5, 1, 1.5, 2, 3)]
    assert dx == pytest.approx([0, 0.15, 0.3, 0.0, -0.3, -0.3])
    assert eval_props(lay, 3, 0.5, 0.5).scale == 2  # mantiene el último valor


def test_loop_animations_oscillate():
    lay = text(loop=Loop(name="pulse", period=1, amount=0.1))
    vals = [eval_props(lay, t / 8, 0.5, 0.5).scale for t in range(8)]
    assert max(vals) > 1.05 and min(vals) < 0.95
    assert is_animated(lay) and not is_animated(text())


def test_sample_times_dense_only_where_moving():
    lay = text(enter=Anim(name="pop", dur=0.4))
    ts = sample_times(lay)
    assert ts[0] == 0 and ts[-1] == 4 and len(ts) == 8  # 0..0.4 en 6 pasos + reposo hasta 4 s
    assert sample_times(text()) == [0.0, 4.0]


def test_ass_events_segment_animation_and_stay_contiguous():
    lay = TextLayer(start=1, end=3, text="Hola", animations=Animations(enter=Anim(name="pop", dur=0.3)))
    _, ev = A.text_events(lay, 1080, 1920, [])
    assert len(ev) > 3 and "\\t(0," in ev[0] and "\\pos(" in ev[-1]
    ends = [e.split(",")[2] for e in ev[:-1]]
    starts = [e.split(",")[1] for e in ev[1:]]
    assert ends == starts  # sin huecos ni solapes entre tramos
    static = A.text_events(TextLayer(end=2, text="x"), 1080, 1920, [])[1]
    assert len(static) == 1 and "\\t(" not in static[0]


def test_shape_is_centered_for_scaling():
    _, ev = A.shape_events(ShapeLayer(end=2, box=Box(x=0.5, y=0.5, w=0.4, h=0.1)), 1000, 2000, [])
    assert "\\an5" in ev[0] and "\\pos(500,1000)" in ev[0]


def test_sprite_sequence_frames_bbox_and_dedup(tmp_path):
    png = tmp_path / "icon.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(png)
    lay = IconLayer(start=0, end=2, asset="icons/star", box=Box(x=0.5, y=0.5, w=0.2),
                    animations=Animations(enter=Anim(name="slide_left", dur=0.5)))  # fmt: skip
    warns: list[str] = []
    seq = render_sequence(png, lay, 1000, 1000, 10, tmp_path / "seq", warns)
    assert seq and seq.frames == 21 and len(list((tmp_path / "seq").glob("f*.png"))) == 21
    first = Image.open(tmp_path / "seq" / "f00000.png")
    assert (
        first.getchannel("A").getextrema()[1] == 0 or first.getchannel("A").getextrema()[1] < 40
    )  # arranca casi invisible
    last = Image.open(tmp_path / "seq" / "f00020.png")
    assert last.getchannel("A").getextrema()[1] == 255 and last.size == first.size
    assert seq.x > 300 and seq.x + first.width < 1000  # la caja cubre todo el recorrido, dentro de la pantalla
    off = IconLayer(
        end=2, asset="icons/star", box=Box(x=1.4, y=0.5, w=0.1), animations=Animations(loop=Loop(name="pulse"))
    )
    assert (
        render_sequence(png, off, 1000, 1000, 10, tmp_path / "off", warns) is None
        and "fuera de la pantalla" in warns[-1]
    )


def test_rotation_is_clockwise_like_ass_and_ffmpeg(tmp_path):
    """Un giro positivo es horario en toda la tubería: una imagen con la mitad izquierda roja gira 90° y queda roja ARRIBA."""  # noqa: E501
    png = tmp_path / "half.png"
    img = Image.new("RGBA", (40, 20), (0, 0, 255, 255))
    img.paste((255, 0, 0, 255), (0, 0, 20, 20))
    img.save(png)
    lay = IconLayer(
        end=1,
        asset="icons/star",
        box=Box(x=0.5, y=0.5, w=0.2, h=0.1, rotation=90),
        animations=Animations(loop=Loop(name="blink", amount=0)),
    )
    seq = render_sequence(png, lay, 400, 400, 10, tmp_path / "rot", [])
    frame = Image.open(tmp_path / "rot" / "f00000.png").convert("RGBA")
    w, h = frame.size
    top, bottom = frame.getpixel((w // 2, 6)), frame.getpixel((w // 2, h - 7))
    assert seq and top[0] > 200 and top[2] < 60 and bottom[2] > 200 and bottom[0] < 60  # rojo arriba, azul abajo


def test_subtitle_lines_balance_and_avoid_orphans():
    assert A._lines(["aprender", "cómo", "se"], 2) == [[0, 1, 2]]  # cabe en una línea
    assert A._lines(["aplicaciones", "en", "Linux,"], 2) == [[0], [1, 2]]  # equilibrado por letras
    assert A._lines(["los", "repositorios", "del"], 2) in ([[0], [1, 2]], [[0, 1], [2]])
    assert A._lines(["uno", "dos"], 1) == [[0, 1]]
    assert A._lines(["x"], 2) == [[0]]
