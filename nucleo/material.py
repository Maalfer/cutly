"""El MATERIAL de trabajo: lo que el usuario aporta (arrastrándolo a cutly estudio o copiándolo) vive en editor/crudo/
y se describe en editor/crudo/material.json, con el PAPEL de cada archivo. Así Claude sabe qué es cada cosa sin
depender de nombres fijos ("cara.mp4").

    {"material": [{"archivo": "cara.mp4", "rol": "cara", "rol_manual": false, "duracion": 202.3,
                   "ancho": 1080, "alto": 1920, "fps": 30.0, "audio": true, "tamano": 123456, "anadido": "..."}]}

Papeles (ROLES): cara · pantalla · short · toma · directo · grabacion · audio · imagen. Se deducen solos (inferir_rol),
pero lo normal es que los fije la interfaz: el usuario arrastra cada vídeo a la ranura de su papel ("Cara",
"Pantalla"...) y queda rol_manual: true (sincronizar ya no lo toca). Nadie coloca archivos en carpetas a mano.
Lo usan: editor/comun/material.py (CLI para Claude), estudio/paneles/material.py (la pestaña), las skills.
"""
import os
import shutil
from datetime import datetime

from nucleo import archivos, rutas

ROLES = {
    "cara": "vídeo vertical con tu cara y tu voz (se funde con la pantalla)",
    "pantalla": "Short mudo de pantalla con la banda negra arriba (de short_desde_toma.py)",
    "short": "Short montado con voz (para subtitular o verificar)",
    "toma": "grabación de la VM hecha por crear-shorts (tiene registro .steps.jsonl)",
    "directo": "directo o grabación larga 16:9 con voz (se corta en clips)",
    "grabacion": "otra grabación horizontal",
    "audio": "solo audio",
    "imagen": "imagen fija",
}
VIDEO = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
AUDIO = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")
IMAGEN = (".png", ".jpg", ".jpeg", ".webp")
DIRECTO_MIN_S = 15 * 60          # una grabación horizontal con voz de más de 15 min se trata como directo
SILENCIO_DB = -60                # pico por debajo de esto = pista de audio muda (el Short de pantalla lleva una)


def carpeta():
    return rutas.CRUDO               # se lee al llamar (CUTLY_CRUDO / pruebas pueden cambiarla)


def manifiesto():
    return os.path.join(carpeta(), "material.json")


def es_medio(nombre):
    n = nombre.lower()
    return n.endswith(VIDEO + AUDIO + IMAGEN) and not n.startswith("_vbox_rec")


def describir(path):
    """Propiedades medidas con ffprobe (o lo mínimo, para imágenes y si ffprobe falla)."""
    d = {"tamano": os.path.getsize(path)}
    if path.lower().endswith(IMAGEN):
        return d
    try:
        from nucleo import medios
        i = medios.info(path)
    except Exception:
        return d
    v = next((s for s in i.get("streams", []) if s.get("codec_type") == "video"), None)
    d["pista_audio"] = any(s.get("codec_type") == "audio" for s in i.get("streams", []))
    # "audio" = que SUENE: el Short de pantalla trae una pista muda y no por eso es la cara (medido)
    d["audio"] = d["pista_audio"] and pico_db(path) > SILENCIO_DB
    d["duracion"] = round(float(i.get("format", {}).get("duration", 0) or 0), 2)
    if v:
        d["ancho"], d["alto"] = v.get("width"), v.get("height")
        num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
        d["fps"] = round(float(num) / float(den or 1), 2) if float(den or 1) else 0
    return d


