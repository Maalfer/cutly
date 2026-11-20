"""Configuración de la VM (variables de entorno) y la salida de error común.

VM_NAME (kali) · VM_KEY (~/.ssh/cutly_vm) · VM_HOST (127.0.0.1, el reenvío NAT; con la VM en modo puente,
pon la IP real del invitado en tu LAN) · VM_SSH_PORT (2222; con VM_HOST puesto a la IP real, normalmente 22) ·
VM_USER (kali) · VBOXMANAGE (ruta) ·
VM_OCR=tesseract (fuerza Tesseract) · VM_CANAL=auto|ssh|guestcontrol (canal con el invitado, vm/canales/) ·
VM_GUEST_PASSFILE / VM_GUEST_PASS (solo si los das tú: bootstrap y canal guestcontrol; nunca se adivinan)
"""
import os
import sys
import tempfile

VM = os.environ.get("VM_NAME", "kali")
KEY = os.environ.get("VM_KEY", os.path.expanduser("~/.ssh/cutly_vm"))
HOST = os.environ.get("VM_HOST", "127.0.0.1")
PORT = os.environ.get("VM_SSH_PORT", "2222")
USER = os.environ.get("VM_USER", "kali")
TMP = tempfile.gettempdir()
STATE_FILE = os.path.join(TMP, "cutly_take.json")   # toma abierta (nombre, registro, inicio de la grabación)
IS_WIN = os.name == "nt"


def die(msg):
    sys.exit(f"[vm_control] {msg}")


def contrasena_invitado():
    """La contraseña del invitado SI el usuario la ha dado (VM_GUEST_PASSFILE, preferido, o VM_GUEST_PASS); si no,
    None. Nunca se adivina ni se guarda en el repo."""
    pf = os.environ.get("VM_GUEST_PASSFILE")
    if pf:
        with open(pf, encoding="utf-8") as f:
            return f.read().rstrip("\r\n")
    return os.environ.get("VM_GUEST_PASS") or None
