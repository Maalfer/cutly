"""Ajuste de inicio/fin a límites de frase usando los tiempos por palabra, y deduplicado."""

import re

from cutly.services.candidates.types import Candidate

_END = re.compile(r"[.!?…]+[\"'»”)\]]*$")


def _is_end(word: str) -> bool:
    return bool(_END.search(word))


def flatten_words(segments: list[dict]) -> list[dict]:
    return [w for s in segments for w in s["words"]]


def snap_to_sentences(words: list[dict], start: float, end: float, tol: float = 8.0) -> tuple[float, float] | None:
    """Mueve `start` al inicio de frase más cercano y `end` al final de frase más cercano
    (dentro de ±`tol` s). Añade un pequeño margen sin invadir las palabras vecinas."""
    if not words:
        return None
    # candidatos a inicio: palabras que abren frase (la primera o la que sigue a un final de frase)
    starts = [i for i, w in enumerate(words) if i == 0 or _is_end(words[i - 1]["w"])]
    ends = [i for i, w in enumerate(words) if _is_end(w["w"]) or i == len(words) - 1]
    si = [i for i in starts if abs(words[i]["start"] - start) <= tol]
    ei = [i for i in ends if abs(words[i]["end"] - end) <= tol]
    if si:
        i = min(si, key=lambda i: (abs(words[i]["start"] - start), words[i]["start"] > start))
    else:
        i = min(range(len(words)), key=lambda i: abs(words[i]["start"] - start))
    if ei:
        k = min(ei, key=lambda k: (abs(words[k]["end"] - end), words[k]["end"] < end))
    else:
        k = min(range(len(words)), key=lambda k: abs(words[k]["end"] - end))
    if k < i:
        return None
    s = words[i]["start"] - 0.25
    if i > 0:
        s = max(s, words[i - 1]["end"])
    e = words[k]["end"] + 0.35
    if k + 1 < len(words):
        e = min(e, words[k + 1]["start"])
    return round(max(s, 0.0), 3), round(e, 3)


def overlap(a: Candidate, b: Candidate) -> tuple[float, float]:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    union = (a.end - a.start) + (b.end - b.start) - inter
    return (inter / union if union else 0.0), inter / max(min(a.end - a.start, b.end - b.start), 1e-6)


def dedupe(cands: list[Candidate], iou_max: float = 0.3, contain_max: float = 0.6) -> list[Candidate]:
    """Se queda con la mejor puntuación cuando dos candidatos (de bloques solapados) cuentan lo mismo."""
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda c: -c.score):
        if all(overlap(c, k)[0] < iou_max and overlap(c, k)[1] < contain_max for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: c.start)
