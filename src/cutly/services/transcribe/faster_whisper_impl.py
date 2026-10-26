"""Motor local con faster-whisper. Importa la librería solo cuando se usa."""

from collections.abc import Callable
from pathlib import Path

import numpy as np

from cutly.config import get_settings
from cutly.services.transcribe.base import SAMPLE_RATE, TranscriptionCancelled
from cutly.services.transcribe.cleanup import is_hallucination, renumber
from cutly.services.transcribe.types import Segment, Word
from cutly.services.transcribe.windows import plan_windows


class FasterWhisperTranscriber:
    def __init__(self):
        self.s = get_settings()
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self.s.models_dir.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(
                self.s.whisper_model,
                device=self.s.whisper_device,
                compute_type=self.s.whisper_compute,
                cpu_threads=self.s.whisper_threads,
                download_root=str(self.s.models_dir),
            )
        return self._model

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
        model = self._load()
        pcm = np.memmap(pcm_path, dtype="<i2", mode="r")
        total = max(len(pcm) / SAMPLE_RATE, 1.0)
        out: list[Segment] = []
        prompt: str | None = None
        hint = f"Vocabulario: {vocabulary}. " if vocabulary else ""
        for a, b in plan_windows(pcm, self.s.whisper_window_s):
            audio = np.asarray(pcm[a:b], dtype=np.float32) / 32768.0
            offset = a / SAMPLE_RATE
            segs, info = model.transcribe(
                audio,
                language=language,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                beam_size=beam_size or self.s.whisper_beam_size,
                initial_prompt=(hint + (prompt or "")) or None,
                condition_on_previous_text=False,
            )
            language = language or info.language  # fija el idioma detectado en la 1ª ventana
            for seg in segs:  # generador perezoso: aquí se hace el trabajo
                if cancelled():
                    raise TranscriptionCancelled()
                on_progress(min((offset + seg.end) / total, 0.99))
                if is_hallucination(seg.text, seg.no_speech_prob, seg.avg_logprob):
                    continue
                words = [
                    Word(
                        w=w.word.strip(),
                        start=round(offset + w.start, 3),
                        end=round(offset + w.end, 3),
                        p=round(w.probability, 3),
                    )
                    for w in (seg.words or [])
                    if w.word.strip()
                ]
                if not words:
                    continue
                out.append(
                    Segment(
                        id=0,
                        start=words[0].start,
                        end=words[-1].end,
                        text=" ".join(w.w for w in words),
                        words=words,
                    )
                )
            prompt = " ".join(s.text for s in out[-3:])[-200:] or None  # continuidad entre ventanas
        return renumber(out), language or "es"
