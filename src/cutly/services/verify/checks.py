"""Comprobaciones automáticas de calidad de un proyecto. Pensadas para un agente que no ve el vídeo: cada problema
trae código, tiempo, capa afectada y una sugerencia concreta con los valores a usar."""

from collections.abc import Callable
from dataclasses import asdict, dataclass

from cutly.schema.project import (
    EffectLayer,
    IconLayer,
    ImageLayer,
    ProjectDoc,
    SubtitleLayer,
    TextLayer,
    timeline_starts,
)
from cutly.services.candidates.snapping import snap_to_sentences
from cutly.services.projects.check import check_project
from cutly.services.verify.geometry import (
    Frame,
    Rect4,
    layer_rect,
    overlap_ratio,
    source_rect_to_output,
    text_metrics,
)

_END = (".", "!", "?", "…")
# zonas que la interfaz de Reels/TikTok/Shorts suele tapar: franja inferior y botones laterales
UI_BOTTOM, UI_RIGHT_X = 0.82, 0.88


@dataclass
class Issue:
    severity: str  # error | warning | info
    code: str
    message: str
    t: float | None = None
    layer_id: str | None = None
    suggestion: str | None = None

    def dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _word_end_sentence(w: str) -> bool:
    return w.rstrip("\"'»”)").endswith(_END)


def output_to_source(doc: ProjectDoc, t: float) -> float | None:
    for s, c in zip(timeline_starts(doc.timeline), doc.timeline, strict=True):
        if s <= t < s + c.duration:
            return c.source_in + (t - s) * c.speed
    return None


def _label(layer) -> str:
    return f"'{layer.name or layer.id}' ({layer.type})"


def check_layers(doc: ProjectDoc, W: int, H: int) -> list[Issue]:
    out: list[Issue] = []
    dur = doc.duration
    visible = [layer for layer in doc.layers if layer.visible]
    for layer in visible:
        rect = layer_rect(layer, W, H)
        if rect is None:
            continue
        lbl = _label(layer)
        if rect[0] < -0.01 or rect[1] < -0.01 or rect[2] > 1.01 or rect[3] > 1.01:
            out.append(Issue("warning", "off_screen", f"La capa {lbl} se sale del fotograma (x {rect[0]:.2f}–{rect[2]:.2f}, y {rect[1]:.2f}–{rect[3]:.2f}).", layer.start, layer.id,
                             "Acércala al centro con update_layer sobre `box` o reduce `box.w`/`style.size`."))  # fmt: skip
        if isinstance(layer, TextLayer | SubtitleLayer):
            size = layer.style.size
            if size * H < (56 if isinstance(layer, SubtitleLayer) else 36) * (H / 1920):
                out.append(
                    Issue(
                        "warning",
                        "text_small",
                        f"El texto de {lbl} es muy pequeño ({size * 1920:.0f} px a 1920): difícil de leer en móvil.",
                        layer.start,
                        layer.id,
                        "Sube `style.size`.",
                    )
                )
            if isinstance(layer, TextLayer):
                _, _, lines = text_metrics(
                    layer.text, layer.style.font, size, layer.style.uppercase, layer.box.w, W, H, layer.style.bold
                )
                if lines > 4:
                    out.append(
                        Issue(
                            "warning",
                            "text_long",
                            f"El texto de {lbl} ocupa unas {lines} líneas: demasiado para un rótulo.",
                            layer.start,
                            layer.id,
                            "Acórtalo o ensancha `box.w`.",
                        )
                    )
            if rect[3] > UI_BOTTOM and rect[1] < 1.0:
                out.append(
                    Issue(
                        "warning",
                        "platform_ui_zone",
                        f"{lbl} cae en la franja inferior que tapan los controles de la app (y > {UI_BOTTOM}).",
                        layer.start,
                        layer.id,
                        f"Súbela por encima de y={UI_BOTTOM - 0.03:.2f}.",
                    )
                )
            elif rect[2] > UI_RIGHT_X and 0.45 < (rect[1] + rect[3]) / 2 < 0.85:
                out.append(
                    Issue(
                        "info",
                        "platform_ui_zone",
                        f"{lbl} queda junto al borde derecho donde van los botones de la app.",
                        layer.start,
                        layer.id,
                        "Muévela a la izquierda.",
                    )
                )
        if layer.end > dur + 0.05 or layer.start >= dur:
            out.append(
                Issue(
                    "warning",
                    "layer_timing",
                    f"{lbl} no cabe en el clip (dura {dur:.1f} s; la capa va de {layer.start:.1f} a {layer.end:.1f}).",
                    layer.start,
                    layer.id,
                    "Ajusta start/end.",
                )
            )
    # solapes entre capas visibles de contenido (no formas ni efectos)
    content = [
        (layer, layer_rect(layer, W, H))
        for layer in visible
        if isinstance(layer, TextLayer | IconLayer | ImageLayer | SubtitleLayer)
    ]
    seen: set[tuple[str, str]] = set()
    for i, (a, ra) in enumerate(content):
        for b, rb in content[i + 1 :]:
            if ra is None or rb is None:
                continue
            t0, t1 = max(a.start, b.start), min(a.end, b.end, dur)
            if t1 - t0 < 0.3 or overlap_ratio(ra, rb) < 0.2 or (a.id, b.id) in seen:
                continue
            seen.add((a.id, b.id))
            out.append(
                Issue(
                    "warning",
                    "layers_overlap",
                    f"{_label(a)} y {_label(b)} se pisan entre {t0:.1f} y {t1:.1f} s.",
                    t0,
                    a.id,
                    "Cambia la posición de una, o desplaza sus tiempos para que no coincidan.",
                )
            )
    n_fx = sum(
        1
        for layer in visible
        if isinstance(layer, EffectLayer) and layer.effect in ("zoom_punch", "shake", "flash", "glitch")
    )
    if dur > 8 and n_fx / dur * 60 > 14:
        out.append(
            Issue(
                "info",
                "too_many_effects",
                f"{n_fx} efectos de impacto en {dur:.0f} s ({n_fx / dur * 60:.0f}/min): puede resultar cansado.",
                None,
                None,
                "Deja solo los que acompañen una idea clave.",
            )
        )
    if not any(isinstance(layer, SubtitleLayer) for layer in visible):
        out.append(
            Issue(
                "info",
                "no_subtitles",
                "El clip no tiene subtítulos.",
                None,
                None,
                "Añade una capa `subtitle` (la mayoría de reels se ven sin sonido).",
            )
        )
    return out


