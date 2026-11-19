"""Configuración de la VM (variables de entorno) y la salida de error común.

VM_NAME (kali) · VM_KEY (~/.ssh/cutly_vm) · VM_SSH_PORT (2222) · VM_USER (kali) · VBOXMANAGE (ruta) ·
VM_OCR=tesseract (fuerza Tesseract) · VM_GUEST_PASS (solo si la das tú, para bootstrap con guestcontrol)
"""
import os
import sys
import tempfile

VM = os.environ.get("VM_NAME", "kali")
KEY = os.environ.get("VM_KEY", os.path.expanduser("~/.ssh/cutly_vm"))
PORT = os.environ.get("VM_SSH_PORT", "2222")
USER = os.environ.get("VM_USER", "kali")
TMP = tempfile.gettempdir()
STATE_FILE = os.path.join(TMP, "cutly_take.json")   # toma abierta (nombre, registro, inicio de la grabación)
IS_WIN = os.name == "nt"


def die(msg):
    sys.exit(f"[vm_control] {msg}")
