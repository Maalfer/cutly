import pytest

from cutly.services.presets import library as lib

API = "/api/v1"


def test_every_builtin_preset_is_valid_and_documented():
    items = lib.builtin_presets()
    assert len(items) >= 45 and {p["kind"] for p in items} == set(lib.KINDS)
    for p in items:
        lib.validate_data(p["kind"], p["data"])
        assert p["description"], p["name"]
        assert lib.NAME_RE.match(p["name"])
    assert len({(p["kind"], p["name"]) for p in items}) == len(items)


def test_validation_rejects_bad_data():
    for kind, data in [
        ("subtitle", {"size": 5}),  # fuera de rango
        ("subtitle", {"color": "rojo"}),
        ("color", {"saturation": 99}),
        ("transition", {"name": "no_existe"}),
        ("text", {"nonsense": 1}),
        ("layer", {"type": "subtitle"}),
        ("animation", {"enter": {"name": "volar"}}),
        ("nope", {}),
    ]:
        with pytest.raises(lib.PresetError):
            lib.validate_data(kind, data)


@pytest.fixture
def project(writer, sample_video):
    from sqlmodel import Session

    from cutly.db.models import Transcript
    from cutly.db.session import get_engine

    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    with Session(get_engine()) as s:
        words = [{"w": f"p{i}", "start": 0.2 + i * 0.4, "end": 0.55 + i * 0.4, "p": 1} for i in range(6)]
        s.add(Transcript(media_id=mid, segments=[{"id": 0, "start": 0.2, "end": 2.6, "text": "x", "words": words}]))
        s.commit()
    p = writer.post(f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 1.4}).json()
    writer.post(
        f"{API}/projects/{p['id']}/ops", json={"ops": [{"op": "add_clip", "source_in": 1.5, "source_out": 2.9}]}
    )
    return p["id"]


def apply(writer, pid, **body):
    return writer.post(f"{API}/projects/{pid}/presets/apply", json=body)


def test_list_search_get_create_delete(writer):
    allp = writer.get(f"{API}/presets").json()
    assert allp["count"] >= 45 and "subtitle" in allp["kinds"]
    subs = writer.get(f"{API}/presets", params={"kind": "subtitle"}).json()["presets"]
    assert {"reel_karaoke_yellow", "boxed_dark", "neon_cyan"} <= {p["name"] for p in subs}
    hit = writer.get(f"{API}/presets", params={"q": "cuenta atrás"}).json()["presets"]
    assert any(p["name"] == "big_number" for p in hit)
    assert writer.get(f"{API}/presets/subtitle/reel_karaoke_yellow").json()["data"]["highlight_color"] == "#FFD400"
    near = writer.get(f"{API}/presets/subtitle/reel_karaoke_yelow")
    assert near.status_code == 404 and "reel_karaoke_yellow" in near.json()["detail"]
    mine = {
        "kind": "subtitle",
        "name": "mi_estilo",
        "description": "El mío",
        "data": {"font": "Anton", "size": 0.05, "uppercase": True},
    }
    assert writer.post(f"{API}/presets", json=mine).json()["source"] == "user"
    assert writer.get(f"{API}/presets/subtitle/mi_estilo").json()["data"]["uppercase"] is True
    assert writer.post(f"{API}/presets", json={**mine, "kind": "color", "data": {"saturation": 9}}).status_code == 422
    assert writer.post(f"{API}/presets", json={**mine, "name": "reel_karaoke_yellow"}).status_code == 409
    assert writer.delete(f"{API}/presets/subtitle/mi_estilo").status_code == 200
    assert writer.delete(f"{API}/presets/subtitle/reel_karaoke_yellow").status_code == 403
    assert writer.delete(f"{API}/presets/subtitle/ya_no_existe").status_code == 404


