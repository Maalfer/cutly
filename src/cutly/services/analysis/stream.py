"""Análisis de directos largos: esquema por ventanas, cambios de tema y tramos de 5-10 min con más interés.

Sin modelos ni red: señales baratas y explicables calculadas con la transcripción por palabras y los picos de audio.
Sirve para que un agente navegue 100 minutos sin leerlos enteros (esquema) y para proponerle tramos que merece la pena
revisar (propuestas). La decisión final y el título los pone el agente leyendo el texto.

Limitaciones: no distingue hablantes (no hay diarización) ni detecta risas; el «interés» es una heurística (energía de la
voz, ritmo de habla, intercambios rápidos, preguntas y exclamaciones), no una comprensión del contenido.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

STOP = set(
    "a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque bien cada casi como con contra cosa cosas cual cuando "
    "de del desde donde dos el ella ellas ello ellos en entre era eran eres es esa esas ese eso esos esta estaba estaban estamos estan estar "
    "este esto estos estoy fue fueron ha haber habia han hasta hay he hemos hace hacer hacia lo la las le les lo los mas me mi mis mucho muchos "
    "muy nada ni no nos nosotros o os otra otras otro otros para pero poco por porque pues que quien se ser si sin sobre solo son soy su sus "
    "tambien tan tanto te tengo tiene tienen todo todos tu tus un una unas uno unos vamos va van vas voy vale vez ver ya yo eh em pues vale bueno "
    "entonces osea digo dice dicen mira mirad oye venga igual tipo algo aqui alli ahi ahora luego ".split()
)  # fmt: skip
_TOK = re.compile(r"[a-zñ0-9]+")


def _norm(w: str) -> str:
    d = unicodedata.normalize("NFD", w.lower())
    return "".join(c for c in d if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    return [t for t in _TOK.findall(_norm(text)) if len(t) >= 4 and t not in STOP and not t.isdigit()]


def fmt_t(s: float) -> str:
    s = int(round(s))
    h, m = divmod(s // 60, 60)
    return f"{h}:{m:02d}:{s % 60:02d}" if h else f"{m}:{s % 60:02d}"


@dataclass
class Window:
    i: int
    start: float
    end: float
    n_words: int = 0
    wpm: float = 0.0
    speech: float = 0.0  # fracción del tiempo con voz (palabras)
    energy: float = 0.0  # amplitud media (0-1) o 0 si no hay picos
    peak: float = 0.0  # percentil 95 de la amplitud
    turns: float = 0.0  # segmentos de transcripción por minuto (≈ intercambios rápidos)
    questions: int = 0
    exclaims: int = 0
    text: str = ""
    counts: Counter = field(default_factory=Counter)
    interest: float = 0.0
    boundary: float = 0.0  # 0-1: cuánto cambia el tema respecto a la ventana anterior


def _robust_z(x: np.ndarray) -> np.ndarray:
    if len(x) < 3:
        return np.zeros_like(x, dtype=float)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * 1.4826
    sd = mad if mad > 1e-9 else float(np.std(x))
    return (x - med) / sd if sd > 1e-9 else np.zeros_like(x, dtype=float)


def build_windows(segments: list[dict], duration: float, window: float, peaks: np.ndarray | None = None) -> list[Window]:
    """Parte el directo en ventanas de `window` s y calcula las señales de cada una."""
    n = max(1, int(np.ceil(duration / window)))
    wins = [Window(i, i * window, min(duration, (i + 1) * window)) for i in range(n)]
    amp = None
    if peaks is not None and len(peaks) and duration > 0:
        a = np.asarray(peaks, dtype=np.int16)
        amp = (a.max(axis=1) - a.min(axis=1)).astype(float) / 255.0 if a.ndim == 2 else np.abs(a).astype(float) / 127.0
    spb = duration / len(amp) if amp is not None else 0.0  # segundos por muestra de picos
    texts: list[list[str]] = [[] for _ in wins]
    for seg in segments:
        idx = min(n - 1, max(0, int(seg["start"] // window)))
        wins[idx].turns += 1
        texts[idx].append(seg["text"].strip())
        for w in seg.get("words", []):
            k = min(n - 1, max(0, int(w["start"] // window)))
            wins[k].n_words += 1
            wins[k].speech += max(0.0, w["end"] - w["start"])
            wins[k].counts.update(tokens(w["w"]))
    for k, win in enumerate(wins):
        span = max(win.end - win.start, 1e-6)
        win.wpm = win.n_words / span * 60
        win.speech = min(1.0, win.speech / span)
        win.turns = win.turns / span * 60
        win.text = " ".join(texts[k])
        win.questions = win.text.count("?") + win.text.count("¿") // 2
        win.exclaims = win.text.count("!")
        if amp is not None and spb:
            a0, a1 = int(win.start / spb), max(int(win.end / spb), int(win.start / spb) + 1)
            seg_amp = amp[a0:a1]
            if len(seg_amp):
                win.energy, win.peak = float(seg_amp.mean()), float(np.percentile(seg_amp, 95))
    _interest(wins)
    _boundaries(wins)
    return wins


def _interest(wins: list[Window]) -> None:
    f = lambda attr: np.array([getattr(w, attr) for w in wins], dtype=float)  # noqa: E731
    qrate = np.array([(w.questions + w.exclaims) / max((w.end - w.start) / 60, 1e-6) for w in wins])
    has_audio = any(w.energy > 0 for w in wins)
    z = (
        (0.30 * _robust_z(f("energy")) + 0.20 * _robust_z(f("peak")) if has_audio else 0)
        + 0.20 * _robust_z(f("wpm")) + 0.15 * _robust_z(f("turns")) + 0.15 * _robust_z(qrate)
    )  # fmt: skip
    if not has_audio:
        z = z / 0.5  # sin audio, los pesos restantes suman 0,5
    for w, v in zip(wins, z, strict=True):
        w.interest = float(np.clip(v, -3, 4))
        if w.speech < 0.30:  # aire muerto: nunca interesante
            w.interest = min(w.interest, -1.0)


def _boundaries(wins: list[Window], block: int = 2) -> None:
    """Cambio de tema entre ventanas: 1 - coseno entre el vocabulario de las `block` anteriores y las `block` siguientes
    (ponderado por TF-IDF)."""
    df: Counter = Counter()
    for w in wins:
        df.update(w.counts.keys())
    N = max(len(wins), 1)
    idf = {t: np.log((1 + N) / (1 + c)) + 1 for t, c in df.items()}

    def vec(group: list[Window]) -> dict[str, float]:
        c: Counter = Counter()
        for w in group:
            c.update(w.counts)
        return {t: v * idf[t] for t, v in c.items()}

    def cos(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.5
        num = sum(v * b.get(t, 0.0) for t, v in a.items())
        den = np.sqrt(sum(v * v for v in a.values())) * np.sqrt(sum(v * v for v in b.values()))
        return float(num / den) if den else 0.5

    raw = [0.0] * len(wins)
    for i in range(1, len(wins)):
        raw[i] = 1 - cos(vec(wins[max(0, i - block):i]), vec(wins[i:i + block]))
    arr = np.array(raw)
    if len(arr) > 2 and arr.max() > arr.min():
        arr = (arr - np.percentile(arr, 10)) / max(np.percentile(arr, 95) - np.percentile(arr, 10), 1e-9)
    for w, v in zip(wins, arr, strict=True):
        w.boundary = float(np.clip(v, 0, 1))


def keywords(counts: Counter, wins: list[Window], top: int = 5) -> list[str]:
    """Términos más característicos (TF-IDF contra el resto del directo)."""
    df: Counter = Counter()
    for w in wins:
        df.update(w.counts.keys())
    N = max(len(wins), 1)
    scored = {t: c * (np.log((1 + N) / (1 + df[t])) + 1) for t, c in counts.items() if c >= 2}
    return [t for t, _ in sorted(scored.items(), key=lambda kv: -kv[1])[:top]]


@dataclass
class Proposal:
    start: float
    end: float
    score: float  # 0-100 (percentil entre todos los tramos candidatos)
    raw: float
    interest: float
    energy_z: float
    wpm: float
    questions: int
    dead_air: float
    keywords: list[str]
    inner_topics: int
    first: str
    last: str


def propose(
    wins: list[Window], min_s: float, max_s: float, count: int, gap: float = 30.0, exclude: list[tuple[float, float]] | None = None
) -> list[Proposal]:
    """Tramos de entre `min_s` y `max_s` con más interés sostenido, que empiezan y acaban en cambios de tema, sin aire muerto
    y sin solaparse entre sí (ni con `exclude`)."""
    if not wins:
        return []
    window = wins[0].end - wins[0].start or 1.0
    kmin, kmax = max(1, int(round(min_s / window))), max(1, int(round(max_s / window)))
    interest = np.array([w.interest for w in wins])
    dead = np.array([1.0 if w.speech < 0.45 else 0.0 for w in wins])
    bnd = np.array([w.boundary for w in wins])
    ci, cd = np.concatenate([[0], np.cumsum(interest)]), np.concatenate([[0], np.cumsum(dead)])
    n = len(wins)
    cands = []
    for i in range(n):
        for k in range(kmin, kmax + 1):
            j = i + k
            if j > n:
                break
            m_int, d_frac = (ci[j] - ci[i]) / k, (cd[j] - cd[i]) / k
            inner = bnd[i + 1:j]
            coherence = 1 - float(inner.mean()) if len(inner) else 1.0
            edge = (bnd[i] if i > 0 else 0.6) + (bnd[j] if j < n else 0.6)
            raw = m_int + 0.6 * coherence + 0.4 * edge / 2 - 1.5 * d_frac
            if wins[j - 1].end - wins[i].start > max_s + 1e-6 and k > kmin:
                continue
            cands.append((raw, i, j, m_int, d_frac))
    if not cands:
        return []
    raws = np.array([c[0] for c in cands])
    order = sorted(range(len(cands)), key=lambda x: -cands[x][0])
    taken: list[tuple[float, float]] = list(exclude or [])
    out: list[Proposal] = []
    for x in order:
        raw, i, j, m_int, d_frac = cands[x]
        s, e = wins[i].start, wins[j - 1].end
        if any(s < b + gap and e > a - gap for a, b in taken):
            continue
        group = wins[i:j]
        counts: Counter = Counter()
        for w in group:
            counts.update(w.counts)
        text = " ".join(w.text for w in group).strip()
        out.append(Proposal(
            start=s, end=e, score=float(round(100 * (raws < raw).mean(), 1)), raw=float(raw), interest=float(m_int),
            energy_z=float(np.mean([w.interest for w in group])), wpm=float(np.mean([w.wpm for w in group])),
            questions=int(sum(w.questions for w in group)), dead_air=float(d_frac), keywords=keywords(counts, wins),
            inner_topics=int((bnd[i + 1:j] > 0.6).sum()), first=text[:220], last=text[-180:],
        ))  # fmt: skip
        taken.append((s, e))
        if len(out) >= count:
            break
    return sorted(out, key=lambda p: -p.score)
