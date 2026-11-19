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
    c = shutil.which("tesseract") or os.path.join(os.environ.get("ProgramFiles", ""), "Tesseract-OCR", "tesseract.exe")
    return c if c and os.path.isfile(c) else None


def vbox(*args, check=True):
    return subprocess.run([find_vboxmanage(), *args], capture_output=True, text=True, check=check)
