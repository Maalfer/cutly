#!/usr/bin/env python3
"""
material.py — El material de trabajo (editor/crudo/) y el papel de cada archivo, para Claude y para el usuario.
Contrato y lógica: nucleo/material.py (manifiesto editor/crudo/material.json).

    python editor/comun/material.py                    # inventario: papel, archivo, duración, resolución, fps, audio
    python editor/comun/material.py rol ARCHIVO ROL    # fija el papel (cara, pantalla, toma, directo, grabacion...)
    python editor/comun/material.py ruta ROL           # rutas con ese papel (p. ej. la cara y la pantalla a fundir)
    python editor/comun/material.py anadir RUTA [--copiar | --mover]   # trae un archivo al material

El usuario suele aportar el material soltándolo en las secciones de cutly estudio, que escribe lo mismo.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import material  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Material de trabajo (editor/crudo/) y su papel")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("rol", help="fija el papel de un archivo")
    r.add_argument("archivo")
    r.add_argument("rol", choices=list(material.ROLES))
    q = sub.add_parser("ruta", help="rutas con un papel")
    q.add_argument("rol", choices=list(material.ROLES))
    a = sub.add_parser("anadir", help="trae un archivo al material")
    a.add_argument("ruta")
    g = a.add_mutually_exclusive_group()
    g.add_argument("--copiar", action="store_true")
    g.add_argument("--mover", action="store_true")
    args = ap.parse_args()

    if args.cmd == "rol":
        e = material.fijar_rol(args.archivo, args.rol)
        print(f"{e['archivo']}: {e['rol']}")
    elif args.cmd == "ruta":
        print("\n".join(material.por_rol(args.rol)))
    elif args.cmd == "anadir":
        destino = material.anadir(args.ruta, "copiar" if args.copiar else "mover" if args.mover else "auto")
        material.sincronizar()
        print(destino)
    else:
        print(f"Material en {material.carpeta()}  (papeles: {', '.join(material.ROLES)})\n")
        print(material.tabla())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
