"""Utilidades de las pruebas: rutas del repo e importación de scripts sueltos (no son paquetes) por su ruta."""
import importlib.util
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HERRAMIENTAS = os.path.join(REPO, "crear-shorts", "herramientas")
for p in (REPO, HERRAMIENTAS):
    if p not in sys.path:
        sys.path.insert(0, p)


def cargar(ruta_relativa):
    """Importa un script del repo (p. ej. 'editor/shorts/fusionar_cara_pantalla.py') como módulo."""
    ruta = os.path.join(REPO, ruta_relativa)
    nombre = "script_" + os.path.splitext(os.path.basename(ruta))[0]
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
