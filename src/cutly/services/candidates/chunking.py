"""Troceado del transcript en bloques con solape, alineados a segmentos."""


def make_chunks(segments: list[dict], size_s: float, overlap_s: float) -> list[list[dict]]:
    """Bloques de ~`size_s` con `overlap_s` de solape. Un momento cortado al final de un bloque
    aparece completo en el siguiente."""
    if not segments:
        return []
    total = segments[-1]["end"]
    if total <= size_s * 1.2:
        return [segments]
    chunks, start = [], 0.0
    while start < total:
        end = start + size_s
        part = [s for s in segments if s["end"] > start and s["start"] < end]
        if part:
            chunks.append(part)
        if end >= total:
            break
        start = end - overlap_s
    return chunks


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}"


def render_chunk(chunk: list[dict]) -> str:
    """Una línea por segmento: `[id @ h:mm:ss] texto`."""
    return "\n".join(f"[{s['id']} @ {fmt_ts(s['start'])}] {s['text']}" for s in chunk)
