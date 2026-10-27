"""Servidor MCP de un solo archivo (web/tools/cutly_mcp.py): protocolo stdio y herramientas sobre la API real."""

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "web" / "tools" / "cutly_mcp.py"
spec = importlib.util.spec_from_file_location("cutly_mcp", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def rpc(method, params=None, id=1):
    return M.handle({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})


def test_protocol_basics():
    init = rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"]
    assert M.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert rpc("ping")["result"] == {}
    tools = rpc("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"cutly_guide", "cutly_api", "cutly_frame", "cutly_ops", "cutly_scene_preview"} <= names
    assert all(t["inputSchema"]["type"] == "object" and t["description"] for t in tools)
    assert rpc("nope")["error"]["code"] == -32601
    missing = rpc("tools/call", {"name": "cutly_frame", "arguments": {}})["result"]
    assert missing["isError"]


def test_stdio_process_speaks_json_lines():
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]  # fmt: skip
    p = subprocess.run([sys.executable, "-I", str(SCRIPT)], input="\n".join(map(json.dumps, msgs)) + "\n",
                       capture_output=True, text=True, timeout=20)  # fmt: skip
    out = [json.loads(x) for x in p.stdout.splitlines()]
    assert [o["id"] for o in out] == [1, 2] and len(out[1]["result"]["tools"]) >= 10


@pytest.fixture
def api(writer, monkeypatch):
    """Hace que el servidor MCP hable con la app de test (TestClient) en vez de con la red."""

    def fake(method, path, query=None, body=None):
        q = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in (query or {}).items() if v is not None}
        r = writer.request(method, f"/api/v1{path}", params=q, json=body)
        return r.status_code, r.headers.get("content-type", ""), r.content

    monkeypatch.setattr(M, "http", fake)
    return writer


def call(name, **args):
    return rpc("tools/call", {"name": name, "arguments": args})["result"]


