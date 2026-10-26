"""Siembra el servidor de desarrollo: sube el vídeo real, copia su transcripción corregida y monta el proyecto.

Si no existe el vídeo real de producción, usa uno sintético (así los tests también corren en otra máquina).
"""

import http.cookiejar
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

base = sys.argv[1]
D = Path(os.environ["CUTLY_DATA_DIR"])
REPO = Path(__file__).resolve().parents[2]
PROD = REPO / "data"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def api(method, path, data=None, raw=None, timeout=600):
    h = {}
    if data is not None:
        raw, h["Content-Type"] = json.dumps(data).encode(), "application/json"
    return json.loads(
        op.open(
            urllib.request.Request(base + "/api/v1" + path, data=raw, method=method, headers=h), timeout=timeout
        ).read()
    )


api("POST", "/auth/login", {"username": "test", "password": "testpass1234"})
state_file = D / "state.json"
if state_file.exists() and api("GET", "/media"):
    print(state_file.read_text())
    sys.exit(0)

real = next(iter((PROD / "media").glob("m_*/original.mp4")), None) if (PROD / "media").is_dir() else None
if real:
    src = real
else:
    src = D / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1080x1920:rate=30:duration=40",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=40",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
    )
mid = api("POST", "/media/simple?filename=apps-linux.mp4", raw=src.read_bytes())["media_id"]
# la transcripción corregida de producción (si existe)
prod_db = PROD / "cutly.db"
segments = []
if real and prod_db.exists():
    row = sqlite3.connect(prod_db).execute("select segments, language from transcript limit 1").fetchone()
    if row:
        segments = json.loads(row[0])
if not segments:  # transcripción sintética con palabras
    words = [
        {"w": w, "start": 0.4 + i * 0.45, "end": 0.8 + i * 0.45, "p": 1}
        for i, w in enumerate("Hoy aprendemos cómo funciona el editor de vídeo de Cutly paso a paso".split())
    ]
    segments = [
        {"id": 0, "start": 0.4, "end": words[-1]["end"], "text": " ".join(w["w"] for w in words), "words": words}
    ]
con = sqlite3.connect(D / "dev.db")
con.execute(
    "insert into transcript (id, media_id, language, segments, created_at) values (?,?,?,?,datetime('now'))",
    ("t_dev", mid, "es", json.dumps(segments)),
)
con.commit()
con.close()
key = api("POST", "/api-keys", {"name": "e2e", "can_write": True})["token"]
env = {**os.environ, "CUTLY_URL": base, "CUTLY_API_KEY": key}
r = subprocess.run(
    [sys.executable, str(REPO / "scripts/apps_linux/build.py"), mid], env=env, capture_output=True, text=True, cwd=D
)
if r.returncode:
    # sin el vídeo real, el guion de la edición no aplica: proyecto sencillo
    dur = api("GET", f"/media/{mid}")["duration"]
    pid = api(
        "POST", "/projects", {"media_id": mid, "source_in": 0, "source_out": min(dur, 30), "name": "Proyecto de prueba"}
    )["id"]
else:
    pid = (D / "project_id.txt").read_text()
state = {"base": base, "user": "test", "password": "testpass1234", "media_id": mid, "project_id": pid}
state_file.write_text(json.dumps(state))
print(json.dumps(state))
