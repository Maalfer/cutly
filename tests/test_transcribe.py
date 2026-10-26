import subprocess

import numpy as np
import pytest
from sqlmodel import Session

from cutly.db.session import get_engine
from cutly.services.transcribe.base import SAMPLE_RATE
from cutly.services.transcribe.cleanup import apply_text_edit, is_hallucination
from cutly.services.transcribe.windows import plan_windows

API = "/api/v1"


def test_windows_cut_in_silence():
    rng = np.random.default_rng(0)
    pcm = (rng.standard_normal(SAMPLE_RATE * 130) * 3000).astype(np.int16)  # ruido continuo
    gap = SAMPLE_RATE * 58  # hueco de 1 s en el segundo 58, cerca del corte nominal de 60
    pcm[gap : gap + SAMPLE_RATE] = 0
    wins = plan_windows(pcm, window_s=60, search_s=10)
    assert wins[0][0] == 0 and wins[-1][1] == len(pcm)
    assert all(a[1] == b[0] for a, b in zip(wins, wins[1:], strict=False))  # sin huecos ni solapes
    assert gap <= wins[0][1] <= gap + SAMPLE_RATE  # cortó dentro del silencio


def test_short_audio_single_window():
    assert plan_windows(np.zeros(SAMPLE_RATE * 30, dtype=np.int16), window_s=600) == [(0, SAMPLE_RATE * 30)]


def test_hallucination_filter():
    assert is_hallucination("Subtítulos por la comunidad de Amara.org", 0.5, -0.5)
    assert is_hallucination("   ", 0.0, 0.0)
    assert is_hallucination("hmm", 0.8, -1.5)
    assert not is_hallucination("Hola, hoy hablamos de IA", 0.05, -0.3)


def _seg():
    ws = [{"w": w, "start": i * 0.5, "end": i * 0.5 + 0.4, "p": 0.9} for i, w in enumerate(["hola", "mundo", "cruel"])]
    return {"id": 0, "start": 0.0, "end": 1.9, "text": "hola mundo cruel", "words": ws}


def test_edit_same_word_count_keeps_timing():
    out = apply_text_edit(_seg(), "hola mundo bello")
    assert [w["w"] for w in out["words"]] == ["hola", "mundo", "bello"]
    assert out["words"][2]["start"] == 1.0


def test_edit_different_count_redistributes():
    out = apply_text_edit(_seg(), "hola a todo el mundo")
    assert len(out["words"]) == 5 and out["text"] == "hola a todo el mundo"
    assert out["words"][0]["start"] == 0.0 and abs(out["words"][-1]["end"] - 1.9) < 0.01
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(out["words"], out["words"][1:], strict=False))
    with pytest.raises(ValueError):
        apply_text_edit(_seg(), "   ")


def test_transcribe_api_with_fake_engine(writer, sample_video, monkeypatch):
    from cutly.config import get_settings

    monkeypatch.setenv("CUTLY_TRANSCRIBER_BACKEND", "fake")
    get_settings.cache_clear()
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    assert writer.get(f"{API}/media/{mid}/transcript").status_code == 404

    job = writer.post(f"{API}/media/{mid}/transcribe", json={"language": "es"}).json()["job_id"]
    j = writer.get(f"{API}/jobs/{job}").json()
    assert j["status"] == "done", j
    t = writer.get(f"{API}/media/{mid}/transcript").json()
    assert t["language"] == "es" and len(t["segments"]) == 0  # 3 s < 4 s: el falso no emite nada

    # transcripción con duración suficiente: 12 s de vídeo
    long = sample_video.parent / "long.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=12",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=12", "-c:v", "libx264", "-c:a", "aac", str(long)],
        check=True,
    )  # fmt: skip
    mid = writer.post(f"{API}/media/simple", params={"filename": "l.mp4"}, content=long.read_bytes()).json()["media_id"]
    assert writer.post(f"{API}/media/{mid}/transcribe", json={}).status_code == 200
    t = writer.get(f"{API}/media/{mid}/transcript", params={"format": "text"}).json()
    assert t["text"].splitlines()[0].startswith("[00:00:00] #0 palabra0_0")
    r = writer.patch(f"{API}/media/{mid}/transcript/segments/0", json={"text": "hola mundo de la ia hoy"})
    assert r.status_code == 200 and r.json()["text"] == "hola mundo de la ia hoy"
    again = writer.get(f"{API}/media/{mid}/transcript", params={"words": "false"}).json()["segments"][0]
    assert again["text"] == "hola mundo de la ia hoy" and "words" not in again
    assert writer.patch(f"{API}/media/{mid}/transcript/segments/99", json={"text": "x"}).status_code == 404
    from cutly.config import get_settings as gs

    assert not list(gs().media_dir.glob("*/audio16k.pcm"))
    # volver a transcribir reemplaza, no duplica
    writer.post(f"{API}/media/{mid}/transcribe", json={})
    from sqlmodel import Session, func, select

    from cutly.db.models import Transcript
    from cutly.db.session import get_engine

    with Session(get_engine()) as s:
        assert s.exec(select(func.count()).select_from(Transcript).where(Transcript.media_id == mid)).one() == 1


