"""Generación de ficheros ASS (libass) para subtítulos, textos y formas.

Todo texto que llega aquí es no confiable (palabras del directo, textos del proyecto): se escapa
con `ass_escape` antes de entrar en un evento.
"""

from dataclasses import dataclass
from itertools import combinations

from cutly.schema.project import (
    ShapeLayer,
    SubtitleLayer,
    SubtitleStyle,
    TextLayer,
    TimelineClip,
    timeline_starts,
)
from cutly.services.render.animation import eval_props, is_animated, sample_times

DEFAULT_FONT = "DejaVu Sans"
PAUSE_BREAK = 0.8  # una pausa mayor corta la frase de subtítulos


def ass_escape(text: str) -> str:
    """Quita lo que libass interpretaría como código: llaves, barras invertidas y saltos."""
    return (text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\r", "").replace("\n", " ")).strip()


def font_name(name: str) -> str:
    return DEFAULT_FONT if name == "default" else name


def ass_color(hexcolor: str, opacity: float = 1.0) -> str:
    """#RRGGBB[AA] → &HAABBGGRR (en ASS el alfa 00 es opaco)."""
    h = hexcolor.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    a = int(h[6:8], 16) if len(h) == 8 else 255
    alpha = 255 - round(a * opacity)
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def alpha_of(hexcolor: str | None) -> float:
    """Opacidad (0-1) incluida en un #RRGGBBAA; 1 si no lleva canal alfa."""
    if hexcolor and len(hexcolor.lstrip("#")) == 8:
        return int(hexcolor.lstrip("#")[6:8], 16) / 255
    return 1.0


def ass_time(sec: float) -> str:
    sec = max(sec, 0)
    cs = round(sec * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


# --- Tiempos: del vídeo original al clip resultante --------------------------------------------------------


@dataclass
class Segment:
    out_start: float
    out_end: float
    src_in: float
    src_out: float
    speed: float


def build_time_map(timeline: list[TimelineClip]) -> list[Segment]:
    return [
        Segment(s, s + c.duration, c.source_in, c.source_out, c.speed)
        for s, c in zip(timeline_starts(timeline), timeline, strict=True)
    ]


def map_words(words: list[dict], tmap: list[Segment]) -> list[tuple[float, float, str]]:
    """Palabras del original → (inicio, fin, texto) en el tiempo del clip resultante."""
    out = []
    for w in words:
        for seg in tmap:
            if w["end"] > seg.src_in and w["start"] < seg.src_out:
                s = seg.out_start + (max(w["start"], seg.src_in) - seg.src_in) / seg.speed
                e = seg.out_start + (min(w["end"], seg.src_out) - seg.src_in) / seg.speed
                if e - s > 0.01:
                    out.append((s, e, w["w"]))
                break
    return out


# --- Cabecera y estilos ---------------------------------------------------------------------------------------


def header(width: int, height: int, styles: list[str]) -> str:
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\nYCbCr Matrix: None\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) + "\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def style_line(name, font, size_px, primary, outline_c, back_c, bold, italic, border_style, outline_px, an, ml, mr, mv):
    return (
        f"Style: {name},{font},{size_px:.1f},{primary},{primary},{outline_c},{back_c},{-1 if bold else 0},"
        f"{-1 if italic else 0},0,0,100,100,0,0,{border_style},{outline_px:.1f},0,{an},{ml},{mr},{mv},1"
    )


def dialogue(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}"


# --- Subtítulos ----------------------------------------------------------------------------------------------------


def group_cues(words: list[tuple[float, float, str]], max_words: int) -> list[list[tuple[float, float, str]]]:
    """Agrupa palabras en frases cortas: por nº máximo, pausas largas y puntuación de cierre."""
    cues, cur = [], []
    for w in words:
        if cur and w[0] - cur[-1][1] > PAUSE_BREAK:
            cues.append(cur)
            cur = []
        cur.append(w)
        ends_sentence = w[2].rstrip("\"'»”)").endswith((".", "!", "?", "…"))
        if len(cur) >= max_words or ends_sentence:
            cues.append(cur)
            cur = []
    if cur:
        cues.append(cur)
    return cues


LINE_CHARS = (
    17  # por encima, la frase se reparte en dos líneas (a ~83 px una línea de 17 letras cabe holgada en 1080 px)
)


def _lines(texts: list[str], max_lines: int) -> list[list[int]]:
    """Reparte los índices de palabra en líneas equilibradas por nº de letras: una sola línea si cabe, y nunca una
    palabra huérfana si se puede evitar."""
    n = len(texts)
    total = sum(len(t) for t in texts) + n - 1
    if max_lines <= 1 or n < 2 or total <= LINE_CHARS:
        return [list(range(n))]
    k = min(max_lines, n)
    best: tuple[int, list[list[int]]] | None = None
    for cuts in combinations(range(1, n), k - 1):
        bounds = [0, *cuts, n]
        groups = [list(range(bounds[i], bounds[i + 1])) for i in range(k)]
        longest = max(sum(len(texts[j]) for j in g) + len(g) - 1 for g in groups)
        if best is None or longest < best[0]:
            best = (longest, groups)
    return best[1]  # type: ignore[index]


def subtitle_events(
    layer: SubtitleLayer, words: list[tuple[float, float, str]], width: int, height: int
) -> tuple[list[str], list[str]]:
    """(líneas de estilo, líneas Dialogue) de una layer de subtítulos."""
    st: SubtitleStyle = layer.style
    size_px = st.size * height
    outline_px = st.outline_width * height
    border = 3 if st.bg_color else 1
    outline_c = ass_color(st.bg_color) if st.bg_color else ass_color(st.outline_color)
    name = f"Sub_{layer.id}".replace("-", "_")
    style = style_line(name, font_name(st.font), size_px, ass_color(st.color), outline_c, ass_color("#00000080"),
                       st.bold, False, border, outline_px if not st.bg_color else size_px * 0.18, 5,
                       int(width * 0.06), int(width * 0.06), 0)  # fmt: skip
    z = layer.z + 100
    pos = f"\\an5\\pos({width // 2},{round(st.position_y * height)})"
    base_c, hl_c = ass_color(st.color), ass_color(st.highlight_color or st.color)
    events = []
    if layer.source == "custom":
        words = []
        for cue in layer.cues:
            toks = cue.text.split()
            step = (cue.end - cue.start) / max(len(toks), 1)
            words += [(cue.start + i * step, cue.start + (i + 1) * step, t) for i, t in enumerate(toks)]
    words = [(max(s, layer.start), min(e, layer.end), t) for s, e, t in words if e > layer.start and s < layer.end]
    for cue in group_cues(words, st.max_words_per_cue):
        texts = [ass_escape(w[2]).upper() if st.uppercase else ass_escape(w[2]) for w in cue]
        lines = _lines(texts, st.max_lines)
        cue_end = cue[-1][1] + 0.12
        for i, (s, _e, _t) in enumerate(cue):
            end = cue[i + 1][0] if i + 1 < len(cue) else cue_end
            parts = []
            for idxs in lines:
                seg = []
                for j in idxs:
                    if j == i and st.animation != "none" and st.highlight_color:
                        pop = "\\fscx80\\fscy80\\t(0,90,\\fscx112\\fscy112)" if st.animation == "pop" else ""
                        seg.append(f"{{\\1c{hl_c}{pop}}}{texts[j]}{{\\1c{base_c}\\fscx100\\fscy100}}")
                    else:
                        seg.append(texts[j])
                parts.append(" ".join(seg))
            start = cue[0][0] if i == 0 else s
            events.append(dialogue(z, start, end, name, "{" + pos + "}" + "\\N".join(parts)))
    return [style], events


# --- Texto y formas ---------------------------------------------------------------------------------------------------

_AN = {
    "top_left": 7,
    "top_center": 8,
    "top_right": 9,
    "center": 5,
    "bottom_left": 1,
    "bottom_center": 2,
    "bottom_right": 3,
}
_FACTOR = {"left": 0.0, "center": 0.5, "right": 1.0}


def _anchor_parts(anchor: str) -> str:
    return "left" if anchor.endswith("left") else "right" if anchor.endswith("right") else "center"


def _a(v: float) -> str:
    return f"&H{round(255 * (1 - min(max(v, 0.0), 1.0))):02X}&"


def _alpha_tags(opacity: float, base: tuple[float, float, float]) -> str:
    """Opacidad de la animación aplicada a cada componente (relleno, borde/caja, sombra) sin perder su transparencia propia."""
    return f"\\1a{_a(base[0] * opacity)}\\3a{_a(base[1] * opacity)}\\4a{_a(base[2] * opacity)}"


def animated_events(
    layer, base_x: float, base_y: float, base_rot: float, width: int, height: int, style: str, body: str,
    prefix: str = "",
    base: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> list[str]:  # fmt: skip
    """Un evento por tramo de la curva de animación (o uno solo si la layer es estática).

    Cada tramo interpola linealmente posición (\\move), escala, rotación y opacidad (\\t) entre dos muestras
    del motor de animación; el easing queda aproximado por el muestreo (15 por segundo).
    """
    length = layer.end - layer.start
    times = sample_times(layer) if is_animated(layer) else [0.0, length]
    events = []
    for ta, tb in zip(times, times[1:], strict=False):
        pa = eval_props(layer, ta, base_x, base_y, base_rot)
        pb = eval_props(layer, tb, base_x, base_y, base_rot)
        dur = max(round((tb - ta) * 1000), 1)
        x1, y1 = base_x * width + pa.dx * width, base_y * height + pa.dy * height
        x2, y2 = base_x * width + pb.dx * width, base_y * height + pb.dy * height
        moving = abs(x1 - x2) > 0.5 or abs(y1 - y2) > 0.5
        tags = f"\\move({x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f},0,{dur})" if moving else f"\\pos({x1:.0f},{y1:.0f})"
        tags += f"\\fscx{pa.scale * 100:.0f}\\fscy{pa.scale * 100:.0f}\\frz{-(base_rot + pa.rot):g}{_alpha_tags(pa.opacity, base)}"
        changes = ""
        if abs(pa.scale - pb.scale) > 1e-3:
            changes += f"\\fscx{pb.scale * 100:.0f}\\fscy{pb.scale * 100:.0f}"
        if abs(pa.rot - pb.rot) > 1e-2:
            changes += f"\\frz{-(base_rot + pb.rot):g}"
        if abs(pa.opacity - pb.opacity) > 1e-3:
            changes += _alpha_tags(pb.opacity, base)
        if changes:
            tags += f"\\t(0,{dur},{changes})"
        events.append(
            dialogue(layer.z + 100, layer.start + ta, layer.start + tb, style, "{" + prefix + tags + "}" + body)
        )
    return events


def text_events(layer: TextLayer, width: int, height: int, warnings: list[str]) -> tuple[list[str], list[str]]:
    st, box = layer.style, layer.box
    h = _anchor_parts(box.anchor)
    left_edge = box.x - box.w * _FACTOR[h]
    ml, mr = max(0, round(left_edge * width)), max(0, round(width - (left_edge + box.w) * width))
    name = f"Txt_{layer.id}".replace("-", "_")
    border = 3 if st.bg_color else 1
    outline_c = ass_color(st.bg_color) if st.bg_color else ass_color(st.outline_color)
    style = style_line(name, font_name(st.font), st.size * height, ass_color(st.color), outline_c,
                       ass_color("#00000080"), st.bold, st.italic, border,
                       st.outline_width * height if not st.bg_color else st.size * height * 0.2, _AN[box.anchor], ml, mr, 0)  # fmt: skip
    text = "\\N".join(ass_escape(t) for t in layer.text.split("\n"))
    if st.uppercase:
        text = text.upper()
    base = (alpha_of(st.color), alpha_of(st.bg_color if st.bg_color else st.outline_color), 1.0)
    return [style], animated_events(layer, box.x, box.y, box.rotation, width, height, name, text, base=base)


def shape_events(layer: ShapeLayer, width: int, height: int, warnings: list[str]) -> tuple[list[str], list[str]]:
    box = layer.box
    w = box.w * width
    h = box.h * height if box.h else w
    h_part, v_part = _anchor_parts(box.anchor), box.anchor.split("_")[0]
    x0 = box.x * width - w * _FACTOR[h_part]
    y0 = box.y * height - h * (0.0 if v_part == "top" else 1.0 if v_part == "bottom" else 0.5)
    # el dibujo se centra en su punto (\\an5): así escala y rota alrededor de su centro
    base_x, base_y = (x0 + w / 2) / width, (y0 + h / 2) / height
    if layer.shape == "rect":
        path = f"m 0 0 l {w:.0f} 0 {w:.0f} {h:.0f} 0 {h:.0f}"
    else:
        k, rx, ry = 0.5523, w / 2, h / 2
        path = (
            f"m 0 {ry:.0f} b 0 {ry * (1 - k):.0f} {rx * (1 - k):.0f} 0 {rx:.0f} 0 "
            f"{rx * (1 + k):.0f} 0 {w:.0f} {ry * (1 - k):.0f} {w:.0f} {ry:.0f} "
            f"{w:.0f} {ry * (1 + k):.0f} {rx * (1 + k):.0f} {h:.0f} {rx:.0f} {h:.0f} "
            f"{rx * (1 - k):.0f} {h:.0f} 0 {ry * (1 + k):.0f} 0 {ry:.0f}"
        )
    fill = ass_color(layer.fill)[:2] + ass_color(layer.fill)[4:] if layer.fill else "&H000000"
    fill = "&H" + fill.replace("&H", "")[-6:] + "&" if layer.fill else "&H000000&"
    fill_alpha = ""
    stroke = (
        f"\\3c&H{ass_color(layer.stroke)[-6:]}&\\bord{layer.stroke_width * height:.1f}" if layer.stroke else "\\bord0"
    )
    name = "Shape"
    style = style_line(name, DEFAULT_FONT, 20, "&H00FFFFFF", "&H00000000", "&H00000000", False, False, 1, 0, 5, 0, 0, 0)
    prefix = f"\\an5\\1c{fill}{fill_alpha}{stroke}\\p1"
    base = (alpha_of(layer.fill) if layer.fill else 0.0, alpha_of(layer.stroke) if layer.stroke else 0.0, 0.0)
    evs = animated_events(layer, base_x, base_y, box.rotation, width, height, name, path + "{\\p0}", prefix, base)
    return [style], evs


def build_ass(width: int, height: int, styles: list[str], events: list[str]) -> str:
    return header(width, height, list(dict.fromkeys(styles))) + "\n".join(events) + "\n"
