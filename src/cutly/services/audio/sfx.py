"""Efectos de sonido sintetizados (sin ficheros ni licencias): whoosh, golpe, pop, riser…

Se generan con numpy de forma determinista (misma semilla = mismo sonido) y se guardan en caché como WAV
estéreo de 48 kHz. Los usa la capa `audio` al renderizar; el catálogo (`GET /sfx`) los describe para el agente.
"""

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 48000


@dataclass(frozen=True)
class SfxDef:
    name: str
    duration: float
    description: str
    use: str


CATALOG: dict[str, SfxDef] = {d.name: d for d in [
    SfxDef("whoosh", 0.7, "Barrido de aire suave que sube y baja.", "Cambio de plano, transición, aparición de un título grande o un whip_pan (empieza ~0,1 s antes del corte)."),
    SfxDef("whoosh_fast", 0.32, "Barrido de aire corto y seco.", "Aparición rápida de rótulos, iconos o un zoom_blur breve."),
    SfxDef("hit", 0.9, "Golpe grave de impacto con cola corta.", "Palabra de impacto, revelación, el final de un riser o un zoom de énfasis fuerte."),
    SfxDef("pop", 0.16, "Burbuja corta y limpia.", "Aparición de un rótulo pequeño, icono o palabra con rebote."),
    SfxDef("click", 0.06, "Clic seco de interfaz.", "Pulsar un botón, un paso de lista, un cambio de pestaña."),
    SfxDef("ding", 1.3, "Campanilla brillante que se apaga.", "Acierto, resultado positivo, cifra que llega a su valor."),
    SfxDef("riser", 2.0, "Tensión ascendente de ruido filtrado.", "Antes de una revelación: termina justo donde pones un `hit`."),
    SfxDef("glitch", 0.4, "Ráfagas digitales entrecortadas.", "Error, fallo, hackeo, o un efecto glitch."),
]}  # fmt: skip


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return x * (peak / m)


def _svf_sweep(noise: np.ndarray, f0: np.ndarray, q: float = 0.9, mode: str = "bp") -> np.ndarray:
    """Filtro de variable de estado con frecuencia de corte variable en el tiempo (barridos)."""
    low = band = 0.0
    out = np.empty_like(noise)
    g = 2 * np.sin(np.pi * np.clip(f0, 20, SR * 0.45) / SR)
    for i, x in enumerate(noise):
        low += g[i] * band
        high = x - low - q * band
        band += g[i] * high
        out[i] = band if mode == "bp" else low
    return out


def _t(dur: float) -> np.ndarray:
    return np.linspace(0, dur, int(SR * dur), endpoint=False)


def _stereo(rng, make) -> np.ndarray:
    """Dos canales con ruido independiente: ancho estéreo."""
    return np.stack([make(rng), make(rng)], axis=1)


def _whoosh(dur: float, lo: float, hi: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _t(dur)
    u = t / dur
    sweep = lo + (hi - lo) * np.sin(np.pi * u) ** 1.5
    env = np.sin(np.pi * u) ** 2 * (0.6 + 0.4 * u)

    def make(r):
        return _svf_sweep(r.standard_normal(len(t)), sweep, 0.7) * env

    return _stereo(rng, make)


def _hit() -> np.ndarray:
    rng = np.random.default_rng(3)
    t = _t(0.9)
    f = 38 + 90 * np.exp(-t * 14)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5.5)
    click = _svf_sweep(rng.standard_normal(len(t)), np.full(len(t), 900.0), 0.8, "lp") * np.exp(-t * 60)
    tail = _svf_sweep(rng.standard_normal(len(t)), np.full(len(t), 160.0), 0.8, "lp") * np.exp(-t * 7) * 0.5
    x = np.tanh(2.2 * (body + 0.6 * click + tail))
    return np.stack([x, x], axis=1)


def _pop() -> np.ndarray:
    t = _t(0.16)
    f = 520 * np.exp(-t * 9) + 260
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26) * np.minimum(1, t / 0.004)
    return np.stack([x, x], axis=1)


def _click() -> np.ndarray:
    rng = np.random.default_rng(5)
    t = _t(0.06)
    n = rng.standard_normal(len(t))
    hp = n - _svf_sweep(n, np.full(len(t), 2500.0), 0.8, "lp")
    x = hp * np.exp(-t * 110) + 0.5 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 140)
    return np.stack([x, x], axis=1)


def _ding() -> np.ndarray:
    t = _t(1.3)
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in ((1318, 1.0, 4.0), (1976, 0.55, 5.5), (2637, 0.3, 7.5), (3951, 0.12, 11.0)))
    x = x * np.minimum(1, t / 0.002)
    return np.stack([x, x * 0.96], axis=1)


def _riser() -> np.ndarray:
    rng = np.random.default_rng(11)
    dur = 2.0
    t = _t(dur)
    u = t / dur
    env = u**2.2

    def make(r):
        return _svf_sweep(r.standard_normal(len(t)), 300 + 5200 * u**2, 0.6) * env

    noise = _stereo(rng, make)
    tone = np.sin(2 * np.pi * np.cumsum(180 + 900 * u**2) / SR) * env * 0.25
    return noise + tone[:, None]


def _glitch() -> np.ndarray:
    rng = np.random.default_rng(17)
    n = int(SR * 0.4)
    x = np.zeros(n)
    pos = 0
    while pos < n:
        seg = int(SR * rng.uniform(0.01, 0.05))
        gate = rng.random() > 0.35
        if gate:
            burst = np.sign(rng.standard_normal(seg)) * rng.uniform(0.3, 1.0)
            burst = np.round(burst * 4) / 4  # bitcrush
            freq = rng.uniform(400, 4000)
            burst = burst * (np.sin(2 * np.pi * freq * np.arange(seg) / SR) > 0)
            x[pos:pos + seg] = burst[: n - pos]
        pos += seg
    x *= np.exp(-np.linspace(0, 1, n) * 1.5)
    return np.stack([x, np.roll(x, 40)], axis=1)


def synth(name: str) -> np.ndarray:
    if name == "whoosh":
        x = _whoosh(0.7, 350, 4200, 1)
    elif name == "whoosh_fast":
        x = _whoosh(0.32, 700, 6500, 2)
    elif name == "hit":
        x = _hit()
    elif name == "pop":
        x = _pop()
    elif name == "click":
        x = _click()
    elif name == "ding":
        x = _ding()
    elif name == "riser":
        x = _riser()
    elif name == "glitch":
        x = _glitch()
    else:
        raise KeyError(name)
    return _norm(x)


def sfx_path(name: str, cache_dir: Path) -> Path:
    """WAV del efecto (lo genera la primera vez)."""
    if name not in CATALOG:
        raise KeyError(f"Efecto de sonido desconocido: {name}. Disponibles: {', '.join(CATALOG)}")
    path = cache_dir / f"{name}.wav"
    if not path.is_file():
        cache_dir.mkdir(parents=True, exist_ok=True)
        pcm = (synth(name) * 32767).astype("<i2")
        tmp = path.with_suffix(".tmp")
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        tmp.replace(path)
    return path
