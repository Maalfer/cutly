"""Herramientas del ANFITRIÓN: VBoxManage (que en Windows no está en el PATH) y Tesseract."""
import os
import shutil
import subprocess

from .config import die


def find_vboxmanage():
    """VBoxManage no está en el PATH en Windows. Orden: $VBOXMANAGE, PATH, rutas típicas de cada SO."""
    cands = [os.environ.get("VBOXMANAGE"), shutil.which("VBoxManage"), shutil.which("VBoxManage.exe")]
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        if os.environ.get(var):
            cands.append(os.path.join(os.environ[var], "Oracle", "VirtualBox", "VBoxManage.exe"))
    cands += ["/usr/local/bin/VBoxManage", "/Applications/VirtualBox.app/Contents/MacOS/VBoxManage",
              "/usr/bin/VBoxManage", "/usr/lib/virtualbox/VBoxManage"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    die("no encuentro VBoxManage: instala VirtualBox o define VBOXMANAGE=<ruta> (ver PORTABILIDAD.md §Windows)")


def find_tesseract():
    """Tesseract: PATH, o las rutas del instalador de Windows (para todos los usuarios o solo para el actual)."""
    cands = [shutil.which("tesseract")]
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            cands.append(os.path.join(base, "Tesseract-OCR", "tesseract.exe"))
    return next((c for c in cands if c and os.path.isfile(c)), None)


def vbox(*args, check=True):
    """VBoxManage con sus argumentos. check=True: si falla, sale con SU mensaje de error (no con una traza de Python)."""
    r = subprocess.run([find_vboxmanage(), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode:
        detalle = (r.stderr or r.stdout).strip().splitlines()
        die(f"VBoxManage {' '.join(str(a) for a in args[:3])} falló: " +
            " | ".join(l for l in detalle if l.strip())[:300])
    return r
