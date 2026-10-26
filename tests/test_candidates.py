import json
from types import SimpleNamespace

import pytest

from cutly.services.candidates.chunking import make_chunks
from cutly.services.candidates.llm import SCHEMA, AnthropicLLM
from cutly.services.candidates.snapping import dedupe, flatten_words, snap_to_sentences
from cutly.services.candidates.types import Candidate, ProposeParams

API = "/api/v1"


def make_segments(n=40, dur=5.0):
    """Segmentos de 5 s con 5 palabras; la última de cada segmento par cierra frase."""
    segs = []
    for i in range(n):
        t = i * dur
        words = []
        for k in range(5):
            w = f"p{i}_{k}"
            if k == 4 and i % 2 == 1:
                w += "."
            words.append({"w": w, "start": t + k * 0.9, "end": t + k * 0.9 + 0.8, "p": 0.9})
        segs.append(
            {
                "id": i,
                "start": words[0]["start"],
                "end": words[-1]["end"],
                "text": " ".join(x["w"] for x in words),
                "words": words,
            }
        )
    return segs


def test_chunks_overlap_and_cover():
    segs = make_segments(600)  # 50 min
    chunks = make_chunks(segs, size_s=1500, overlap_s=180)
    assert len(chunks) == 3
    assert chunks[0][0]["id"] == 0 and chunks[-1][-1]["id"] == 599
    assert chunks[1][0]["start"] < chunks[0][-1]["end"]  # hay solape
    assert make_chunks(make_segments(10), 1500, 180) == [make_segments(10)]


def test_snap_moves_to_sentence_boundaries():
    words = flatten_words(make_segments(10))
    # frases terminan al final de los segmentos impares (id 1, 3, 5…): la 3ª frase abarca segs 4-5
    start, end = snap_to_sentences(words, 21.0, 47.0)  # seg 4 empieza en 20.0; seg 9 acaba en ~49.6
    assert 19.7 <= start <= 20.0  # inicio de frase (seg 4) con margen
    assert end >= 49.0  # fin de frase (seg 9 termina con punto)
    assert snap_to_sentences([], 0, 1) is None


def test_dedupe_keeps_best():
    a = Candidate(100, 160, 80, "a", "", [])
    b = Candidate(110, 170, 90, "b", "", [])  # casi el mismo momento, mejor puntuación
    c = Candidate(300, 350, 70, "c", "", [])
    out = dedupe([a, b, c])
    assert [x.title for x in out] == ["b", "c"]


class StubClient:
    def __init__(self, texts, stop="end_turn"):
        self.calls, self.texts, self.stop = [], list(texts), stop
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.calls.append(kw)
        stop = self.stop if not isinstance(self.stop, list) else self.stop[len(self.calls) - 1]
        return SimpleNamespace(
            stop_reason=stop, usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            content=[SimpleNamespace(type="text", text=self.texts[min(len(self.calls) - 1, len(self.texts) - 1)])],
        )  # fmt: skip


def test_anthropic_request_shape_and_parse():
    good = json.dumps(
        {
            "candidates": [
                {"start_segment": 2, "end_segment": 9, "title": "T", "reason": "R", "criteria": ["hook"], "score": 85}
            ]
        }
    )
    stub = StubClient([good])
    raws, usage = AnthropicLLM(stub).propose("[2 @ 0:00:10] hola", (0, 20), ProposeParams())
    kw = stub.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["output_config"]["format"]["schema"] == SCHEMA
    assert kw["output_config"]["effort"] == "high"
    for banned in ("temperature", "top_p", "top_k", "tool_choice", "budget_tokens"):
        assert banned not in kw  # no admitidos en estos modelos
    assert "<transcripcion>" in kw["messages"][0]["content"] and kw["messages"][-1]["role"] == "user"
    assert raws[0].score == 85 and usage.input_tokens == 100


def test_refusal_uses_fallback_then_gives_up():
    good = json.dumps({"candidates": []})
    stub = StubClient([good, good], stop=["refusal", "end_turn"])
    raws, usage = AnthropicLLM(stub).propose("x", (0, 1), ProposeParams())
    assert [c["model"] for c in stub.calls] == ["claude-opus-5-5", "claude-opus-4-8"] and usage.refusals == 1
    stub2 = StubClient([good], stop="refusal")
    raws, usage = AnthropicLLM(stub2).propose("x", (0, 1), ProposeParams())
    assert raws == [] and usage.refusals == 2
    with pytest.raises(RuntimeError, match="cortó"):
        AnthropicLLM(StubClient([good], stop="max_tokens")).propose("x", (0, 1), ProposeParams())


def test_candidates_api_flow(writer, sample_video, monkeypatch):
    from sqlmodel import Session

    from cutly.config import get_settings
    from cutly.db.models import Transcript
    from cutly.db.session import get_engine

    monkeypatch.setenv("CUTLY_CANDIDATES_BACKEND", "fake")
    get_settings.cache_clear()
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    assert writer.post(f"{API}/media/{mid}/candidates/propose").status_code == 409  # sin transcripción
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=mid, segments=make_segments(60)))
        s.commit()
    r = writer.post(
        f"{API}/media/{mid}/candidates/propose", json={"criteria": ["hook"], "min_seconds": 20, "max_seconds": 60}
    )
    j = writer.get(f"{API}/jobs/{r.json()['job_id']}").json()
    assert j["status"] == "done", j
    cands = writer.get(f"{API}/media/{mid}/candidates").json()
    assert len(cands) == 1 and cands[0]["status"] == "proposed" and cands[0]["text"].startswith("p")
    cid = cands[0]["id"]
    assert writer.patch(f"{API}/candidates/{cid}", json={"start": 5, "end": 6}).status_code == 422  # <3 s
    assert writer.patch(f"{API}/candidates/{cid}", json={"title": "Nuevo"}).json()["title"] == "Nuevo"
    assert writer.post(f"{API}/candidates/{cid}/accept").json()["status"] == "accepted"
    # volver a proponer conserva los aceptados
    writer.post(f"{API}/media/{mid}/candidates/propose")
    assert {c["status"] for c in writer.get(f"{API}/media/{mid}/candidates").json()} == {"accepted", "proposed"}
    assert len(writer.get(f"{API}/media/{mid}/candidates", params={"status": "accepted"}).json()) == 1
    assert writer.post(f"{API}/candidates/{cid}/discard").json()["status"] == "discarded"


def test_missing_api_key_is_actionable(writer, sample_video, monkeypatch):
    from sqlmodel import Session

    from cutly.db.models import Transcript
    from cutly.db.session import get_engine

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=mid, segments=make_segments(5)))
        s.commit()
    r = writer.post(f"{API}/media/{mid}/candidates/propose")
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]
