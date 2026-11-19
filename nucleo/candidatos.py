"""Fragmentos candidatos de un directo: lo que Claude propone para sacar clips (paso 3 de /directo-a-clips) y lo que
el usuario elige en la interfaz. Un fichero junto al directo:

    <directo>.candidatos.json
    {"directo": "directo4-completo.mp4",
     "fragmentos": [{"n": 1, "inicio": 479.0, "fin": 1420.0, "titulo": "Como-Explote-El-CVE-De-OpenSSH-En-Directo",
                     "tema": "explicación de la noticia/CVE + demo práctica completa, un solo tramo continuo",
                     "estrella": true, "elegido": false}]}

Claude lo escribe (y sigue enseñando la tabla en la sesión); la sección "Directo → clips" de cutly estudio lo muestra
con el directo al lado, el usuario marca "elegido" y se lo dice a Claude. Tiempos en segundos del directo original.
"""
import os

from nucleo import archivos

CAMPOS = ("n", "inicio", "fin", "titulo", "tema")


def ruta(directo):
    return os.path.splitext(directo)[0] + ".candidatos.json"


def validar(datos):
    """Lista de problemas (vacía = bien): campos que faltan, tiempos imposibles, números repetidos."""
    problemas = []
    vistos = set()
    for i, f in enumerate(datos.get("fragmentos", [])):
        faltan = [c for c in CAMPOS if c not in f]
        if faltan:
            problemas.append(f"fragmento {i + 1}: faltan {', '.join(faltan)}")
            continue
        if not (0 <= float(f["inicio"]) < float(f["fin"])):
            problemas.append(f"fragmento {f['n']}: inicio {f['inicio']} >= fin {f['fin']}")
        if f["n"] in vistos:
            problemas.append(f"fragmento {f['n']}: número repetido")
        vistos.add(f["n"])
    return problemas


def cargar(path):
    d = archivos.leer_json(path)
    d.setdefault("fragmentos", [])
    for f in d["fragmentos"]:
        f.setdefault("estrella", False)
        f.setdefault("elegido", False)
    return d


def guardar(path, datos):
    archivos.escribir_json(path, datos)


def hhmmss(seg):
    seg = int(round(float(seg)))
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"
