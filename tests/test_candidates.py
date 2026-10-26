from cutly.services.candidates.snapping import dedupe, flatten_words, snap_to_sentences
from cutly.services.candidates.types import Candidate

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


def _media_with_transcript(writer, sample_video, segs):
    from sqlmodel import Session

    from cutly.db.models import Transcript
    from cutly.db.session import get_engine

    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    if segs:
        with Session(get_engine()) as s:
            s.add(Transcript(media_id=mid, segments=segs))
            s.commit()
    return mid


def test_agent_registers_candidates_and_reviews_them(writer, sample_video):
    mid = _media_with_transcript(writer, sample_video, make_segments(0))
    dur = writer.get(f"{API}/media/{mid}").json()["duration"]  # el vídeo de prueba dura 3 s
    assert writer.post(f"{API}/media/{mid}/candidates", json={"candidates": []}).status_code == 422
    assert writer.post(f"{API}/media/nope/candidates", json={"candidates": [{"start": 0, "end": 5}]}).status_code == 404
    too_short = writer.post(f"{API}/media/{mid}/candidates", json={"candidates": [{"start": 0.0, "end": 1.0}]})
    assert too_short.status_code == 422 and "candidates[0]" in too_short.json()["detail"]
    beyond = writer.post(f"{API}/media/{mid}/candidates", json={"candidates": [{"start": 0.0, "end": dur + 30}]})
    assert beyond.status_code == 422 and "supera" in beyond.json()["detail"]
    ok = writer.post(
        f"{API}/media/{mid}/candidates",
        json={"candidates": [{"start": 0.0, "end": dur, "title": "Mi clip", "criteria": ["hook"], "score": 88}]},
    )
    assert ok.status_code == 200, ok.text
    made = ok.json()["created"]
    assert (
        len(made) == 1 and made[0]["status"] == "proposed" and made[0]["title"] == "Mi clip" and made[0]["score"] == 88
    )
    cid = made[0]["id"]
    # un clip que se solapa con uno existente se omite y se explica; criterios inválidos se rechazan
    again = writer.post(
        f"{API}/media/{mid}/candidates", json={"candidates": [{"start": 0.0, "end": dur, "title": "otro"}]}
    ).json()
    assert again["created"] == [] and again["skipped"][0]["reason"].startswith("se solapa")
    assert (
        writer.post(
            f"{API}/media/{mid}/candidates", json={"candidates": [{"start": 0, "end": 3, "criteria": ["x"]}]}
        ).status_code
        == 422
    )
    assert writer.patch(f"{API}/candidates/{cid}", json={"start": 1, "end": 2}).status_code == 422  # <3 s
    assert writer.patch(f"{API}/candidates/{cid}", json={"title": "Nuevo"}).json()["title"] == "Nuevo"
    assert writer.post(f"{API}/candidates/{cid}/accept").json()["status"] == "accepted"
    assert len(writer.get(f"{API}/media/{mid}/candidates", params={"status": "accepted"}).json()) == 1
    assert writer.post(f"{API}/candidates/{cid}/discard").json()["status"] == "discarded"
    assert writer.delete(f"{API}/candidates/{cid}").json() == {"ok": True}
    assert writer.get(f"{API}/candidates/{cid}").status_code == 404


def test_candidates_snap_to_sentences_and_replace_proposed(writer, sample_video, monkeypatch):
    segs = make_segments(10)  # 50 s de transcripción; las frases acaban al final de los segmentos impares
    mid = _media_with_transcript(writer, sample_video, segs)
    from sqlmodel import Session

    from cutly.db.models import Media
    from cutly.db.session import get_engine

    with Session(
        get_engine()
    ) as s:  # el vídeo de prueba dura 3 s; lo alargamos para poder probar tiempos de la transcripción
        m = s.get(Media, mid)
        m.duration = 120.0
        s.add(m)
        s.commit()
    r = writer.post(
        f"{API}/media/{mid}/candidates", json={"candidates": [{"start": 21.0, "end": 47.0, "title": "a"}]}
    ).json()
    c = r["created"][0]
    assert 19.7 <= c["start"] <= 20.0 and c["end"] >= 49.0  # ajustado a inicio y fin de frase
    raw = writer.post(
        f"{API}/media/{mid}/candidates",
        json={"snap": False, "candidates": [{"start": 21.0, "end": 47.0, "title": "b"}]},
    )
    assert raw.json()["created"] == []  # se solapa con el anterior
    rep = writer.post(
        f"{API}/media/{mid}/candidates",
        json={"snap": False, "replace_proposed": True, "candidates": [{"start": 21.0, "end": 47.0, "title": "b"}]},
    ).json()
    assert rep["created"][0]["start"] == 21.0
    assert [x["title"] for x in writer.get(f"{API}/media/{mid}/candidates").json()] == ["b"]


def test_there_is_no_ai_proposal_endpoint(writer, sample_video):
    mid = _media_with_transcript(writer, sample_video, make_segments(5))
    assert writer.post(f"{API}/media/{mid}/candidates/propose").status_code in (404, 405)
