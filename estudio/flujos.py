"""Los flujos de trabajo de la app SON las skills del proyecto (.claude/skills/<nombre>/SKILL.md): cada una es un botón
que escribe /<nombre> en la sesión de Claude Code. Una skill nueva = un botón nuevo, sin tocar la app."""
import glob
import os
import re

from .entorno import REPO

SKILLS = os.path.join(REPO, ".claude", "skills")
# orden y rótulo cortos de los conocidos (los demás van detrás con su nombre)
ROTULOS = {
    "preparar-vm": "Preparar VM",
    "grabar-demo": "Grabar demo",
    "fusionar-cara-pantalla": "Fusionar cara + pantalla",
    "short-desde-grabacion": "Grabación → Short",
    "subtitular-short": "Subtitular Short",
    "directo-a-clips": "Directo → clips",
}


def leer_skill(ruta):
    """(nombre, descripción, pista de argumentos) del frontmatter de un SKILL.md."""
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    m = re.match(r"^---\n(.*?)\n---", texto, re.S)
    campos = dict(re.findall(r"^([\w-]+):\s*(.*)$", m.group(1), re.M)) if m else {}
    nombre = campos.get("name") or os.path.basename(os.path.dirname(ruta))
    return nombre, campos.get("description", "").strip('"'), campos.get("argument-hint", "").strip('"')


def flujos():
    """[{nombre, rotulo, descripcion, argumentos, comando}] en el orden de ROTULOS y luego alfabético."""
    out = []
    for ruta in glob.glob(os.path.join(SKILLS, "*", "SKILL.md")):
        nombre, desc, args = leer_skill(ruta)
        out.append({"nombre": nombre, "rotulo": ROTULOS.get(nombre, nombre), "descripcion": desc, "argumentos": args,
                    "comando": "/" + nombre})
    orden = list(ROTULOS)
    return sorted(out, key=lambda f: (orden.index(f["nombre"]) if f["nombre"] in orden else len(orden), f["nombre"]))