def check_cuts(doc: ProjectDoc, words: list[dict]) -> list[Issue]:
    """Cortes de la línea de tiempo respecto a las palabras habladas."""
    if not words:
        return []
    out: list[Issue] = []
    flat = sorted(words, key=lambda w: w["start"])
    for c in doc.timeline:
        for kind, t in (("start", c.source_in), ("end", c.source_out)):
            inside = next((w for w in flat if w["start"] + 0.03 < t < w["end"] - 0.03), None)
            snapped = snap_to_sentences(flat, c.source_in, c.source_out)
            hint = (
                f"Prueba set_clip_range clip_id={c.id} source_in={snapped[0]:.2f} source_out={snapped[1]:.2f}."
                if snapped
                else None
            )
            if inside:
                out.append(
                    Issue(
                        "error",
                        "cut_mid_word",
                        f"El corte de {'inicio' if kind == 'start' else 'final'} del clip {c.id} ({t:.2f} s) parte la palabra «{inside['w']}».",
                        t,
                        None,
                        hint,
                    )
                )
                continue
            before = [w for w in flat if w["end"] <= t + 0.03]
            after = [w for w in flat if w["start"] >= t - 0.03]
            if kind == "start":
                prev = before[-1] if before else None
                if prev and t - prev["end"] < 0.35 and not _word_end_sentence(prev["w"]):
                    out.append(
                        Issue(
                            "warning",
                            "cut_starts_mid_sentence",
                            f"El clip {c.id} empieza a mitad de frase (tras «{prev['w']}»).",
                            t,
                            None,
                            hint,
                        )
                    )
                nxt = after[0] if after else None
                if nxt and 0 <= nxt["start"] - t < 0.05:
                    out.append(
                        Issue(
                            "info",
                            "tight_cut",
                            f"El clip {c.id} empieza justo al comenzar una palabra: puede comerse el ataque.",
                            t,
                            None,
                            "Deja ~0.15 s de margen antes.",
                        )
                    )
            else:
                last = before[-1] if before else None
                nxt = after[0] if after else None
                if last and nxt and nxt["start"] - t < 0.35 and not _word_end_sentence(last["w"]):
                    out.append(
                        Issue(
                            "warning",
                            "cut_ends_mid_sentence",
                            f"El clip {c.id} termina a mitad de frase (antes de «{nxt['w']}»).",
                            t,
                            None,
                            hint,
                        )
                    )
    return out


