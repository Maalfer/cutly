import pytest
from sqlmodel import Session

from cutly.db.models import ClipCandidate, Transcript
from cutly.db.session import get_engine

API = "/api/v1"


@pytest.fixture
def media_id(writer, sample_video):
    return writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]


@pytest.fixture
def project(writer, media_id):
    r = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0.5, "source_out": 2.5, "name": "P"})
    assert r.status_code == 200, r.text
    return r.json()


def ops(writer, pid, *items, **kw):
    return writer.post(f"{API}/projects/{pid}/ops", json={"ops": list(items), **kw})


def test_create_from_candidate_with_subtitles(writer, media_id):
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=media_id, segments=[{"id": 0, "start": 0, "end": 1, "text": "hola", "words": []}]))
        c = ClipCandidate(media_id=media_id, start=0.2, end=2.8, title="Mi clip")
        s.add(c)
        s.commit()
        cid = c.id
    r = writer.post(f"{API}/projects", json={"media_id": media_id, "candidate_id": cid})
    p = r.json()
    assert p["name"] == "Mi clip" and p["candidate_id"] == cid and abs(p["duration"] - 2.6) < 1e-6
    assert [layer["type"] for layer in p["project"]["layers"]] == ["subtitle"]
    assert p["project"]["layers"][0]["end"] == p["duration"]
    assert writer.post(f"{API}/projects", json={"media_id": media_id}).status_code == 422
    assert (
        writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0, "source_out": 99}).status_code == 422
    )


def test_timeline_ops(writer, project):
    pid, c1 = project["id"], project["project"]["timeline"][0]["id"]
    r = ops(writer, pid, {"op": "split_clip", "clip_id": c1, "at_output": 1.0})
    tl = r.json()["project"]["timeline"]
    assert len(tl) == 2 and tl[0]["source_out"] == 1.5 == tl[1]["source_in"]
    c2 = tl[1]["id"]
    r = ops(
        writer,
        pid,
        {"op": "move_clip", "clip_id": c2, "to_index": 0},
        {"op": "set_clip_speed", "clip_id": c1, "speed": 2},
    )
    tl = r.json()["project"]["timeline"]
    assert [c["id"] for c in tl] == [c2, c1] and abs(r.json()["duration"] - (1.0 + 0.5)) < 1e-6
    r = ops(writer, pid, {"op": "set_clip_range", "clip_id": c2, "source_out": 2.0})
    assert r.json()["project"]["timeline"][0]["source_out"] == 2.0
    r = ops(writer, pid, {"op": "delete_clip", "clip_id": c2})
    assert len(r.json()["project"]["timeline"]) == 1
    r = ops(writer, pid, {"op": "add_clip", "source_in": 1, "source_out": 2, "index": 0})
    assert len(r.json()["project"]["timeline"]) == 2


def test_actionable_errors_and_atomic_batch(writer, project):
    pid, c1 = project["id"], project["project"]["timeline"][0]["id"]
    r = ops(writer, pid, {"op": "delete_clip", "clip_id": "nope"})
    assert r.status_code == 422 and c1 in r.json()["detail"]  # lista los clips existentes
    r = ops(writer, pid, {"op": "split_clip", "clip_id": c1, "at_source": 99})
    assert r.status_code == 422 and "dentro del clip" in r.json()["detail"]
    r = ops(writer, pid, {"op": "split_clip", "clip_id": c1})
    assert r.status_code == 422 and "exactamente uno" in r.json()["detail"]
    # lote: la primera op es válida, la segunda falla → no se aplica nada
    before = writer.get(f"{API}/projects/{pid}").json()
    r = ops(
        writer, pid, {"op": "set_color", "patch": {"contrast": 1.5}}, {"op": "set_audio", "patch": {"target_lufs": 5}}
    )
    assert r.status_code == 422 and "Operación 2" in r.json()["detail"]
    after = writer.get(f"{API}/projects/{pid}").json()
    assert after["version"] == before["version"] and after["project"]["color"]["contrast"] == 1
    r = ops(writer, pid, {"op": "add_clip", "source_in": 1, "source_out": 500})
    assert r.status_code == 422 and "dura" in r.json()["detail"]  # más allá del vídeo
    assert writer.post(f"{API}/projects/{pid}/ops", json={"ops": [{"op": "hack"}]}).status_code == 422