def test_tools_against_the_real_api(api, sample_video):
    guide = call("cutly_guide")
    assert "Cutly" in guide["content"][0]["text"]
    mid = api.post("/api/v1/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()["media_id"]
    pid = api.post("/api/v1/projects", json={"media_id": mid, "source_in": 0, "source_out": 2.9}).json()["id"]
    dry = call("cutly_ops", project_id=pid, dry_run=True, ops=[{"op": "ripple_delete", "start": 1, "end": 2}])
    assert '"duration_after": 1.9' in dry["content"][0]["text"]
    assert call("cutly_summary", project_id=pid)["content"][0]["text"].count("out_start") == 1
    img = call("cutly_frame", project_id=pid, t=1.0)["content"][0]
    assert img["type"] == "image" and img["mimeType"] == "image/jpeg"
    assert base64.b64decode(img["data"])[:2] == b"\xff\xd8"
    bad = call("cutly_api", method="GET", path="/projects/p_nope")
    assert bad["isError"] and "404" in bad["content"][0]["text"]
    kit = call("cutly_scene_kit")["content"][0]["text"]
    assert "base_html" in kit


# --- v2: instrucciones, prompts, recursos y herramientas compuestas ----------------------------------------------


def test_instructions_prompts_resources_and_annotations():
    init = rpc("initialize", {})["result"]
    assert "cutly_review" in init["instructions"] and {"tools", "prompts", "resources"} <= set(init["capabilities"])
    prompts = {p["name"]: p for p in rpc("prompts/list")["result"]["prompts"]}
    assert {"edit_short", "clip_hunter", "explain_with_animation", "cleanup_dead_air", "polish_and_verify"} <= set(prompts)
    got = rpc("prompts/get", {"name": "edit_short", "arguments": {"project_id": "p_1", "goal": "gamer"}})["result"]
    text = got["messages"][0]["content"]["text"]
    assert "p_1" in text and "gamer" in text and "(no indicado)" in text  # lo que falta no rompe el prompt
    assert rpc("prompts/get", {"name": "nope"})["error"]["code"] == -32602
    assert [r["uri"] for r in rpc("resources/list")["result"]["resources"]][:2] == ["cutly://guide", "cutly://playbook"]
    pb = rpc("resources/read", {"uri": "cutly://playbook"})["result"]["contents"][0]
    assert "Hook" in pb["text"]
    tools = {t["name"]: t for t in rpc("tools/list")["result"]["tools"]}
    for ro in ("cutly_review", "cutly_frame", "cutly_overview", "cutly_catalog", "cutly_summary"):
        assert tools[ro]["annotations"]["readOnlyHint"] is True
    assert tools["cutly_ops"]["annotations"]["readOnlyHint"] is False
    assert len(tools) >= 24 and all(t["description"] for t in tools.values())
    for n in M.PROMPTS:  # ningún prompt revienta con argumentos vacíos
        assert M.get_prompt(n, {})["messages"][0]["content"]["text"]


def test_composite_tools_against_the_real_api(api, sample_video):
    mid = api.post("/api/v1/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()["media_id"]
    ov = call("cutly_overview")["content"][0]["text"]
    assert mid in ov and "v.mp4" in ov
    med = call("cutly_media", media_id=mid, frames=2)["content"]
    assert med[0]["type"] == "text" and sum(c["type"] == "image" for c in med) == 2
    st = call("cutly_start_project", media_id=mid, source_in=0, source_out=2.9)["content"][0]["text"]
    pid = st.split()[1]
    assert pid.startswith("p_") and "#/editor/" in st
    add = call("cutly_ops", project_id=pid, ops=[{"op": "add_layer", "layer": {"type": "text", "id": "t1", "start": 0.3, "end": 2.0, "text": "Hola"}}])
    assert not add.get("isError")
    rev = call("cutly_review", project_id=pid)["content"]
    assert rev[0]["type"] == "text" and "RESUMEN" in rev[0]["text"] and "COMPROBACIONES" in rev[0]["text"]
    assert any(c["type"] == "image" for c in rev), rev[0]["text"]
    lc = call("cutly_layer_check", project_id=pid, layer_id="t1")["content"]
    assert lc[-1]["type"] == "image"
    assert call("cutly_layer_check", project_id=pid, layer_id="nada")["isError"]
    cat = call("cutly_catalog", kind="presets", preset_kind="subtitle")["content"][0]["text"]
    assert cat.startswith("- subtitle:")
    assert "zoom_punch" in call("cutly_catalog", kind="effects")["content"][0]["text"]
    assert call("cutly_catalog", kind="templates", q="dns")["content"][0]["text"].count("dns_lookup") == 1
    assert "estado: done" in call("cutly_render", project_id=pid, quality="draft", wait=60)["content"][0]["text"]
    undo = call("cutly_undo", project_id=pid)
    assert not undo.get("isError")


def test_outline_and_find_segments_tools_on_a_long_synthetic_stream(api, sample_video):
    from sqlmodel import Session

    from cutly.db.models import Media, Transcript
    from cutly.db.session import get_engine

    mid = api.post("/api/v1/media/simple", params={"filename": "directo.mp4"}, content=sample_video.read_bytes()).json()["media_id"]
    segs, t = [], 0.0
    while t < 12 * 60:  # 12 min de charla; entre el 4:00 y el 9:30 el debate (rápido y con preguntas)
        lively = 4 * 60 <= t < 9.5 * 60
        topic = ["bitcoin", "mercado", "riesgo"] if lively else ["receta", "cocina", "tomate"]
        words, dt = [], 0.28 if lively else 0.45
        for k in range(12):
            words.append({"w": topic[k % 3] + ("?" if lively and k == 11 else "."), "start": t + k * dt, "end": t + k * dt + dt * 0.8})
        segs.append({"id": len(segs), "start": t, "end": t + 12 * dt, "text": " ".join(w["w"] for w in words), "words": words})
        t += 12 * dt + (0.2 if lively else 1.5)
    with Session(get_engine()) as s:
        m = s.get(Media, mid)
        m.duration = 12 * 60.0
        s.add(m)
        s.add(Transcript(media_id=mid, segments=segs))
        s.commit()
    out = call("cutly_outline", media_id=mid, window=60)
    text = out["content"][0]["text"]
    assert not out.get("isError") and "ESQUEMA" in text and "bitcoin" in text and "★" in text
    found = call("cutly_find_segments", media_id=mid, min_minutes=3, max_minutes=6, count=2, save=True)
    ftxt = found["content"][0]["text"]
    assert not found.get("isError") and "tramos propuestos" in ftxt and "Registrados como candidatos" in ftxt
    cands = api.get(f"/api/v1/media/{mid}/candidates").json()
    assert cands and all(180 <= c["duration"] <= 361 for c in cands) and cands[0]["status"] == "proposed"
    assert any(c["start"] < 4 * 60 + 90 and c["end"] > 9.5 * 60 - 90 or c["start"] >= 4 * 60 - 60 for c in cands)
    assert "stream_to_clips" in {p["name"] for p in rpc("prompts/list")["result"]["prompts"]}
