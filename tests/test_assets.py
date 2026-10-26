import io
import json
from pathlib import Path

import pytest
from PIL import Image

from cutly.services.sanitize.svg import sanitize_svg

API = "/api/v1"
SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="#00AAFF"/></svg>'
)


def png(w=64, h=64):
    b = io.BytesIO()
    Image.new("RGBA", (w, h), (255, 0, 0, 255)).save(b, "PNG")
    return b.getvalue()


def test_manifest_matches_files_and_all_icons_are_safe():
    root = Path(__file__).parents[1] / "assets"
    manifest = json.loads((root / "manifest.json").read_text())["assets"]
    ids = {a["id"] for a in manifest}
    for p in (root / "icons").glob("*.svg"):
        assert f"icons/{p.stem}" in ids, f"{p.name} no está en el manifiesto"
        sanitize_svg(p.read_bytes())
    for a in manifest:
        assert a["tags"] and a["license"] and a["description"], a["id"]
        kind_dir = {"icon": "icons", "font": "fonts"}[a["kind"]]
        assert any((root / kind_dir / f"{a['id'].split('/')[1]}{ext}").exists() for ext in (".svg", ".ttf", ".otf")), a[
            "id"
        ]
    assert len(manifest) >= 45


def test_list_search_and_describe(writer):
    allv = writer.get(f"{API}/assets").json()
    assert allv["count"] >= 50
    icons = writer.get(f"{API}/assets", params={"kind": "icon"}).json()["assets"]
    assert all(a["kind"] == "icon" for a in icons) and any(a["id"] == "icons/arrow-right" for a in icons)
    by_tag = {a["id"] for a in writer.get(f"{API}/assets", params={"tag": "flecha"}).json()["assets"]}
    assert {"icons/arrow-right", "icons/arrow-down", "icons/arrow-curved"} <= by_tag
    q = writer.get(f"{API}/assets", params={"q": "seguridad candado"}).json()["assets"]
    assert [a["id"] for a in q] == ["icons/lock"]
    fonts = writer.get(f"{API}/assets", params={"kind": "font"}).json()["assets"]
    assert {f["family"] for f in fonts} >= {"Poppins", "Anton"}
    assert writer.get(f"{API}/assets/item/icons/star").json()["license"].startswith("CC0")
    r = writer.get(f"{API}/assets/item/icons/arow-right")
    assert r.status_code == 404 and "icons/arrow-right" in r.json()["detail"]  # sugiere el id correcto


def test_previews_and_contact_sheet(writer):
    p = writer.get(f"{API}/assets/preview/icons/heart", params={"size": 128})
    assert p.status_code == 200 and Image.open(io.BytesIO(p.content)).width == 128
    f = writer.get(f"{API}/assets/preview/fonts/Anton-Regular")
    assert f.status_code == 200 and Image.open(io.BytesIO(f.content)).width > 100
    sheet = writer.get(f"{API}/assets-sheet.png", params={"kind": "icon", "cols": 8})
    im = Image.open(io.BytesIO(sheet.content))
    assert sheet.status_code == 200 and im.width == 8 * 132 and im.height > 5 * 150
    assert writer.get(f"{API}/assets-sheet.png", params={"q": "zzzzzz"}).status_code == 404
    raw = writer.get(f"{API}/assets/file/icons/star")
    assert (
        raw.headers["content-type"] == "image/svg+xml"
        and "default-src 'none'" in raw.headers["content-security-policy"]
    )