def test_layers_crud_and_validation(writer, project):
    pid = project["id"]
    r = writer.post(
        f"{API}/projects/{pid}/layers", json={"layer": {"type": "text", "id": "t1", "end": 1.5, "text": "Hola"}}
    )
    assert r.status_code == 200 and r.json()["project"]["layers"][-1]["id"] == "t1"
    assert (
        writer.post(
            f"{API}/projects/{pid}/layers", json={"layer": {"type": "text", "id": "t1", "end": 1, "text": "x"}}
        ).status_code
        == 422
    )
    r = writer.patch(
        f"{API}/projects/{pid}/layers/t1",
        json={"patch": {"text": "Adiós", "style": {"color": "#FF0000"}, "opacity": 0.5}},
    )
    layer = [x for x in r.json()["project"]["layers"] if x["id"] == "t1"][0]
    assert layer["text"] == "Adiós" and layer["style"]["color"] == "#FF0000" and layer["style"]["size"] == 0.045
    bad = writer.patch(f"{API}/projects/{pid}/layers/t1", json={"patch": {"style": {"color": "rojo"}}})
    assert bad.status_code == 422 and "color" in bad.json()["detail"]
    assert writer.patch(f"{API}/projects/{pid}/layers/t1", json={"patch": {"type": "icon"}}).status_code == 422
    assert writer.patch(f"{API}/projects/{pid}/layers/zzz", json={"patch": {}}).status_code == 422
    r = writer.post(
        f"{API}/projects/{pid}/layers",
        json={"layer": {"type": "icon", "id": "i1", "start": 0.5, "end": 9, "asset": "icons/star"}},
    )
    assert any("se recortará" in w for w in r.json()["warnings"])
    assert writer.delete(f"{API}/projects/{pid}/layers/i1").status_code == 200


def test_reframe_audio_color_output(writer, project):
    pid = project["id"]
    rect = {"x": 0.7, "y": 0.0, "w": 0.3, "h": 0.3}
    game = {"x": 0, "y": 0, "w": 0.7, "h": 1}
    r = ops(
        writer,
        pid,
        {"op": "set_reframe", "patch": {"mode": "stack", "facecam": rect, "game": game}},
        {"op": "set_audio", "patch": {"gain_db": 3}},
        {"op": "set_color", "patch": {"saturation": 1.2}},
        {"op": "set_output", "patch": {"fps": 60}},
    )
    p = r.json()["project"]
    assert p["reframe"]["mode"] == "stack" and p["audio"]["gain_db"] == 3 and p["output"]["fps"] == 60
    bad = ops(writer, pid, {"op": "set_reframe", "patch": {"game": None}})
    assert bad.status_code == 422 and "game" in bad.json()["detail"]


def test_undo_redo_and_branching(writer, project):
    pid = project["id"]
    ops(writer, pid, {"op": "set_color", "patch": {"contrast": 1.3}}, label="contraste")
    ops(writer, pid, {"op": "set_audio", "patch": {"gain_db": 6}})
    h = writer.get(f"{API}/projects/{pid}/history").json()
    assert [e["label"] for e in h["entries"]] == ["contraste", "set_audio"] and h["cursor"] == 2
    r = writer.post(f"{API}/projects/{pid}/undo").json()
    assert (
        r["project"]["audio"]["gain_db"] == 0
        and r["project"]["color"]["contrast"] == 1.3
        and r["can_redo"]
        and r["can_undo"]
    )
    r = writer.post(f"{API}/projects/{pid}/undo").json()
    assert r["project"]["color"]["contrast"] == 1 and not r["can_undo"]
    assert writer.post(f"{API}/projects/{pid}/undo").status_code == 422
    r = writer.post(f"{API}/projects/{pid}/redo").json()
    assert r["project"]["color"]["contrast"] == 1.3
    # un cambio nuevo tras deshacer descarta lo rehacible
    ops(writer, pid, {"op": "set_color", "patch": {"saturation": 0.5}})
    assert writer.post(f"{API}/projects/{pid}/redo").status_code == 422
    h = writer.get(f"{API}/projects/{pid}/history").json()
    assert len(h["entries"]) == 2 and h["cursor"] == 2
    # una operación que no cambia nada no ensucia el historial
    v = writer.get(f"{API}/projects/{pid}").json()["version"]
    ops(writer, pid, {"op": "set_color", "patch": {"saturation": 0.5}})
    assert writer.get(f"{API}/projects/{pid}").json()["version"] == v


