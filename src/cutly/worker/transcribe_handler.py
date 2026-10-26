"""Job `transcribe`: extrae audio 16 kHz mono, transcribe por ventanas y guarda el resultado."""

import os

from sqlmodel import Session, select

from cutly.config import get_settings
from cutly.db.models import Media, Transcript
from cutly.db.session import get_engine
from cutly.services.ingest.media_store import media_dir
from cutly.services.transcribe.base import TranscriptionCancelled, get_transcriber
from cutly.worker.jobs import JobContext, handler
from cutly.worker.subprocess_runner import JobCancelled, run_ffmpeg

EXTRACT_SHARE = 0.1  # el 10 % inicial del progreso es la extracción de audio


@handler("transcribe")
def transcribe(ctx: JobContext) -> dict:
    s = get_settings()
    with Session(get_engine()) as session:
        media = session.get(Media, ctx.params["media_id"])
        if media is None:
            raise RuntimeError("El medio ya no existe")
        if not media.metadata_json.get("has_audio"):
            raise RuntimeError("El vídeo no tiene pista de audio: no hay nada que transcribir")
        src, duration, media_id = media.original_path, media.duration or 0.0, media.id
    language = ctx.params.get("language")
    pcm = media_dir(media_id) / "audio16k.pcm"
    try:
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", src, "-map", "0:a:0",
            "-ac", "1", "-ar", "16000", "-f", "s16le", "-progress", "pipe:1", "-nostats", str(pcm),
        ]  # fmt: skip
        run_ffmpeg(
            cmd, duration=duration, timeout=s.job_timeout_s, cancelled=ctx.cancelled,
            on_progress=lambda p: ctx.progress(p * EXTRACT_SHARE),
        )  # fmt: skip
        segments, lang = get_transcriber().transcribe(
            pcm, language=language, duration=duration, cancelled=ctx.cancelled,
            vocabulary=ctx.params.get("vocabulary"), beam_size=ctx.params.get("beam_size"),
            on_progress=lambda p: ctx.progress(EXTRACT_SHARE + p * (1 - EXTRACT_SHARE)),
        )  # fmt: skip
    except TranscriptionCancelled as e:
        raise JobCancelled() from e
    finally:
        pcm.unlink(missing_ok=True)
    with Session(get_engine()) as session:
        for old in session.exec(select(Transcript).where(Transcript.media_id == media_id)).all():
            session.delete(old)
        t = Transcript(media_id=media_id, language=lang, segments=[x.model_dump() for x in segments])
        session.add(t)
        session.commit()
        return {"transcript_id": t.id, "segments": len(segments), "language": lang, "pid": os.getpid()}
