"""Avisos no bloqueantes sobre un proyecto (lo bloqueante lo valida el esquema)."""

from cutly.schema.project import ProjectDoc, SubtitleLayer


def check_project(doc: ProjectDoc, has_transcript: bool) -> list[str]:
    w: list[str] = []
    dur = doc.duration
    if not doc.timeline:
        w.append("La línea de tiempo está vacía: añade un clip (add_clip) antes de renderizar")
    for layer in doc.layers:
        label = f"layer '{layer.id}' ({layer.type})"
        if layer.start >= dur > 0:
            w.append(f"La {label} empieza en {layer.start:g} s, pero el clip dura {dur:g} s: no se verá")
        elif layer.end > dur + 0.01 and dur > 0:
            w.append(f"La {label} termina en {layer.end:g} s pero el clip dura {dur:g} s: se recortará")
        if isinstance(layer, SubtitleLayer) and layer.source == "transcript" and not has_transcript:
            w.append(f"La {label} usa la transcripción, pero el vídeo no tiene: lanza POST /media/{{id}}/transcribe")
    return w
