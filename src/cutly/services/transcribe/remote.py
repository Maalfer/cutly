"""Motor remoto (GPU alquilada o API). Contrato previsto, aún sin implementar.

Contrato propuesto para CUTLY_TRANSCRIBER_REMOTE_URL:
  POST {url}/transcribe  (multipart: file=<pcm s16le 16 kHz mono>, language=<es|auto>)
  → 200 {"language": "es", "segments": [{"start":..,"end":..,"words":[{"w","start","end","p"}]}]}
Implementarlo aquí no requiere tocar nada más: solo cumplir la interfaz `Transcriber`.
"""

from cutly.services.transcribe.base import Transcriber  # noqa: F401


class RemoteTranscriber:
    def transcribe(self, *args, **kwargs):
        raise NotImplementedError(
            "El transcriptor remoto aún no está implementado. Usa CUTLY_TRANSCRIBER_BACKEND=faster_whisper."
        )
