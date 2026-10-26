"""Job `candidates.propose`: elige clips de la transcripción con el modelo y los guarda."""

from sqlmodel import Session, select

from cutly.db.models import ClipCandidate, Transcript
from cutly.db.session import get_engine
from cutly.services.candidates.llm import get_llm
from cutly.services.candidates.pipeline import Cancelled, propose_candidates
from cutly.services.candidates.types import ProposeParams
from cutly.worker.jobs import JobContext, handler
from cutly.worker.subprocess_runner import JobCancelled


@handler("candidates.propose")
def propose(ctx: JobContext) -> dict:
    media_id = ctx.params["media_id"]
    params = ProposeParams(**ctx.params["params"])
    with Session(get_engine()) as session:
        t = session.exec(select(Transcript).where(Transcript.media_id == media_id)).first()
        if t is None or not t.segments:
            raise RuntimeError("No hay transcripción: lanza antes POST /media/{id}/transcribe")
        segments = t.segments
    try:
        cands, stats = propose_candidates(segments, get_llm(), params, ctx.progress, ctx.cancelled)
    except Cancelled as e:
        raise JobCancelled() from e
    with Session(get_engine()) as session:
        for old in session.exec(
            select(ClipCandidate).where(ClipCandidate.media_id == media_id, ClipCandidate.status == "proposed")
        ).all():
            session.delete(old)
        rows = [
            ClipCandidate(
                media_id=media_id,
                start=c.start,
                end=c.end,
                score=c.score,
                title=c.title,
                reason=c.reason,
                criteria=c.criteria,
            )  # fmt: skip
            for c in cands
        ]
        session.add_all(rows)
        session.commit()
        ids = [r.id for r in rows]
    return {**stats, "candidate_ids": ids}