def pico_db(path, segundos=120):
    """Pico de volumen (dB) de los primeros `segundos` (volumedetect de ffmpeg); -inf si no se puede medir."""
    import re
    import subprocess
    from nucleo.ffmpeg import requerir
    r = subprocess.run([requerir("ffmpeg"), "-v", "info", "-t", str(segundos), "-i", path, "-vn", "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", r.stderr)
    return float(m.group(1)) if m and m.group(1) != "-inf" else float("-inf")


def inferir_rol(nombre, d, hay_registro=False):
    """El papel más probable de un archivo a partir de sus propiedades."""
    n = nombre.lower()
    if n.endswith(IMAGEN):
        return "imagen"
    if n.endswith(AUDIO) or ("ancho" not in d and d.get("audio")):
        return "audio"
    if hay_registro:
        return "toma"
    ancho, alto = d.get("ancho") or 0, d.get("alto") or 0
    if alto > ancho:                                  # vertical
        if not d.get("audio"):
            return "pantalla"
        # con voz: un Short ya montado (corto, 60 fps, se llama short_...) o la grabación de la cara
        return "short" if n.startswith("short_") or (d.get("duracion", 0) <= 95 and d.get("fps") == 60) else "cara"
    if d.get("audio") and d.get("duracion", 0) >= DIRECTO_MIN_S:
        return "directo"
    return "grabacion"


def cargar():
    try:
        return archivos.leer_json(manifiesto())
    except (OSError, ValueError):
        return {"material": []}


def guardar(m):
    os.makedirs(carpeta(), exist_ok=True)
    m["material"].sort(key=lambda e: e.get("anadido", ""), reverse=True)
    archivos.escribir_json(manifiesto(), m)


def sincronizar():
    """Pone el manifiesto al día con lo que HAY en la carpeta: añade lo nuevo (rol deducido), quita lo que ya no está,
    re-mide lo que cambió y respeta los roles fijados a mano. Devuelve el manifiesto."""
    m = cargar()
    previos = {e["archivo"]: e for e in m["material"]}
    out = []
    if os.path.isdir(carpeta()):
        for nombre in sorted(os.listdir(carpeta())):
            ruta = os.path.join(carpeta(), nombre)
            if not (os.path.isfile(ruta) and es_medio(nombre)):
                continue
            e = previos.get(nombre)
            if e is None or e.get("tamano") != os.path.getsize(ruta):
                d = describir(ruta)
                registro = os.path.exists(os.path.splitext(ruta)[0] + ".steps.jsonl")
                nuevo = {"archivo": nombre, **d,
                         "anadido": (e or {}).get("anadido") or datetime.now().isoformat(timespec="seconds")}
                if e and e.get("rol_manual"):
                    nuevo.update(rol=e["rol"], rol_manual=True)
                else:
                    nuevo.update(rol=inferir_rol(nombre, d, registro), rol_manual=False)
                e = nuevo
            out.append(e)
    m["material"] = out
    guardar(m)
    return m


def fijar_rol(archivo, rol):
    if rol not in ROLES:
        raise ValueError(f"rol desconocido: {rol} (hay: {', '.join(ROLES)})")
    m = sincronizar()
    for e in m["material"]:
        if e["archivo"] == os.path.basename(archivo):
            e.update(rol=rol, rol_manual=True, asignado=datetime.now().isoformat(timespec="seconds"))
            guardar(m)
            return e
    raise FileNotFoundError(f"{archivo} no está en el material")


def nombre_libre(nombre):
    """Un nombre que no pise nada en la carpeta: x.mp4, x-2.mp4, x-3.mp4..."""
    base, ext = os.path.splitext(nombre)
    candidato, n = nombre, 2
    while os.path.exists(os.path.join(carpeta(), candidato)):
        candidato, n = f"{base}-{n}{ext}", n + 1
    return candidato


def anadir(origen, modo="auto"):
    """Trae un archivo al material. modo: "auto" (enlace duro si está en el mismo disco: instantáneo y sin ocupar
    espacio; si no, copia), "copiar" o "mover". Devuelve la ruta en editor/crudo/."""
    origen = os.path.abspath(origen)
    if not os.path.isfile(origen):
        raise FileNotFoundError(origen)
    if os.path.dirname(origen) == os.path.abspath(carpeta()):
        return origen                                  # ya está en el material
    os.makedirs(carpeta(), exist_ok=True)
    destino = os.path.join(carpeta(), nombre_libre(os.path.basename(origen)))
    if modo == "mover":
        shutil.move(origen, destino)
    elif modo == "copiar":
        shutil.copy2(origen, destino)
    else:
        try:
            os.link(origen, destino)                   # mismo volumen: el mismo fichero con dos nombres
        except OSError:
            shutil.copy2(origen, destino)
    return destino


def por_rol(rol, m=None):
    """Rutas del material con ese papel, primero la última asignada (lo último que se soltó en su ranura)."""
    m = m or sincronizar()
    es = sorted((e for e in m["material"] if e["rol"] == rol),
                key=lambda e: max(e.get("asignado", ""), e.get("anadido", "")), reverse=True)
    return [os.path.join(carpeta(), e["archivo"]) for e in es]


def tabla(m=None):
    """Inventario legible (lo que imprime la CLI para Claude)."""
    m = m or sincronizar()
    if not m["material"]:
        return f"(no hay material en {carpeta()})"
    filas = []
    for e in m["material"]:
        res = f"{e['ancho']}x{e['alto']}" if e.get("ancho") else "-"
        dur = f"{e['duracion']:.1f}s" if e.get("duracion") else "-"
        audio = "con audio" if e.get("audio") else ("mudo" if "audio" in e else "-")
        fija = " (fijado)" if e.get("rol_manual") else ""
        filas.append(f"{e['rol'] + fija:<20} {e['archivo']:<48} {dur:>9}  {res:>10}  {e.get('fps', '-')!s:>6} fps  {audio}")
    return "\n".join(filas)