def test_optimistic_concurrency(writer, project):
    pid, v = project["id"], project["version"]
    assert ops(writer, pid, {"op": "set_color", "patch": {"contrast": 1.1}}, base_version=v).status_code == 200
    r = ops(writer, pid, {"op": "set_color", "patch": {"contrast": 1.2}}, base_version=v)  # versión vieja
    assert r.status_code == 409 and "léelo de nuevo" in r.json()["detail"]
    assert writer.get(f"{API}/projects/{pid}").json()["project"]["color"]["contrast"] == 1.1


def test_subtitles_follow_duration(writer, media_id):
    with Session(get_engine()) as s:
        s.add(Transcript(media_id=media_id, segments=[]))
        s.commit()
    p = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0, "source_out": 2}).json()
    cid = p["project"]["timeline"][0]["id"]
    r = ops(writer, p["id"], {"op": "set_clip_range", "clip_id": cid, "source_out": 1.0}).json()
    assert r["duration"] == 1.0 and r["project"]["layers"][0]["end"] == 1.0


def test_list_rename_delete_schema_and_permissions(writer, client, project, media_id):
    pid = project["id"]
    assert [x["id"] for x in writer.get(f"{API}/projects", params={"media_id": media_id}).json()] == [pid]
    assert writer.patch(f"{API}/projects/{pid}", json={"name": "Nuevo"}).json()["name"] == "Nuevo"
    assert "ProjectDoc" in writer.get(f"{API}/project-schema").json()["title"]
    assert writer.delete(f"{API}/projects/{pid}").status_code == 200
    assert writer.get(f"{API}/projects/{pid}").status_code == 404

    from cutly.auth import generate_api_key

    with Session(get_engine()) as s:
        _, tok = generate_api_key(s, "ro", can_write=False)
    ro = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{API}/projects", headers=ro).status_code == 200
    assert (
        client.post(
            f"{API}/projects", headers=ro, json={"media_id": media_id, "source_in": 0, "source_out": 1}
        ).status_code
        == 403
    )


def test_delete_project_and_media_with_history(writer, media_id):
    """Regresión: borrar un proyecto con historial violaba la clave foránea (500)."""
    p = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0, "source_out": 2}).json()
    ops(writer, p["id"], {"op": "set_color", "patch": {"contrast": 1.4}})
    assert writer.delete(f"{API}/projects/{p['id']}").status_code == 200
    p2 = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0, "source_out": 2}).json()
    ops(writer, p2["id"], {"op": "set_color", "patch": {"contrast": 1.4}})
    assert writer.delete(f"{API}/media/{media_id}").status_code == 200
    assert writer.get(f"{API}/projects/{p2['id']}").status_code == 404


def test_add_title_endpoint(writer, project):
    pid = project["id"]
    body = {"start": 0.2, "end": 1.8, "lines": [{"text": "11 Skills", "style": "title"}, {"text": "a la vez", "style": "kicker"}]}
    dry = writer.post(f"{API}/projects/{pid}/title", json={**body, "dry_run": True})
    assert dry.status_code == 200 and dry.json()["dry_run"] and dry.json()["layer_id"]
    assert not writer.get(f"{API}/projects/{pid}").json()["project"]["layers"]  # dry_run no guarda
    r = writer.post(f"{API}/projects/{pid}/title", json=body)
    assert r.status_code == 200, r.text
    layer = [x for x in r.json()["project"]["layers"] if x["id"] == r.json()["layer_id"]][0]
    assert layer["type"] == "scene" and layer["transparent"] is True and layer["params"]["lines"][1]["in"] == "tracking"
    assert writer.post(f"{API}/projects/{pid}/title", json={**body, "lines": []}).status_code == 422
    assert writer.post(f"{API}/projects/{pid}/title", json={**body, "start": 2, "end": 1}).status_code == 422


def test_horizontal_layout_keeps_the_full_16_9_frame(writer, media_id):
    r = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0.5, "source_out": 2.5, "layout": "horizontal"})
    assert r.status_code == 200, r.text
    doc = r.json()["project"]
    assert (doc["output"]["width"], doc["output"]["height"]) == (1920, 1080)
    assert doc["reframe"]["mode"] == "custom" and doc["reframe"]["game"] == {"x": 0, "y": 0, "w": 1, "h": 1}
    v = writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0.5, "source_out": 2.5}).json()["project"]
    assert (v["output"]["width"], v["output"]["height"]) == (1080, 1920)  # por defecto, vertical como siempre
    assert writer.post(f"{API}/projects", json={"media_id": media_id, "source_in": 0, "source_out": 1, "layout": "cuadrado"}).status_code == 422
