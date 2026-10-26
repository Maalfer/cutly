"""Renderiza el proyecto de project_id.txt y descarga el MP4: python3 render.py draft|final"""
import json, os, sys, time, urllib.request
U = os.environ["CUTLY_URL"].rstrip("/"); KEY = os.environ["CUTLY_API_KEY"]; q = sys.argv[1]
def web(m, p, d=None, raw=False):
    h = {"Authorization": f"Bearer {KEY}"}
    if d is not None:
        h["Content-Type"] = "application/json"
    r = urllib.request.urlopen(urllib.request.Request(U + "/api/v1" + p, data=json.dumps(d).encode() if d is not None else None, method=m, headers=h), timeout=600).read()
    return r if raw else json.loads(r)
pid = open("project_id.txt").read()
jid = web("POST", f"/projects/{pid}/render", {"quality": q})["job_id"]
t0 = time.time(); last = -1
while True:
    j = web("GET", f"/jobs/{jid}")
    if int(j["progress"] * 10) != last: last = int(j["progress"] * 10); print(f"  {j['status']} {j['progress']:.0%} ({time.time() - t0:.0f}s)", flush=True)
    if j["status"] in ("done", "failed", "cancelled"): break
    time.sleep(5)
print(j["status"], j.get("error"), {k: j["result"][k] for k in ("width", "height", "size", "duration", "warnings")} if j.get("result") else "")
if j["status"] == "done":
    open(f"out_{q}.mp4", "wb").write(web("GET", f"/renders/{jid}/download", raw=True))
