"""Ejemplo completo de edición profesional vía API: «apps linux.mp4» (tutorial apt/flatpak, 94 s, 9:16).

Uso: CUTLY_URL=https://editor.cogny.es CUTLY_API_KEY=ct_... python3 build.py [media_id]
Lee la transcripción, calcula los tiempos a partir de las palabras y crea el proyecto con un solo lote de operaciones.
Es una plantilla: adapta coordenadas (cara 0–0.40, comandos ≈0.55) y textos a cada vídeo.
"""
import json, os, re, sys, urllib.error, urllib.request

U = os.environ["CUTLY_URL"].rstrip("/")
KEY = os.environ["CUTLY_API_KEY"]
M = sys.argv[1] if len(sys.argv) > 1 else "m_ad7487db158d4304"


def web(method, path, data=None, raw=False):
    h = {"Authorization": f"Bearer {KEY}"}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(U + "/api/v1" + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=h)
    try:
        body = urllib.request.urlopen(req, timeout=300).read()
        return body if raw else json.loads(body)
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read()[:600].decode()); raise


media = web("GET", f"/media/{M}")
DUR = media["duration"]
segs = web("GET", f"/media/{M}/transcript")["segments"]
words = [(w["start"], w["end"], re.sub(r"[^\wáéíóúñü]", "", w["w"].lower())) for s in segs for w in s["words"]]
toks = [w[2] for w in words]


def ph(phrase, n=0):
    """(inicio, fin) de la n-ésima aparición de una secuencia de palabras en el vídeo."""
    p = phrase.lower().split()
    hits = [i for i in range(len(toks) - len(p) + 1) if toks[i:i + len(p)] == p]
    if len(hits) <= n:
        raise SystemExit(f"no encuentro «{phrase}» (apariciones: {len(hits)})")
    i = hits[n]
    return words[i][0], words[i + len(p) - 1][1]


def seg(i):
    return segs[i]["start"], segs[i]["end"]


YEL, WHITE, BLACK = "#FFD400", "#FFFFFF", "#000000"
BLUE, ORANGE, RED, GREEN, PURPLE = "#0A84FF", "#FF9F0A", "#FF3B30", "#34C759", "#AF52DE"
L = []  # ops


def add(layer):
    L.append({"op": "add_layer", "layer": layer})


def text(t0, t1, txt, box, style, anim=None, z=20, name=None):
    layer = {"type": "text", "start": round(t0, 2), "end": round(t1, 2), "text": txt, "box": box, "style": style, "z": z}
    if anim: layer["animations"] = anim
    if name: layer["name"] = name
    add(layer)


def chip(t0, t1, txt, color, name):
    text(t0, t1, txt, {"x": 0.965, "y": 0.03, "w": 0.62, "anchor": "top_right"},
         {"font": "Poppins ExtraBold", "size": 0.027, "color": WHITE, "bg_color": color + "E8", "bold": False, "uppercase": True, "outline_width": 0},
         {"enter": {"name": "slide_left", "dur": 0.3}, "exit": {"name": "slide_left", "dur": 0.25}}, name=name)


def box(t0, t1, x, y, w, h, color, name):
    add({"type": "shape", "shape": "rect", "start": round(t0, 2), "end": round(t1, 2), "z": 8, "name": name,
         "fill": color + "26", "stroke": color, "stroke_width": 0.0035, "box": {"x": x, "y": y, "w": w, "h": h},
         "animations": {"enter": {"name": "pop", "dur": 0.28}, "exit": {"name": "fade", "dur": 0.2}, "loop": {"name": "pulse", "period": 1.1, "amount": 0.012}}})


def icon(t0, t1, asset, x, y, w, name, rot=0, loop="pulse"):
    add({"type": "icon", "asset": asset, "start": round(t0, 2), "end": round(t1, 2), "z": 22, "name": name,
         "box": {"x": x, "y": y, "w": w, "rotation": rot},
         "animations": {"enter": {"name": "pop", "dur": 0.35}, "exit": {"name": "fade", "dur": 0.25}, "loop": {"name": loop, "period": 0.9, "amount": 0.07}}})


def fx(t0, t1, effect, params=None, region=None, z=0, name=None):
    layer = {"type": "effect", "effect": effect, "start": round(t0, 2), "end": round(t1, 2), "params": params or {}, "z": z}
    if region: layer["region"] = region
    if name: layer["name"] = name
    add(layer)


FACE = {"x": 0, "y": 0, "w": 1, "h": 0.40}

# --- 1) título de apertura -----------------------------------------------------------------------------------------
text(0.15, 3.7, "CÓMO INSTALAR APPS EN LINUX", {"x": 0.5, "y": 0.047, "w": 0.94},
     {"font": "Anton", "size": 0.047, "color": YEL, "bg_color": "#000000C4", "bold": False, "uppercase": True, "outline_width": 0},
     {"enter": {"name": "pop", "dur": 0.35}, "exit": {"name": "fade", "dur": 0.3}}, z=24, name="título")

# --- 2) rótulos de concepto (arriba a la derecha) ------------------------------------------------------------------------
a0 = ph("por apt")[0] - 0.1
chip(a0, ph("yo por ejemplo")[0], "APT", BLUE, "chip apt")
t_ns = ph("que esto no siempre va a funcionar")
chip(t_ns[0], seg(4)[1], "¡No siempre funciona!", RED, "chip no siempre")
icon(t_ns[0] + 0.15, seg(4)[1], "icons/exclamation", 0.905, 0.125, 0.10, "icono alerta")
chip(seg(6)[0], seg(6)[1], "FLATPAK", ORANGE, "chip flatpak")
t_ok = ph("ya lo tenemos instalado")
chip(t_ok[0], seg(9)[1], "¡Instalado!", GREEN, "chip instalado")
icon(t_ok[0] + 0.2, seg(9)[1] - 0.6, "icons/check", 0.905, 0.125, 0.10, "icono check", loop="float")
chip(seg(10)[0], seg(10)[1], "Listar apps", ORANGE, "chip listar")
chip(seg(11)[0], seg(11)[1], "Eliminar apps", PURPLE, "chip eliminar")
chip(seg(12)[0], seg(12)[1], "apt remove", BLUE, "chip apt remove")
chip(seg(13)[0], seg(14)[1], "apt autoremove", BLUE, "chip autoremove")