def check_audio(doc: ProjectDoc, stats: dict | None) -> list[Issue]:
    if not stats or not stats.get("has_audio", True):
        return [] if stats is None else [Issue("warning", "no_audio", "El vídeo original no tiene pista de audio.")]
    out: list[Issue] = []
    lufs, peak = stats.get("integrated_lufs"), stats.get("true_peak_db")
    if lufs is None:
        return out
    if doc.audio.normalize:
        out.append(
            Issue(
                "info",
                "loudness",
                f"Volumen medido antes de normalizar: {lufs:.1f} LUFS (objetivo {doc.audio.target_lufs:g}); se aplicará {doc.audio.target_lufs - lufs:+.1f} dB.",
            )
        )
        if lufs < -45:
            out.append(
                Issue(
                    "warning",
                    "audio_very_quiet",
                    f"El audio es muy bajo ({lufs:.1f} LUFS): normalizarlo subirá también el ruido.",
                    None,
                    None,
                    "Activa `denoise` o revisa la fuente.",
                )
            )
    else:
        if abs(lufs - doc.audio.target_lufs) > 3:
            out.append(
                Issue(
                    "warning",
                    "loudness_off",
                    f"Volumen {lufs:.1f} LUFS, lejos del objetivo {doc.audio.target_lufs:g}.",
                    None,
                    None,
                    "Activa `normalize` con set_audio.",
                )
            )
        if peak is not None and peak > doc.audio.true_peak + 0.2:
            out.append(
                Issue(
                    "warning",
                    "peak_over",
                    f"Pico de {peak:.1f} dBFS por encima de {doc.audio.true_peak:g}: riesgo de saturación.",
                    None,
                    None,
                    "Baja `gain_db` o activa `normalize`.",
                )
            )
    dur = stats.get("duration", doc.duration)
    for s in stats.get("silences", []):
        if s["start"] < 0.05 and s["duration"] >= 0.6:
            out.append(
                Issue(
                    "info",
                    "dead_air_start",
                    f"Silencio de {s['duration']:.1f} s al principio.",
                    0.0,
                    None,
                    f"Recorta el inicio con set_clip_range (+{s['end'] - 0.15:.2f} s).",
                )
            )
        elif s["end"] >= dur - 0.05 and s["duration"] >= 0.6:
            out.append(
                Issue(
                    "info",
                    "dead_air_end",
                    f"Silencio de {s['duration']:.1f} s al final.",
                    s["start"],
                    None,
                    "Recorta el final del último clip.",
                )
            )
        elif s["duration"] >= 1.5:
            out.append(
                Issue(
                    "warning",
                    "long_silence",
                    f"Silencio de {s['duration']:.1f} s ({s['start']:.1f}–{s['end']:.1f} s): resta ritmo.",
                    s["start"],
                    None,
                    "Corta ese tramo con split_clip + delete_clip.",
                )
            )
    return out


