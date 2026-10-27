"""Análisis de directos largos con una transcripción y unos picos sintéticos (sin Whisper)."""

import numpy as np

from cutly.services.analysis import stream as S


def _stream(minutes=40):
    """Directo sintético: charla tranquila sobre «cocina», a los 15-22 min un debate animado sobre «bitcoin» (rápido, alto,
    con preguntas) y aire muerto entre el minuto 30 y el 33."""
    segs, t = [], 0.0
    end = minutes * 60
    while t < end:
        lively = 15 * 60 <= t < 22 * 60
        dead = 30 * 60 <= t < 33 * 60
        if dead:
            t += 5
            continue
        topic = ["bitcoin", "mercado", "inversión", "riesgo"] if lively else ["cocina", "receta", "sartén", "tomate"]
        n = 14 if lively else 8
        words, dt = [], (0.28 if lively else 0.42)
        for k in range(n):
            words.append({"w": topic[k % 4] + ("?" if lively and k == n - 1 else "."), "start": t + k * dt, "end": t + k * dt + dt * 0.8})
        segs.append({"id": len(segs), "start": t, "end": t + n * dt, "text": " ".join(w["w"] for w in words), "words": words})
        t += n * dt + (0.2 if lively else 1.2)
    bins = int(end / 0.05)
    amp = np.full(bins, 20, dtype=np.int16)
    lo, hi = int(15 * 60 / 0.05), int(22 * 60 / 0.05)
    amp[lo:hi] = 90  # voz más alta en el debate
    amp[int(30 * 60 / 0.05): int(33 * 60 / 0.05)] = 2
    peaks = np.stack([-amp, amp], axis=1).astype(np.int8)
    return segs, float(end), peaks


def test_windows_capture_the_lively_debate_and_dead_air():
    segs, dur, peaks = _stream()
    wins = S.build_windows(segs, dur, 60, peaks)
    assert len(wins) == 40
    lively = np.mean([w.interest for w in wins[15:22]])
    calm = np.mean([w.interest for w in wins[2:12]])
    assert lively > calm + 1.0
    assert all(w.interest <= -1 for w in wins[30:33])  # aire muerto: nunca interesante
    assert wins[16].questions > 0 and wins[5].questions == 0


def test_topic_boundary_peaks_where_the_subject_changes():
    segs, dur, peaks = _stream()
    wins = S.build_windows(segs, dur, 60, peaks)
    best = max(range(1, len(wins)), key=lambda i: wins[i].boundary)
    assert best in (15, 22)  # entrada o salida del debate
    assert wins[15].boundary >= 0.6 and wins[6].boundary < 0.3


def test_keywords_distinguish_topics():
    segs, dur, peaks = _stream()
    wins = S.build_windows(segs, dur, 60, peaks)
    assert "bitcoin" in S.keywords(wins[17].counts, wins) or "mercado" in S.keywords(wins[17].counts, wins)
    assert "receta" in S.keywords(wins[5].counts, wins) or "cocina" in S.keywords(wins[5].counts, wins)


def test_proposals_find_the_debate_respect_limits_and_do_not_overlap():
    segs, dur, peaks = _stream(60)
    wins = S.build_windows(segs, dur, 60, peaks)
    props = S.propose(wins, 300, 600, 4)
    assert props and all(300 <= p.end - p.start <= 600 + 1 for p in props)
    top = props[0]
    assert top.start <= 15 * 60 + 90 and top.end >= 22 * 60 - 90  # cubre (casi) todo el debate
    assert top.dead_air == 0
    spans = sorted((p.start, p.end) for p in props)
    assert all(b[0] >= a[1] for a, b in zip(spans, spans[1:]))
    assert props == sorted(props, key=lambda p: -p.score)


def test_exclude_ranges_are_respected():
    segs, dur, peaks = _stream(60)
    wins = S.build_windows(segs, dur, 60, peaks)
    props = S.propose(wins, 300, 600, 3, exclude=[(14 * 60, 23 * 60)])
    assert all(p.end <= 14 * 60 - 30 + 1 or p.start >= 23 * 60 + 30 - 1 for p in props)


def test_works_without_audio_peaks():
    segs, dur, _ = _stream()
    wins = S.build_windows(segs, dur, 60, None)
    assert all(w.energy == 0 for w in wins) and np.mean([w.interest for w in wins[15:22]]) > 0.5


# --- API ---

API = "/api/v1"


def test_outline_and_suggest_need_a_transcript_then_work(writer, sample_video):
    from sqlmodel import Session

    from cutly.db.models import Transcript
    from cutly.db.session import get_engine

    mid = writer.post(f"{API}/media/simple", params={"filename": "d.mp4"}, content=sample_video.read_bytes()).json()["media_id"]
    assert writer.get(f"{API}/media/{mid}/outline").status_code == 409
    assert writer.post(f"{API}/media/{mid}/suggest-segments", json={}).status_code == 409
    words = [{"w": "hola.", "start": 0.2, "end": 0.6}, {"w": "directo?", "start": 0.7, "end": 1.2}]
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=mid, segments=[{"id": 0, "start": 0.2, "end": 1.2, "text": "hola. directo?", "words": words}]))
        s.commit()
    o = writer.get(f"{API}/media/{mid}/outline", params={"window": 30}).json()
    assert o["windows"] and o["windows"][0]["questions"] == 1 and "hint" in o
    sg = writer.post(f"{API}/media/{mid}/suggest-segments", json={"save": True})
    assert sg.status_code == 200 and sg.json()["segments"] == [] and sg.json()["registered"] == []  # 3 s: no hay tramo de 5 min
    assert writer.post(f"{API}/media/{mid}/suggest-segments", json={"min_minutes": 8, "max_minutes": 5}).status_code == 422