# --- 3) resaltes sobre la línea de comandos de la terminal -------------------------------------------------------------------
Y = 0.55
c1 = ph("apt install audacity");              box(c1[0] - 0.15, c1[1] + 0.5, 0.395, Y, 0.75, 0.046, YEL, "resalte apt install audacity")
c2 = ph("sudo apt install");                  box(c2[0] - 0.1, c2[1] + 0.9, 0.41, Y, 0.78, 0.046, YEL, "resalte sudo apt install")
e0 = ph("no me va a funcionar")[0];           box(e0 - 0.4, seg(5)[1] - 0.2, 0.5, 0.574, 0.99, 0.040, RED, "resalte error")
c4 = ph("flatpak install");                   box(c4[0] - 0.1, c4[1] + 1.4, 0.41, 0.66, 0.78, 0.046, YEL, "resalte flatpak install")
c5 = ph("flatpak list");                      box(c5[0] - 0.1, c5[1] + 0.9, 0.32, Y, 0.60, 0.046, YEL, "resalte flatpak list")
c6 = ph("flatpak uninstall chrome");          box(c6[0] - 0.1, c6[1] + 1.0, 0.46, Y, 0.88, 0.046, YEL, "resalte flatpak uninstall")
c7 = ph("sudo apt remove audacity");          box(c7[0] - 0.1, c7[1] + 1.2, 0.435, Y, 0.83, 0.046, YEL, "resalte apt remove")
c8 = ph("sudo apt autoremove");               box(c8[0] - 0.1, c8[1] + 1.2, 0.46, Y, 0.88, 0.046, YEL, "resalte apt autoremove")

# --- 4) efectos ---------------------------------------------------------------------------------------------------------------
punch = [0.05, ph("por apt")[0], seg(4)[0], ph("flatpak")[0], ph("y listo")[0], seg(11)[0], seg(16)[0]]
for k, t in enumerate(punch):
    fx(t, t + 0.75, "zoom_punch", {"scale": 1.10, "focus_x": 0.5, "focus_y": 0.30, "attack": 0.12, "release": 0.45}, FACE, name=f"punch {k + 1}")
for t in (seg(6)[0], seg(11)[0], seg(16)[0]):
    fx(t, t + 0.28, "flash", {"color": "white", "strength": 0.28}, None, name="destello")
g = ph("ciberseguridad")
fx(g[0], g[1] + 0.2, "glitch", {"intensity": 9, "rate": 16}, FACE, name="glitch ciberseguridad")
fx(0, DUR, "progress_bar", {"position": "bottom", "thickness": 0.006, "color": YEL, "opacity": 0.9}, None, z=30, name="progreso")

# --- 5) llamada a la acción final ----------------------------------------------------------------------------------------------
cta = seg(16)[0] + 0.25
text(cta, DUR, "COMENTA\n«LINUX»", {"x": 0.5, "y": 0.62, "w": 0.8},
     {"font": "Anton", "size": 0.078, "color": YEL, "bg_color": "#000000D0", "bold": False, "uppercase": True, "outline_width": 0},
     {"enter": {"name": "pop", "dur": 0.4}, "exit": {"name": "fade", "dur": 0.3}, "loop": {"name": "pulse", "period": 1.2, "amount": 0.03}},
     z=26, name="CTA comenta")
icon(cta + 0.7, DUR, "icons/arrow-right", 0.5, 0.775, 0.13, "flecha CTA", rot=90, loop="float")
gp = ph("al privado")
text(gp[0] - 0.4, DUR, "GUÍA AL PRIVADO", {"x": 0.5, "y": 0.875, "w": 0.8},
     {"font": "Poppins ExtraBold", "size": 0.03, "color": WHITE, "bg_color": GREEN + "F0", "bold": False, "uppercase": True, "outline_width": 0},
     {"enter": {"name": "pop", "dur": 0.35}, "exit": {"name": "fade", "dur": 0.2}}, z=26, name="CTA guía")

# --- 6) proyecto: crear y aplicar --------------------------------------------------------------------------------------------------
p = web("POST", "/projects", {"media_id": M, "source_in": 0, "source_out": round(DUR, 3), "name": "Instalar apps en Linux (reel)"})
pid = p["id"]
sub_id = [l["id"] for l in p["project"]["layers"] if l["type"] == "subtitle"][0]
head = [
    {"op": "update_layer", "layer_id": sub_id, "patch": {"name": "subtítulos", "style": {"font": "Poppins", "size": 0.043, "color": WHITE, "outline_color": BLACK, "outline_width": 0.007,
        "highlight_color": YEL, "position_y": 0.425, "max_words_per_cue": 3, "max_lines": 2, "animation": "pop", "bold": True}}},
    {"op": "set_color", "patch": {"saturation": 1.06, "contrast": 1.04}},
]
r = web("POST", f"/projects/{pid}/ops", {"ops": head + L, "label": "montaje completo"})
print("proyecto", pid, "versión", r["version"], "capas", len(r["project"]["layers"]), "duración", r["duration"])
print("avisos:", r["warnings"])
open("project_id.txt", "w").write(pid)
