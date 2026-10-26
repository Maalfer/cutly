"""Interfaz del transcriptor.

Entrada: PCM crudo s16le, 16 kHz, mono (`SAMPLE_RATE`), en disco. Así un motor remoto
(GPU alquilada, API) puede recibir el audio sin tocar el resto del sistema.
Salida: segmentos con palabras y tiempos en segundos desde el inicio del audio.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from cutly.services.transcribe.types import Segment

SAMPLE_RATE = 16000


class TranscriptionCancelled(Exception):
    pass


class Transcriber(Protocol):
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
        """Devuelve (segmentos, idioma detectado o forzado). Lanza TranscriptionCancelled si procede."""
        ...


def get_transcriber() -> Transcriber:
    from cutly.config import get_settings

    backend = get_settings().transcriber_backend
    if backend == "faster_whisper":
        from cutly.services.transcribe.faster_whisper_impl import FasterWhisperTranscriber

        return FasterWhisperTranscriber()
    if backend == "remote":
        from cutly.services.transcribe.remote import RemoteTranscriber

        return RemoteTranscriber()
    if backend == "fake":
        from cutly.services.transcribe.fake import FakeTranscriber

        return FakeTranscriber()
    raise ValueError(f"CUTLY_TRANSCRIBER_BACKEND desconocido: {backend}")
