"""Filtro de alucinaciones típicas de Whisper en silencio/música y edición de texto."""

import re

from cutly.services.transcribe.types import Segment, Word

HALLUCINATIONS = (
    "subtítulos por la comunidad de amara.org",
    "subtitulado por la comunidad de amara.org",
    "gracias por ver el vídeo",
    "suscríbete al canal",
)


def is_hallucination(text: str, no_speech_prob: float, avg_logprob: float) -> bool:
    t = re.sub(r"\s+", " ", text.strip().lower())
    if not t:
        return True
    if any(h in t for h in HALLUCINATIONS) and no_speech_prob > 0.3:
        return True
    return no_speech_prob > 0.6 and avg_logprob < -1.0


def apply_text_edit(seg: dict, text: str) -> dict:
    """Reemplaza el texto de un segmento conservando los tiempos de palabra.

    Mismo nº de palabras → se sustituye cada una (tiempos intactos).
    Distinto nº → se reparten las palabras nuevas por todo el segmento, proporcional a su longitud.
    """
    tokens = text.split()
    if not tokens:
        raise ValueError("El texto del segmento no puede quedar vacío")
    old = seg["words"]
    if len(tokens) == len(old):
        words = [{**w, "w": t} for w, t in zip(old, tokens, strict=True)]
    else:
        start, end = seg["start"], seg["end"]
        total = sum(len(t) + 1 for t in tokens)
        cur, words = start, []
        for t in tokens:
            nxt = cur + (end - start) * (len(t) + 1) / total
            words.append(Word(w=t, start=round(cur, 3), end=round(nxt, 3), p=None).model_dump())
            cur = nxt
    return {**seg, "text": " ".join(tokens), "words": words}


def renumber(segments: list[Segment]) -> list[Segment]:
    for i, s in enumerate(segments):
        s.id = i
    return segments


def apply_word_edits(seg: dict, edits: list[dict]) -> dict:
    """Correcciones a nivel de palabra conservando los tiempos de las demás.

    replace: cambia el texto de la palabra `index`. merge: une las palabras `index..to` en una sola (hereda el
    inicio de la primera y el fin de la última). delete: quita la palabra. Los índices son los del segmento
    ANTES de aplicar nada; se aplican de mayor a menor para que no se desplacen entre sí.
    """
    words = [dict(w) for w in seg["words"]]
    n = len(words)
    for e in sorted(edits, key=lambda e: -e["index"]):
        i, op = e["index"], e["op"]
        if not 0 <= i < n:
            raise ValueError(f"Índice de palabra {i} fuera de rango (0–{n - 1})")
        if op == "delete":
            del words[i]
        elif op == "replace":
            words[i]["w"] = e["text"].strip()
        elif op == "merge":
            j = e.get("to", i + 1)
            if not i < j < n:
                raise ValueError(f"merge necesita index < to <= {n - 1}")
            merged = {"w": e["text"].strip(), "start": words[i]["start"], "end": words[j]["end"],
                      "p": min((w.get("p") or 1.0) for w in words[i : j + 1])}  # fmt: skip
            words[i : j + 1] = [merged]
        if op != "delete" and not words[i]["w"]:
            raise ValueError("El texto de una palabra no puede quedar vacío")
    if not words:
        raise ValueError("No se pueden borrar todas las palabras del segmento; bórralo entero")
    return {
        **seg,
        "words": words,
        "text": " ".join(w["w"] for w in words),
        "start": words[0]["start"],
        "end": words[-1]["end"],
    }
