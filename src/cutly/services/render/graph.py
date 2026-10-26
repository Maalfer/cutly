"""Construcción del filtergraph y del comando FFmpeg a partir de un ProjectDoc.

Un solo comando por clip: una entrada por trozo de línea de tiempo (con `-ss` previo, así no se decodifica
el directo entero), reencuadre vertical, concat, color, capas por orden de z y audio normalizado.
Todo valor que llega al grafo es numérico formateado aquí, un color ya validado o una ruta que genera el
propio servidor (se comprueba su alfabeto).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from cutly.registry import effects as fx_registry
from cutly.schema.project import (
    EffectLayer,
    IconLayer,
    ImageLayer,
    ProjectDoc,
    Rect,
    Reframe,
    SceneLayer,
    ShapeLayer,
    SubtitleLayer,
    TextLayer,
    TimelineClip,
    timeline_starts,
)
from cutly.services.render import ass as A
from cutly.services.render.animation import is_animated
from cutly.services.render.effects_api import EffectBuildError, EffectCtx
from cutly.services.render.rasterize import rasterize
from cutly.services.render.sprite import render_sequence
from cutly.services.scene.sequence import render_scene_sequence
from cutly.services.scene.templates import TemplateError

_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./\-]+$")
_FACTOR = {"left": 0.0, "center": 0.5, "right": 1.0}


@dataclass
class MediaInfo:
    path: str
    width: int
    height: int
    has_audio: bool


@dataclass
class RenderOpts:
    workdir: Path
    draft: bool = False
    encoder: str = "libx264"
    threads: int = 0
    fonts_dir: Path | None = None
    scale: float | None = None  # factor sobre la resolución de salida; por defecto 1/3 en borrador y 1 en final
    with_audio: bool = True

    @property
    def factor(self) -> float:
        return self.scale if self.scale is not None else (1 / 3 if self.draft else 1.0)

    @property
    def light(self) -> bool:
        """Calidad reducida de codificación (borradores y vistas previas)."""
        return self.draft or self.factor < 1


@dataclass
class RenderPlan:
    inputs: list[str]
    graph: str
    width: int
    height: int
    duration: float
    fps: int
    warnings: list[str] = field(default_factory=list)


def even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def safe_path(p: Path | str) -> str:
    s = str(p)
    if not _SAFE_PATH.match(s):
        raise ValueError(f"Ruta con caracteres no permitidos para FFmpeg: {s}")
    return s


def safe_pattern(p: str) -> str:
    """Ruta de secuencia de imágenes: igual que safe_path pero admitiendo solo el patrón exacto `%05d`."""
    if p.count("%05d") != 1:
        raise ValueError("Patrón de secuencia inválido")
    safe_path(p.replace("%05d", "00000"))
    return p


def atempo_chain(speed: float) -> str:
    """atempo solo admite 0,5–2 por instancia: se encadenan."""
    if abs(speed - 1) < 1e-6:
        return ""
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={f(s)}")
    return ",".join(parts)


def _region(label_in: str, rect: Rect, sw: int, sh: int, tw: int, th: int, fit: str, tag: str) -> tuple[list[str], str]:
    x, y, w, h = even(rect.x * sw), even(rect.y * sh), even(rect.w * sw), even(rect.h * sh)
    x, y = min(x, sw - 2), min(y, sh - 2)
    w, h = min(w, sw - x), min(h, sh - y)
    crop = f"crop={w}:{h}:{x}:{y}"
    if fit == "contain":
        return [
            f"[{label_in}]{crop},split=2[{tag}bs][{tag}fs]",
            f"[{tag}bs]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=20:2[{tag}bb]",
            f"[{tag}fs]scale={tw}:{th}:force_original_aspect_ratio=decrease[{tag}ff]",
            f"[{tag}bb][{tag}ff]overlay=(W-w)/2:(H-h)/2[{tag}o]",
        ], f"{tag}o"
    return [
        f"[{label_in}]{crop},scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}[{tag}o]"
    ], f"{tag}o"


def reframe(rf: Reframe, label_in: str, i: int, sw: int, sh: int, W: int, H: int) -> tuple[list[str], str]:
    tag = f"r{i}"
    if rf.mode == "center":
        aspect = W / H
        cw, ch = (sh * aspect, sh) if sw / sh > aspect else (sw, sw / aspect)
        x = min(max(rf.center_x * sw - cw / 2, 0), sw - cw)
        y = (sh - ch) / 2
        return [
            f"[{label_in}]crop={even(cw)}:{even(ch)}:{int(x) // 2 * 2}:{int(y) // 2 * 2},scale={W}:{H}:flags=lanczos[{tag}o]"
        ], f"{tag}o"
    if rf.mode == "stack":
        top_h = even(H * rf.stack_split)
        fr1, top = _region(f"{tag}a", rf.facecam, sw, sh, W, top_h, "cover", f"{tag}t")  # type: ignore[arg-type]
        fr2, bot = _region(f"{tag}b", rf.game, sw, sh, W, H - top_h, rf.game_fit, f"{tag}g")  # type: ignore[arg-type]
        return [f"[{label_in}]split=2[{tag}a][{tag}b]", *fr1, *fr2, f"[{top}][{bot}]vstack[{tag}o]"], f"{tag}o"
    rect = rf.facecam if rf.mode == "facecam" else rf.game
    return _region(label_in, rect, sw, sh, W, H, rf.game_fit if rf.mode != "facecam" else "cover", tag)  # type: ignore[arg-type]


def audio_clip_fragments(doc: ProjectDoc, media: MediaInfo) -> list[str]:
    """Por cada clip: su audio (con velocidad) o silencio si el original no tiene pista. Etiquetas [ca{i}]."""
    out = []
    for i, c in enumerate(doc.timeline):
        if media.has_audio:
            chain = ",".join(
                x
                for x in (
                    "asetpts=PTS-STARTPTS",
                    atempo_chain(c.speed),
                    "aresample=48000",
                    "aformat=channel_layouts=stereo",
                )
                if x
            )
            out.append(f"[{i}:a]{chain}[ca{i}]")
        else:
            out.append(f"anullsrc=r=48000:cl=stereo:d={f(c.duration)}[ca{i}]")
    return out


def user_audio_chain(doc: ProjectDoc) -> list[str]:
    chain = []
    if doc.audio.gain_db:
        chain.append(f"volume={f(doc.audio.gain_db)}dB")
    if doc.audio.denoise:
        chain.append("afftdn=nf=-25")
    return chain


def has_transitions(doc: ProjectDoc) -> bool:
    return any(c.transition_in for c in doc.timeline[1:])


def video_join(doc: ProjectDoc, out: str = "vc0") -> list[str]:
    """Une los clips de vídeo ([cv0]…[cvN]) con cortes (concat) o transiciones (xfade) según cada clip."""
    n = len(doc.timeline)
    if not has_transitions(doc):
        return ["".join(f"[cv{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[{out}]"]
    g, cur, cum = [], "cv0", doc.timeline[0].duration
    for i in range(1, n):
        c, label = doc.timeline[i], (out if i == n - 1 else f"j{i}")
        if c.transition_in:
            tr = c.transition_in
            g.append(f"[{cur}][cv{i}]xfade=transition={tr.name}:duration={f(tr.dur)}:offset={f(cum - tr.dur)}[{label}]")
            cum += c.duration - tr.dur
        else:
            g.append(f"[{cur}][cv{i}]concat=n=2:v=1:a=0[{label}]")
            cum += c.duration
        cur = label
    return g


def audio_join(doc: ProjectDoc, out: str = "ac") -> list[str]:
    """Une el audio de los clips ([ca0]…[caN]) con cortes o fundidos cruzados que acompañan a las transiciones de vídeo."""
    n = len(doc.timeline)
    if not has_transitions(doc):
        return ["".join(f"[ca{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[{out}]"]
    g, cur = [], "ca0"
    for i in range(1, n):
        c, label = doc.timeline[i], (out if i == n - 1 else f"aj{i}")
        if c.transition_in:
            g.append(f"[{cur}][ca{i}]acrossfade=d={f(c.transition_in.dur)}:c1=tri:c2=tri[{label}]")
        else:
            g.append(f"[{cur}][ca{i}]concat=n=2:v=0:a=1[{label}]")
        cur = label
    return g


def build_measure_command(doc: ProjectDoc, media: MediaInfo, workdir: Path) -> list[str]:
    """Pasada solo de audio para medir el volumen integrado (EBU R128) con las mismas cadenas que el render."""
    workdir.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    for c in doc.timeline:
        inputs += ["-vn", "-ss", f(c.source_in), "-t", f(c.source_out - c.source_in), "-i", safe_path(media.path)]
    g = audio_clip_fragments(doc, media)
    g += audio_join(doc)
    g.append(f"[ac]{','.join([*user_audio_chain(doc), 'ebur128=peak=true:framelog=quiet'])}[am]")
    graph_file = workdir / "measure.txt"
    graph_file.write_text(";\n".join(g), encoding="utf-8")
    return [
        "ffmpeg", "-nostdin", "-hide_banner", "-threads", "1", "-filter_complex_threads", "1", *inputs,
        "-filter_complex_script", safe_path(graph_file), "-map", "[am]", "-f", "null", "-",
    ]  # fmt: skip


def gain_from_loudness(stderr: str, target_lufs: float) -> float | None:
    """Ganancia (dB) que lleva el volumen integrado medido al objetivo; None si no hay señal medible."""
    m = re.findall(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS", stderr)
    if not m:
        return None
    measured = float(m[-1])
    if measured < -60:  # silencio o casi: no se amplifica ruido
        return None
    return max(-20.0, min(20.0, target_lufs - measured))


def slice_timeline(doc: ProjectDoc, t0: float, t1: float) -> list[TimelineClip]:
    """Clips (parciales) que caen en la ventana [t0, t1] del clip resultante. Conservan id y velocidad."""
    out: list[TimelineClip] = []
    for start, c in zip(timeline_starts(doc.timeline), doc.timeline, strict=True):
        end = start + c.duration
        a, b = max(start, t0), min(end, t1)
        if b - a > 0.02:
            out.append(c.model_copy(update={"source_in": c.source_in + (a - start) * c.speed,
                                            "source_out": c.source_in + (b - start) * c.speed}))  # fmt: skip
    # una transición solo se conserva si ambos clips siguen cubriendo al menos el doble de su duración
    for i, c in enumerate(out):
        tr = c.transition_in
        if tr and (i == 0 or out[i - 1].duration < 2 * tr.dur or c.duration < 2 * tr.dur):
            out[i] = c.model_copy(update={"transition_in": None})
    return out


def build_plan(
    doc: ProjectDoc,
    media: MediaInfo,
    words: list[dict],
    opts: RenderOpts,
    norm_gain_db: float | None = None,
    window: tuple[float, float] | None = None,
) -> RenderPlan:
    """`window=(t0, t1)` renderiza solo ese tramo del clip resultante conservando los tiempos ABSOLUTOS: se recortan
    los clips de entrada y el reloj del vídeo se desplaza t0, así capas, subtítulos y efectos no se tocan."""
    if not doc.timeline:
        raise ValueError("La línea de tiempo está vacía: añade un clip (add_clip) antes de renderizar")
    W, H = doc.output.width, doc.output.height
    if opts.factor != 1:
        W, H = even(W * opts.factor), even(H * opts.factor)
    fps, sw, sh = doc.output.fps, media.width, media.height
    duration = doc.duration
    full_doc = doc
    t_off = 0.0
    if window:
        t0, t1 = max(0.0, window[0]), min(duration, window[1])
        if t1 - t0 < 0.05:
            raise ValueError(f"La ventana {window} cae fuera del clip (dura {duration:g} s)")
        doc = doc.model_copy(update={"timeline": slice_timeline(doc, t0, t1)})
        t_off, duration = t0, t1 - t0
    opts.workdir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    inputs: list[str] = []
    g: list[str] = []

    # 1) un trozo de entrada por clip de la línea de tiempo
    for c in doc.timeline:
        inputs += ["-ss", f(c.source_in), "-t", f(c.source_out - c.source_in), "-i", safe_path(media.path)]
    for i, c in enumerate(doc.timeline):
        g.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{f(c.speed)},fps={fps}[v{i}]")
        frags, out = reframe(doc.reframe, f"v{i}", i, sw, sh, W, H)
        g += frags
        g.append(f"[{out}]setsar=1[cv{i}]")
    n = len(doc.timeline)
    if opts.with_audio and not has_transitions(doc):
        g += audio_clip_fragments(doc, media)
        g.append("".join(f"[cv{i}][ca{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc0][ac]")
    else:  # con transiciones, vídeo y audio se pliegan por separado (xfade / acrossfade)
        g += video_join(doc)
        if opts.with_audio:
            g += audio_clip_fragments(doc, media)
            g += audio_join(doc)
    g.append(f"[vc0]setpts=PTS+{f(t_off)}/TB[vc]" if t_off else "[vc0]null[vc]")

    # 2) color
    cur = "vc"
    col = doc.color
    if (col.brightness, col.contrast, col.saturation, col.gamma) != (0, 1, 1, 1):
        g.append(
            f"[{cur}]eq=brightness={f(col.brightness)}:contrast={f(col.contrast)}:saturation={f(col.saturation)}:gamma={f(col.gamma)}[vcol]"
        )
        cur = "vcol"

    # 3) capas por orden de z (las de ASS se agrupan mientras sean consecutivas)
    tmap = A.build_time_map(full_doc.timeline)
    mapped_words = A.map_words(words, tmap)
    ass_styles: list[str] = []
    ass_events: list[str] = []
    counters = {"ass": 0, "ov": 0}
    extra_inputs = len(doc.timeline)

    def flush_ass():
        nonlocal cur
        if not ass_events:
            return
        k = counters["ass"] = counters["ass"] + 1
        path = opts.workdir / f"layers{k}.ass"
        path.write_text(A.build_ass(W, H, ass_styles, ass_events), encoding="utf-8")
        fonts = f":fontsdir='{safe_path(opts.fonts_dir)}'" if opts.fonts_dir else ""
        g.append(f"[{cur}]ass=filename='{safe_path(path)}'{fonts}[a{k}]")
        cur = f"a{k}"
        ass_styles.clear()
        ass_events.clear()

    for layer in sorted(doc.layers, key=lambda x: x.z):  # sorted es estable: a igual z, orden de creación
        if not layer.visible:
            continue
        start, end = layer.start, min(layer.end, full_doc.duration)
        if start >= end:
            continue
        if window and (end <= t_off or start >= t_off + duration):
            continue  # fuera de la ventana: ni se compone ni se rasteriza
        orig_layer = layer
        layer = layer.model_copy(update={"end": end})
        if isinstance(layer, SceneLayer):
            flush_ass()
            idx = extra_inputs + counters["ov"]
            counters["ov"] += 1
            try:  # la plantilla se ajusta a la duración COMPLETA de la capa, aunque el vídeo la recorte
                seq = render_scene_sequence(orig_layer, W, H, fps, opts.workdir / f"seq{idx}", warnings,
                                            window=(t_off, t_off + duration) if window else None)  # fmt: skip
            except TemplateError as e:
                warnings.append(f"Escena '{layer.id}' ignorada: {e}")
                seq = None
            if seq is None:
                counters["ov"] -= 1
                continue
            inputs += ["-framerate", str(fps), "-start_number", "0", "-i", safe_pattern(seq.pattern)]
            cur = _overlay_sequence(g, cur, idx, seq, start + seq.t0, end)
            continue
        if isinstance(layer, SubtitleLayer):
            st, ev = A.subtitle_events(layer, mapped_words, W, H)
            if not ev and not window:
                warnings.append(f"La layer '{layer.id}' no generó subtítulos (¿sin transcripción en este tramo?)")
        elif isinstance(layer, TextLayer):
            st, ev = A.text_events(layer, W, H, warnings)
        elif isinstance(layer, ShapeLayer):
            st, ev = A.shape_events(layer, W, H, warnings)
        elif isinstance(layer, IconLayer | ImageLayer):
            flush_ass()
            png = rasterize(layer.asset, even(layer.box.w * W), getattr(layer, "tint", None), opts.workdir / "raster")
            idx = extra_inputs + counters["ov"]
            counters["ov"] += 1
            if is_animated(layer):
                seq = render_sequence(png, layer, W, H, fps, opts.workdir / f"seq{idx}", warnings)
                if seq is None:
                    counters["ov"] -= 1
                    continue
                inputs += ["-framerate", str(fps), "-start_number", "0", "-i", safe_pattern(seq.pattern)]
                cur = _overlay_sequence(g, cur, idx, seq, start, end)
            else:
                inputs += ["-loop", "1", "-framerate", str(fps), "-t", f(end - start), "-i", safe_path(png)]
                cur = _overlay_static(g, cur, idx, layer, W, H, start, end)
            continue
        elif isinstance(layer, EffectLayer):
            flush_ass()
            try:
                defn = fx_registry.get(layer.effect)
                rx = ry = 0
                rw, rh = W, H
                if layer.region:
                    rx, ry = (
                        even(layer.region.x * W) if layer.region.x else 0,
                        even(layer.region.y * H) if layer.region.y else 0,
                    )
                    rw, rh = min(even(layer.region.w * W), W - rx), min(even(layer.region.h * H), H - ry)
                filters = fx_registry.build_filters(defn, layer.params, EffectCtx(start, end, rw, rh, fps))
            except (fx_registry.EffectParamError, EffectBuildError) as e:
                warnings.append(f"Efecto '{layer.effect}' ignorado: {e}")
                continue
            k = counters["fx"] = counters.get("fx", 0) + 1
            chain = ",".join(filters)
            if layer.region:  # el efecto actúa solo sobre la región y se recompone encima
                g.append(f"[{cur}]split=2[fb{k}][fr{k}]")
                g.append(f"[fr{k}]crop={rw}:{rh}:{rx}:{ry},{chain}[fx{k}]")
                g.append(f"[fb{k}][fx{k}]overlay=x={rx}:y={ry}[e{k}]")
            else:
                g.append(f"[{cur}]{chain}[e{k}]")
            cur = f"e{k}"
            continue
        else:  # pragma: no cover
            continue
        ass_styles += st
        ass_events += ev
    flush_ass()
    g.append(f"[{cur}]format=yuv420p[vout]")

    # 4) audio: ganancia del usuario + normalización estática medida (norm_gain_db) + limitador de picos
    au = doc.audio
    chain = user_audio_chain(doc)
    if au.normalize and norm_gain_db is not None:
        # El techo del limitador va 1,5 dB por debajo del objetivo: AAC y los picos entre muestras lo desbordan (medido +0,6 dBFS).
        chain += [f"volume={f(norm_gain_db)}dB", f"alimiter=limit={f(10 ** ((au.true_peak - 1.5) / 20))}:level=0"]
    if opts.with_audio:
        g.append(f"[ac]{','.join(chain) if chain else 'anull'}[aout]")
    return RenderPlan(inputs, ";\n".join(g), W, H, duration, fps, warnings)


def _overlay_sequence(g: list[str], cur: str, idx: int, seq, start: float, end: float) -> str:
    """Capa animada: secuencia de PNG ya compuesta (posición, escala, rotación y opacidad incluidas)."""
    g.append(f"[{idx}:v]format=rgba,setpts=PTS+{f(start)}/TB[ov{idx}]")
    out = f"o{idx}"
    g.append(
        f"[{cur}][ov{idx}]overlay=x={seq.x}:y={seq.y}:enable='between(t,{f(start)},{f(end)})':eof_action=pass:format=auto[{out}]"
    )
    return out


def _overlay_static(
    g: list[str], cur: str, idx: int, layer: IconLayer | ImageLayer, W: int, H: int, start: float, end: float
) -> str:
    """Capa estática: una sola imagen en bucle; es lo más barato."""
    box = layer.box
    chain = ["format=rgba", f"scale={even(box.w * W)}:{even(box.h * H) if box.h else -2}"]
    if box.rotation:
        rad = f(box.rotation * 3.14159265 / 180)
        chain.append(f"rotate={rad}:ow='rotw({rad})':oh='roth({rad})':c=none")
    if layer.opacity < 1:
        chain.append(f"colorchannelmixer=aa={f(layer.opacity)}")
    chain.append(f"setpts=PTS+{f(start)}/TB")
    g.append(f"[{idx}:v]{','.join(chain)}[ov{idx}]")
    h_part = "left" if box.anchor.endswith("left") else "right" if box.anchor.endswith("right") else "center"
    v_part = box.anchor.split("_")[0] if "_" in box.anchor else "center"
    fy = {"top": 0.0, "center": 0.5, "bottom": 1.0}[v_part]
    x = f"{f(box.x)}*main_w-overlay_w*{f(_FACTOR[h_part])}"
    y = f"{f(box.y)}*main_h-overlay_h*{f(fy)}"
    out = f"o{idx}"
    g.append(
        f"[{cur}][ov{idx}]overlay=x='{x}':y='{y}':enable='between(t,{f(start)},{f(end)})':eof_action=pass:format=auto[{out}]"
    )
    return out


def ffmpeg_command(
    plan: RenderPlan, graph_file: Path, out_path: Path, opts: RenderOpts, frame_only: bool = False
) -> list[str]:
    """Comando de render. `frame_only` saca un único fotograma JPEG (sin audio) del primer instante de la ventana."""
    lean = ["-threads", "2", "-filter_threads", "1", "-filter_complex_threads", "1"]
    head = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-y",
        *lean,
        *plan.inputs,
        "-filter_complex_script",
        safe_path(graph_file),
    ]
    if frame_only:
        return [*head, "-map", "[vout]", "-frames:v", "1", "-q:v", "3", safe_path(out_path)]
    if opts.encoder == "h264_nvenc":
        venc = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "32" if opts.light else "21", "-b:v", "0"]
    else:
        # Memoria acotada (VPS pequeño y compartido): pocos hilos y poco lookahead (pico ~1,1 GB → cientos de MB).
        venc = ["-c:v", "libx264", "-preset", "ultrafast" if opts.light else "veryfast", "-crf", "30" if opts.light else "20",
                "-x264-params", "rc-lookahead=8:sync-lookahead=0:lookahead-threads=1:ref=2:bframes=2:threads=2"]  # fmt: skip
    audio = (
        ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k" if opts.light else "192k", "-ar", "48000"]
        if opts.with_audio
        else ["-an"]
    )
    return [*head, "-map", "[vout]", *audio, *venc, "-pix_fmt", "yuv420p", "-r", str(plan.fps),
            "-t", f(plan.duration), "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", safe_path(out_path)]  # fmt: skip