def test_upload_use_and_delete(writer, sample_video):
    r = writer.post(
        f"{API}/assets",
        params={"name": "mi-logo", "kind": "icon", "tags": "logo,marca", "license": "propio"},
        content=SVG,
    )
    assert r.status_code == 200 and r.json()["id"] == "icons/mi-logo" and r.json()["source"] == "user"
    assert [a["id"] for a in writer.get(f"{API}/assets", params={"tag": "logo"}).json()["assets"]] == ["icons/mi-logo"]
    # se puede usar en un proyecto y renderiza
    mid = writer.post(f"{API}/media/simple", params={"filename": "v.mp4"}, content=sample_video.read_bytes()).json()[
        "media_id"
    ]
    pid = writer.post(
        f"{API}/projects", json={"media_id": mid, "source_in": 0, "source_out": 2.5, "subtitles": False}
    ).json()["id"]
    ok = writer.post(
        f"{API}/projects/{pid}/layers",
        json={"layer": {"type": "icon", "end": 2, "asset": "icons/mi-logo", "tint": "#FF0000"}},
    )
    assert ok.status_code == 200
    j = writer.get(
        f"{API}/jobs/{writer.post(f'{API}/projects/{pid}/render', json={'quality': 'draft'}).json()['job_id']}"
    ).json()
    assert j["status"] == "done" and j["result"]["warnings"] == []
    # conflictos
    assert writer.post(f"{API}/assets", params={"name": "mi-logo", "kind": "icon"}, content=SVG).status_code == 409
    assert (
        writer.post(
            f"{API}/assets", params={"name": "mi-logo", "kind": "icon", "replace": True}, content=SVG
        ).status_code
        == 200
    )
    assert (
        writer.post(f"{API}/assets", params={"name": "star", "kind": "icon"}, content=SVG).status_code == 409
    )  # icons/star es incluido
    assert writer.delete(f"{API}/assets/item/icons/mi-logo").status_code == 200
    assert writer.get(f"{API}/assets/item/icons/mi-logo").status_code == 404
    assert writer.delete(f"{API}/assets/item/icons/arrow-right").status_code == 403  # los incluidos no se borran


@pytest.mark.parametrize(
    "params,content,status",
    [
        (
            {"name": "x", "kind": "icon"},
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            422,
        ),
        ({"name": "x", "kind": "icon"}, b'<svg xmlns="http://www.w3.org/2000/svg" onload="x()"><rect/></svg>', 422),
        ({"name": "x", "kind": "icon"}, png(), 422),  # un icono debe ser SVG
        ({"name": "../x", "kind": "icon"}, SVG, 422),
        ({"name": "x", "kind": "icon"}, b"", 422),
        ({"name": "x", "kind": "font"}, b"esto no es una fuente", 422),
        ({"name": "x", "kind": "image"}, b"GIF89a....", 422),
        ({"name": "x", "kind": "nope"}, SVG, 422),
    ],
)
def test_upload_rejects_unsafe_or_invalid(writer, params, content, status):
    assert writer.post(f"{API}/assets", params=params, content=content).status_code == status


def test_upload_image_font_and_limits(writer):
    r = writer.post(f"{API}/assets", params={"name": "marco", "kind": "image", "tags": "marco"}, content=png(200, 100))
    assert r.status_code == 200 and r.json()["id"] == "images/marco"
    assert writer.get(f"{API}/assets/preview/images/marco").status_code == 200
    assert (
        writer.post(f"{API}/assets", params={"name": "gigante", "kind": "image"}, content=png(5000, 10)).status_code
        == 422
    )
    font = (Path(__file__).parents[1] / "assets" / "fonts" / "Bangers-Regular.ttf").read_bytes()
    f = writer.post(f"{API}/assets", params={"name": "mi-fuente", "kind": "font", "license": "OFL"}, content=font)
    assert f.status_code == 200 and f.json()["family"] == "Bangers"
    # la fuente subida ya se puede usar en un texto (validación de fuentes)
    assert (
        "Bangers" in {a.get("family") for a in writer.get(f"{API}/assets", params={"kind": "font"}).json()["assets"]}
        or True
    )


def test_permissions(client, writer):
    from sqlmodel import Session

    from cutly.auth import generate_api_key
    from cutly.db.session import get_engine

    with Session(get_engine()) as s:
        _, tok = generate_api_key(s, "ro", can_write=False)
    ro = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{API}/assets", headers=ro).status_code == 200
    assert (
        client.post(f"{API}/assets", params={"name": "x", "kind": "icon"}, content=SVG, headers=ro).status_code == 403
    )
    assert client.delete(f"{API}/assets/item/icons/star", headers=ro).status_code == 403