def check_faces(
    doc: ProjectDoc, media: dict, faces_at: Callable[[float], list[Rect4]] | None, samples: int = 8
) -> list[Issue]:
    """Capas de contenido que tapan una cara en algún instante (caras vistas en el original y llevadas al reencuadre)."""
    if faces_at is None or not doc.timeline:
        return []
    W, H = doc.output.width, doc.output.height
    fr = Frame(media["width"], media["height"], W, H)
    dur = doc.duration
    times = sorted({round(dur * (k + 0.5) / samples, 2) for k in range(samples)} | {round(layer.start + 0.4, 2) for layer in doc.layers
                    if isinstance(layer, TextLayer | IconLayer | ImageLayer) and layer.start + 0.4 < dur})  # fmt: skip
    times = times[:16]
    hits: dict[str, tuple[float, float, int]] = {}
    any_face = False
    for t in times:
        st = output_to_source(doc, t)
        if st is None:
            continue
        faces: list[Rect4] = []
        for f in faces_at(st):
            faces += source_rect_to_output(f, doc.reframe, fr)
        any_face = any_face or bool(faces)
        for layer in doc.layers:
            if (
                not layer.visible
                or not isinstance(layer, TextLayer | IconLayer | ImageLayer | SubtitleLayer)
                or not (layer.start <= t < layer.end)
            ):
                continue
            rect = layer_rect(layer, W, H)
            if rect is None:
                continue
            worst = max((_covered(rect, f) for f in faces), default=0.0)
            if worst > 0.12:
                prev = hits.get(layer.id)
                hits[layer.id] = (
                    prev[0] if prev else t,
                    max(worst, prev[1] if prev else 0),
                    (prev[2] if prev else 0) + 1,
                )
    out = [
        Issue("error" if worst > 0.3 else "warning", "covers_face", f"{_label(next(x for x in doc.layers if x.id == lid))} tapa la cara ({worst:.0%} de la cara) desde {t:.1f} s (visto en {n} muestra{'s' if n > 1 else ''}).",
              t, lid, "Muévela fuera de la zona de la cara (mira el fotograma con GET /projects/{id}/frame) o redúcela.")
        for lid, (t, worst, n) in hits.items()
    ]  # fmt: skip
    if not any_face:
        out.append(
            Issue(
                "info",
                "no_face_detected",
                "No se detectó ninguna cara en las muestras (o no hay OpenCV): no se pudo comprobar si algo la tapa.",
            )
        )
    return out


def _covered(rect: Rect4, face: Rect4) -> float:
    """Fracción de la cara cubierta por el rectángulo."""
    w = min(rect[2], face[2]) - max(rect[0], face[0])
    h = min(rect[3], face[3]) - max(rect[1], face[1])
    fa = (face[2] - face[0]) * (face[3] - face[1])
    return max(w, 0) * max(h, 0) / fa if fa > 0 else 0.0


def run_checks(
    doc: ProjectDoc,
    media: dict,
    words: list[dict],
    faces_at: Callable[[float], list[Rect4]] | None = None,
    audio: dict | None = None,
    has_transcript: bool = True,
) -> dict:
    issues: list[Issue] = []
    if not doc.timeline:
        issues.append(
            Issue(
                "error", "empty_timeline", "La línea de tiempo está vacía.", None, None, "Añade un clip con add_clip."
            )
        )
    else:
        issues += check_layers(doc, doc.output.width, doc.output.height)
        issues += check_cuts(doc, words)
        issues += check_audio(doc, audio)
        issues += check_faces(doc, media, faces_at)
        d = doc.duration
        if d < 8:
            issues.append(Issue("info", "very_short", f"El clip dura solo {d:.1f} s."))
        elif d > 180:
            issues.append(
                Issue(
                    "info",
                    "long",
                    f"El clip dura {d / 60:.1f} min: los reels suelen funcionar mejor por debajo de 90 s.",
                )
            )
        if not has_transcript and any(isinstance(layer, SubtitleLayer) for layer in doc.layers):
            issues.append(
                Issue(
                    "warning",
                    "subtitles_without_transcript",
                    "Hay subtítulos pero el vídeo no tiene transcripción.",
                    None,
                    None,
                    "Lanza POST /media/{id}/transcribe.",
                )
            )
        known = {i.message for i in issues}
        issues += [Issue("warning", "project_warning", w) for w in check_project(doc, has_transcript) if w not in known]
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i.severity], i.t if i.t is not None else -1))
    counts = {s: sum(1 for i in issues if i.severity == s) for s in order}
    return {"ok": counts["error"] == 0, "counts": counts, "issues": [i.dict() for i in issues]}
