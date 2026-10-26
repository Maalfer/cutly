"""Transcriptor determinista para tests: una frase de 5 palabras cada 5 s."""

from collections.abc import Callable
from pathlib import Path

from cutly.services.transcribe.base import SAMPLE_RATE
from cutly.services.transcribe.types import Segment, Word


class FakeTranscriber:
    def transcribe(
        self,
        pcm_path: Path,
        *,
        language: str | None,
        duration: float,
        on_progress: Callable[[float], None],
        cancelled: Callable[[], bool],
        vocabulary: str | None = None,
        beam_size: int | None = None,
    ) -> tuple[list[Segment], str]:
        secs = pcm_path.stat().st_size / 2 / SAMPLE_RATE
        segs, t, i = [], 0.0, 0
        while t + 4.0 <= secs:
            words = [Word(w=f"palabra{i}_{k}", start=t + k * 0.8, end=t + k * 0.8 + 0.7, p=0.9) for k in range(5)]
            segs.append(
                Segment(id=i, start=words[0].start, end=words[-1].end, text=" ".join(w.w for w in words), words=words)
            )
            t, i = t + 5.0, i + 1
            on_progress(min(t / secs, 0.99))
        return segs, language or "es"