def test_apply_every_kind_and_undo(writer, project):
    pid = project
    r = apply(writer, pid, preset="subtitle:neon_cyan").json()
    sub = [x for x in r["project"]["layers"] if x["type"] == "subtitle"][0]
    assert sub["style"]["font"] == "Anton" and sub["style"]["color"] == "#00E5FF" and sub["style"]["uppercase"] is True
    assert apply(writer, pid, preset="color:cinematic").json()["project"]["color"]["contrast"] == 1.14
    cids = [c["id"] for c in writer.get(f"{API}/projects/{pid}").json()["project"]["timeline"]]
    t = apply(writer, pid, preset="transition:quick_fade", clip_id="all").json()
    assert (
        t["project"]["timeline"][1]["transition_in"] == {"name": "fade", "dur": 0.25}
        and abs(t["duration"] - 2.55) < 1e-6
    )
    # capa completa: necesita start/end; con overrides se personaliza
    assert apply(writer, pid, preset="layer:check_done").status_code == 422
    L = apply(
        writer, pid, preset="layer:circle_highlight", start=0.5, end=2.0, overrides={"box": {"x": 0.3, "y": 0.4}}
    ).json()
    icon = [x for x in L["project"]["layers"] if x["type"] == "icon"][0]
    assert (
        icon["asset"] == "icons/circle-emphasis"
        and icon["box"]["x"] == 0.3
        and icon["animations"]["enter"]["name"] == "pop"
    )
    # texto nuevo desde preset, y animación sobre una capa existente
    T = apply(writer, pid, preset="text:title_hook", start=0.0, end=1.5, overrides={"text": "Hola"}).json()
    title = [x for x in T["project"]["layers"] if x["type"] == "text"][0]
    assert title["text"] == "Hola" and title["style"]["font"] == "Anton"
    A = apply(writer, pid, preset="animation:bounce_in", layer_id=title["id"]).json()
    assert [x for x in A["project"]["layers"] if x["id"] == title["id"]][0]["animations"]["enter"]["name"] == "bounce"
    St = apply(writer, pid, preset="text:label_red", layer_id=title["id"]).json()
    assert [x for x in St["project"]["layers"] if x["id"] == title["id"]][0]["style"]["bg_color"] == "#FF3B30E8"
    # todo es un paso de historial normal: se deshace
    before = writer.get(f"{API}/projects/{pid}").json()["version"]
    assert writer.post(f"{API}/projects/{pid}/undo").json()["version"] == before + 1
    assert cids and len(cids) == 2


def test_apply_errors_are_actionable(writer, project):
    pid = project
    assert "tipo:nombre" in apply(writer, pid, preset="reel_karaoke_yellow").json()["detail"]
    r = apply(writer, pid, preset="subtitle:reel_karaoke_yelow")
    assert r.status_code == 422 and "reel_karaoke_yellow" in r.json()["detail"]
    assert "clip_id" in apply(writer, pid, preset="transition:quick_fade").json()["detail"]
    assert "layer_id" in apply(writer, pid, preset="animation:pop_in_out").json()["detail"]
    assert apply(writer, pid, preset="subtitle:neon_cyan", layer_id="nope").status_code == 422
    assert (
        apply(writer, pid, preset="text:title_hook", layer_id="nope").status_code == 422
    )  # la capa no existe (lista las que hay)
    one = writer.post(
        f"{API}/projects",
        json={"media_id": writer.get(f"{API}/projects/{pid}").json()["media_id"], "source_in": 0, "source_out": 1},
    ).json()["id"]
    assert "un solo clip" in apply(writer, one, preset="transition:quick_fade", clip_id="all").json()["detail"]


def test_applying_subtitle_preset_creates_the_layer_when_missing(writer, sample_video):
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    pid = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 2, "subtitles": False}
    ).json()["id"]
    r = apply(writer, pid, preset="subtitle:gamer_comic").json()
    assert [x["style"]["font"] for x in r["project"]["layers"] if x["type"] == "subtitle"] == ["Bangers"]
