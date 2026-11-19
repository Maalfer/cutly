"""Canales con el invitado, intercambiables. Todos cumplen la interfaz de base.Canal:

    disponible()                   ¿responde el invitado por aquí?
    ejecutar(script, timeout)      bash en el invitado (DISPLAY=:0, locale UTF-8) -> (código, stdout, stderr)
    traer(remoto, local)           fichero invitado -> anfitrión
    enviar(local, remoto)          fichero anfitrión -> invitado

    ssh           SSH + scp por la regla NAT (el de siempre; necesita `vm_control.py bootstrap`)
    guestcontrol  VBoxManage guestcontrol por las Guest Additions (sin SSH; necesita la contraseña que dé el usuario)

Se elige con VM_CANAL=ssh|guestcontrol|auto (defecto auto: ssh si responde; si no, guestcontrol si hay credenciales).
Un canal nuevo (p. ej. la API de VirtualBox): una clase que herede de base.Canal + una entrada en CANALES.
"""
from .base import Canal, CanalTimeout  # noqa: F401
from .guestcontrol import CanalGuestControl
from .ssh import CanalSSH

CANALES = {"ssh": CanalSSH, "guestcontrol": CanalGuestControl}
ORDEN_AUTO = ("ssh", "guestcontrol")       # preferencia en modo auto: el más rápido y medido primero

__all__ = ["Canal", "CanalTimeout", "CanalSSH", "CanalGuestControl", "CANALES", "ORDEN_AUTO"]
