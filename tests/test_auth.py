from sqlmodel import Session

from cutly.auth import generate_api_key, hash_password
from cutly.db.models import User
from cutly.db.session import get_engine


def _user(client):
    with Session(get_engine()) as s:
        s.add(User(username="mario", password_hash=hash_password("una-clave-larga-1")))
        s.commit()


def test_health_is_public(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_and_key_lifecycle(client):
    _user(client)
    assert client.post("/api/v1/auth/login", json={"username": "mario", "password": "mal"}).status_code == 401
    assert (
        client.post("/api/v1/auth/login", json={"username": "mario", "password": "una-clave-larga-1"}).status_code
        == 200
    )
    r = client.post("/api/v1/api-keys", json={"name": "claude", "can_write": True})
    token, key_id = r.json()["token"], r.json()["id"]
    assert "key_hash" not in client.get("/api/v1/api-keys").json()[0]

    client.post("/api/v1/auth/logout")
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=h).json()["can_write"] is True

    client.post("/api/v1/auth/login", json={"username": "mario", "password": "una-clave-larga-1"})
    client.delete(f"/api/v1/api-keys/{key_id}")
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401


def test_read_only_key_cannot_write(client):
    with Session(get_engine()) as s:
        _, token = generate_api_key(s, "ro", can_write=False)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    assert client.get("/api/v1/api-keys", headers=h).status_code == 403


def test_write_key_cannot_list_api_keys(client):
    """GET /api-keys es gestión de credenciales (como POST/DELETE): solo la sesión web, nunca un portador de clave."""
    with Session(get_engine()) as s:
        _, token = generate_api_key(s, "agente-externo", can_write=True)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=h).json()["can_write"] is True
    assert client.get("/api/v1/api-keys", headers=h).status_code == 403


def test_web_is_served_with_strict_csp(client):
    r = client.get("/")
    assert r.status_code == 200 and "importmap" in r.text
    csp = r.headers["content-security-policy"]
    assert "script-src 'self' 'sha256-" in csp and "frame-ancestors 'none'" in csp
    assert client.get("/vendor/preact.js").status_code == 200
    assert client.get("/api/v1/health").headers["cache-control"] == "no-store"


def test_agent_guide_uses_server_url(writer):
    r = writer.get("/api/v1/agent-guide")
    assert r.status_code == 200 and "http://testserver/api/v1" in r.text and "{{" not in r.text
    assert "tools/upload.py" in r.text and r.headers["content-type"].startswith("text/markdown")
    assert writer.get("/tools/upload.py").status_code == 200


def test_agent_guide_only_mentions_things_that_exist(writer):
    """La guía es lo que lee el agente: no puede citar presets, efectos ni iconos inexistentes."""
    import re

    guide = writer.get("/api/v1/agent-guide").text
    for kind, name in set(re.findall(r'"preset":"(\w+):(\w+)"', guide)) | set(
        re.findall(r"`(text|layer):(\w+)`", guide)
    ):
        assert writer.get(f"/api/v1/presets/{kind}/{name}").status_code == 200, f"{kind}:{name}"
    effects = {e["name"] for e in writer.get("/api/v1/effects").json()["effects"]}
    for name in re.findall(
        r"`(zoom_punch|slow_zoom|shake|flash|glitch|vignette|color_pulse|progress_bar|letterbox|film_grain|blur_focus|negative_flash)`",
        guide,
    ):
        assert name in effects
    for aid in re.findall(r"`(icons/[\w-]+)`", guide):
        assert writer.get(f"/api/v1/assets/item/{aid}").status_code == 200, aid