def _words_seg():
    ws = [("flag", 0.0, 0.3), ("pack", 0.3, 0.6), ("list", 0.7, 1.0), ("eh", 1.0, 1.2), ("yo", 1.3, 1.5)]
    words = [{"w": w, "start": s, "end": e, "p": 0.9} for w, s, e in ws]
    return {"id": 0, "start": 0.0, "end": 1.5, "text": " ".join(w[0] for w in ws), "words": words}


def test_word_edits_keep_timing_of_other_words():
    from cutly.services.transcribe.cleanup import apply_word_edits

    out = apply_word_edits(
        _words_seg(), [{"op": "merge", "index": 0, "to": 1, "text": "flatpak"}, {"op": "delete", "index": 3}]
    )
    assert [w["w"] for w in out["words"]] == ["flatpak", "list", "yo"] and out["text"] == "flatpak list yo"
    assert (out["words"][0]["start"], out["words"][0]["end"]) == (0.0, 0.6)  # hereda inicio y fin de las unidas
    assert out["words"][1]["start"] == 0.7 and out["words"][2]["start"] == 1.3  # el resto intacto
    out = apply_word_edits(_words_seg(), [{"op": "replace", "index": 2, "text": "install"}])
    assert out["words"][2]["w"] == "install" and out["words"][2]["end"] == 1.0
    for bad in (
        [{"op": "replace", "index": 9, "text": "x"}],
        [{"op": "merge", "index": 4, "text": "x"}],
        [{"op": "replace", "index": 0, "text": " "}],
    ):
        with pytest.raises(ValueError):
            apply_word_edits(_words_seg(), bad)


def test_word_edit_endpoint_and_vocabulary(writer, sample_video, monkeypatch):
    from cutly.config import get_settings
    from cutly.db.models import Job, Transcript

    monkeypatch.setenv("CUTLY_TRANSCRIBER_BACKEND", "fake")
    get_settings.cache_clear()
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=mid, segments=[_words_seg()]))
        s.commit()
    r = writer.patch(
        f"{API}/media/{mid}/transcript/segments/0/words",
        json={"edits": [{"op": "merge", "index": 0, "to": 1, "text": "flatpak"}]},
    )
    assert r.status_code == 200 and r.json()["text"].startswith("flatpak list")
    assert (
        writer.patch(
            f"{API}/media/{mid}/transcript/segments/0/words",
            json={"edits": [{"op": "replace", "index": 50, "text": "x"}]},
        ).status_code
        == 422
    )
    assert (
        writer.patch(
            f"{API}/media/{mid}/transcript/segments/9/words", json={"edits": [{"op": "delete", "index": 0}]}
        ).status_code
        == 404
    )

    jid = writer.post(
        f"{API}/media/{mid}/transcribe", json={"language": "es", "vocabulary": "apt, flatpak", "beam_size": 5}
    ).json()["job_id"]
    with Session(get_engine()) as s:
        params = s.get(Job, jid).params
    assert params["vocabulary"] == "apt, flatpak" and params["beam_size"] == 5
    assert writer.post(f"{API}/media/{mid}/transcribe", json={"beam_size": 99}).status_code == 422
