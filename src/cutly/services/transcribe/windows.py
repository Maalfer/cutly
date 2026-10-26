"""Troceado del audio en ventanas que cortan en silencios (nunca a mitad de palabra)."""

import numpy as np

from cutly.services.transcribe.base import SAMPLE_RATE


def plan_windows(
    pcm: np.ndarray, window_s: int, search_s: float = 15.0, frame_s: float = 0.25
) -> list[tuple[int, int]]:
    """Divide `pcm` (int16) en ventanas de ~`window_s`; cada corte va al punto más silencioso
    dentro de ±`search_s` del límite nominal. Sin solapamiento."""
    n = len(pcm)
    win = window_s * SAMPLE_RATE
    if n <= win * 1.25:
        return [(0, n)]
    frame = int(frame_s * SAMPLE_RATE)
    cuts = [0]
    while n - cuts[-1] > win * 1.25:
        nominal = cuts[-1] + win
        lo = max(cuts[-1] + frame, nominal - int(search_s * SAMPLE_RATE))
        hi = min(n - frame, nominal + int(search_s * SAMPLE_RATE))
        seg = np.abs(pcm[lo:hi].astype(np.int32))
        usable = len(seg) // frame * frame
        energy = seg[:usable].reshape(-1, frame).mean(axis=1)
        best = int(np.argmin(energy))
        cuts.append(lo + best * frame + frame // 2)
    cuts.append(n)
    return list(zip(cuts[:-1], cuts[1:], strict=True))
