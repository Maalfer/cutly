#!/usr/bin/env python3
"""
lab_idor.py — Laboratorio local MÍNIMO y vulnerable a propósito, para grabar la demo de IDOR.

SOLO escucha en 127.0.0.1:8765 (nada sale del ordenador). Usuarios ficticios.
  /cuenta?id=1001  -> "Cuenta de usuarioA"
  /cuenta?id=1002  -> "Cuenta de usuarioB"      (el fallo: no comprueba de quién es la sesión)
  /                -> página con un <input> (sirve para probar el tecleo en un formulario)

Uso:   python3 crear-shorts/DEMO-IDOR/lab_idor.py &      ...   pkill -f lab_idor.py   (al terminar)
Cómo se usa en la demo: ver ejemplo-idor-con-burp.md.
"""
import http.server, urllib.parse
USERS={"1001":("usuarioA","a@lab.local"),"1002":("usuarioB","b@lab.local")}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        if u.path=="/cuenta":
            n,m=USERS.get(q.get("id",[""])[0],("desconocido","-"))
            body=f"<html><body style='font:28px sans-serif'><h1>Cuenta de {n}</h1><p>correo: {m}</p></body></html>"
        else:
            body="<html><body style='font:28px sans-serif'><h1>Lab IDOR</h1><form><input id=q name=q size=40 autofocus placeholder='escribe aqui'></form></body></html>"
        b=body.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
http.server.ThreadingHTTPServer(("127.0.0.1",8765),H).serve_forever()
