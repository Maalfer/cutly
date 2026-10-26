#!/usr/bin/env python3
"""Sube un vídeo grande a Cutly por trozos, con reanudación. Solo biblioteca estándar.

Uso:
  export CUTLY_URL=https://editor.cogny.es
  export CUTLY_API_KEY=ct_...        # clave con permiso de escritura
  python3 upload.py directo.mkv [--wait]

Si se corta, vuelve a lanzar el mismo comando: continúa por el último trozo recibido.
Con --wait espera a que terminen los jobs de proxy y forma de onda.
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = os.environ.get("CUTLY_URL", "").rstrip("/")
KEY = os.environ.get("CUTLY_API_KEY", "")
STATE = Path.home() / ".cache" / "cutly-uploads.json"


def call(method, path, body=None, json_body=None):
    headers = {"Authorization": f"Bearer {KEY}"}
    data = body
    if json_body is not None:
        data, headers["Content-Type"] = json.dumps(json_body).encode(), "application/json"
    req = urllib.request.Request(f"{URL}/api/v1{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"null")


def die(msg):
    sys.exit(f"ERROR: {msg}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not URL or not KEY or len(args) != 1:
        die("define CUTLY_URL y CUTLY_API_KEY y pasa un archivo: python3 upload.py video.mp4 [--wait]")
    path = Path(args[0]).expanduser().resolve()
    if not path.is_file():
        die(f"no existe {path}")
    size, st = path.stat().st_size, path.stat()
    key = f"{path}:{size}:{int(st.st_mtime)}"
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    up = None
    if key in state:
        try:
            up = call("GET", f"/uploads/{state[key]}")
            if up["status"] != "uploading":
                up = None
        except urllib.error.HTTPError:
            up = None
    if up is None:
        up = call("POST", "/uploads", json_body={"filename": path.name, "size": size, "chunk_size": 8 * 1024 * 1024})
        STATE.parent.mkdir(parents=True, exist_ok=True)
        state[key] = up["upload_id"]
        STATE.write_text(json.dumps(state))
    uid, cs, total = up["upload_id"], up["chunk_size"], up["total_chunks"]
    pending = [n for n in range(total) if n not in set(up["received"])]
    print(f"{path.name}: {size / 1e9:.2f} GB en {total} trozos; faltan {len(pending)}", flush=True)
    done, last_pct = total - len(pending), -1

    def send(n):
        with open(path, "rb") as f:
            f.seek(n * cs)
            blob = f.read(cs)
        h = {"Authorization": f"Bearer {KEY}", "X-Chunk-SHA256": hashlib.sha256(blob).hexdigest()}
        for attempt in range(6):
            try:
                req = urllib.request.Request(f"{URL}/api/v1/uploads/{uid}/chunks/{n}", data=blob, method="PUT", headers=h)
                urllib.request.urlopen(req, timeout=120).read()
                return n
            except Exception as e:  # noqa: BLE001
                if attempt == 5:
                    raise
                time.sleep(2**attempt)
                print(f"  reintento trozo {n}: {e}", flush=True)

    with ThreadPoolExecutor(3) as ex:
        for _ in ex.map(send, pending):
            done += 1
            pct = done * 100 // total
            if pct != last_pct and pct % 5 == 0:
                print(f"  {pct} %", flush=True)
                last_pct = pct
    res = call("POST", f"/uploads/{uid}/complete")
    state.pop(key, None)
    STATE.write_text(json.dumps(state))
    print(json.dumps(res), flush=True)
    if "--wait" in sys.argv:
        while True:
            jobs = [call("GET", f"/jobs/{j}") for j in res["jobs"]]
            print("  " + ", ".join(f"{j['type']}={j['status']} {j['progress']:.0%}" for j in jobs), flush=True)
            if all(j["status"] in ("done", "failed", "cancelled") for j in jobs):
                break
            time.sleep(10)


if __name__ == "__main__":
    main()
