"""Orquestación: bloques → modelo → validación → ajuste a frases → deduplicado → ranking."""

from collections.abc import Callable

from cutly.config import get_settings
from cutly.services.candidates.chunking import make_chunks, render_chunk
from cutly.services.candidates.llm import CandidateLLM
from cutly.services.candidates.snapping import dedupe, flatten_words, snap_to_sentences
from cutly.services.candidates.types import ALL_CRITERIA, Candidate, ProposeParams, Usage


class Cancelled(Exception):
    pass


def propose_candidates(
    segments: list[dict],
    llm: CandidateLLM,
    params: ProposeParams,
    on_progress: Callable[[float], None] = lambda p: None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[list[Candidate], dict]:
    s = get_settings()
    by_id = {seg["id"]: seg for seg in segments}
    chunks = make_chunks(segments, s.candidates_chunk_s, s.candidates_overlap_s)
    usage, raw_found, dropped = Usage(), 0, {"ids": 0, "duracion": 0, "puntuacion": 0, "frase": 0}
    found: list[Candidate] = []
    for n, chunk in enumerate(chunks):
        if cancelled():
            raise Cancelled()
        id_range = (chunk[0]["id"], chunk[-1]["id"])
        raws, u = llm.propose(render_chunk(chunk), id_range, params)
        usage.input_tokens += u.input_tokens
        usage.output_tokens += u.output_tokens
        usage.refusals += u.refusals
        in_chunk = {x["id"] for x in chunk}
        for r in raws:
            raw_found += 1
            if r.start_segment not in in_chunk or r.end_segment not in in_chunk or r.end_segment < r.start_segment:
                dropped["ids"] += 1
                continue
            if not 50 <= r.score <= 100:
                dropped["puntuacion"] += 1
                continue
            a, b = by_id[r.start_segment], by_id[r.end_segment]
            snapped = snap_to_sentences(
                flatten_words(
                    [
                        x
                        for x in segments
                        if a["id"] <= x["id"] <= b["id"] or abs(x["id"] - a["id"]) <= 3 or abs(x["id"] - b["id"]) <= 3
                    ]
                ),
                a["start"],
                b["end"],
            )
            if snapped is None:
                dropped["frase"] += 1
                continue
            start, end = snapped
            if not params.min_seconds * 0.9 <= end - start <= params.long_max_seconds * 1.05:
                dropped["duracion"] += 1
                continue
            crit = [c for c in r.criteria if c in ALL_CRITERIA]
            found.append(Candidate(start, end, float(r.score), r.title.strip()[:120], r.reason.strip()[:500], crit))
        on_progress((n + 1) / len(chunks))
    final = dedupe(found)
    final = sorted(final, key=lambda c: -c.score)[: params.max_candidates]
    stats = {
        "chunks": len(chunks), "raw": raw_found, "after_dedupe": len(final), "dropped": dropped,
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "refusals": usage.refusals,
    }  # fmt: skip
    return sorted(final, key=lambda c: c.start), stats
