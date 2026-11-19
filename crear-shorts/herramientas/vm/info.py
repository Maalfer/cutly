"""Lo que VirtualBox sabe de la VM SIN credenciales ni SSH: estado, configuración, Guest Additions, si hay una sesión
iniciada, la IP y la resolución real del invitado. Sirve para saber en qué punto está la VM antes de intentar
controlarla (y para explicar qué falta en vez de esperar a ciegas).

Fuentes, todas de VBoxManage:
    showvminfo --machinereadable     estado, Guest Additions (versión y nivel), regla NAT, grabación
    guestproperty enumerate          lo que publican las Guest Additions: usuarios con sesión, IP, versión
    getextradata                     GUI/LastGuestSizeHint: última resolución del invitado (sirve con la VM apagada)
    controlvm screenshotpng          la resolución REAL ahora (se lee de la cabecera del PNG, sin Pillow)
"""
import os
import re
import struct

from .anfitrion import vbox
from .config import TMP, VM

# Usuarios de la pantalla de inicio de sesión (no son una sesión del usuario)
GESTORES_DE_LOGIN = {"lightdm", "gdm", "gdm3", "Debian-gdm", "sddm"}

# Nivel de las Guest Additions (showvminfo GuestAdditionsRunLevel)
NIVELES = {0: "sin Guest Additions", 1: "sistema", 2: "servicios de usuario", 3: "escritorio con sesión"}


def existe(nombre=VM):
    return any(re.match(rf'^"{re.escape(nombre)}" ', l) for l in vbox("list", "vms", check=False).stdout.splitlines())


def vms():
    return re.findall(r'^"(.+)" \{', vbox("list", "vms", check=False).stdout, re.M)


def parsear_maquina(texto):
    """showvminfo --machinereadable -> dict (clave -> valor sin comillas)."""
    d = {}
    for l in texto.splitlines():
        if "=" in l:
            k, v = l.split("=", 1)
            d[k.strip('"')] = v.strip().strip('"').replace("\\\\", "\\")   # las rutas vienen con \ escapadas
    return d


def maquina():
    return parsear_maquina(vbox("showvminfo", VM, "--machinereadable", check=False).stdout)


def parsear_propiedades(texto):
    """guestproperty enumerate -> dict (nombre -> valor). Formato: /ruta = 'valor'  @ fecha [flags]."""
    d = {}
    for l in texto.splitlines():
        m = re.match(r"^\s*(\S+)\s*=\s*'(.*?)'\s*(@|$)", l)
        if m:
            d[m.group(1)] = m.group(2)
    return d


def propiedades():
    return parsear_propiedades(vbox("guestproperty", "enumerate", VM, check=False).stdout)


def resumen(m=None, p=None):
    """Estado de un vistazo: dict con estado, adiciones (versión/nivel), sesion (usuarios), ip, natpf, grabacion."""
    m = m if m is not None else maquina()
    p = p if p is not None else (propiedades() if m.get("VMState") == "running" else {})
    nivel = int(m.get("GuestAdditionsRunLevel", "0") or 0)
    lista = p.get("/VirtualBox/GuestInfo/OS/LoggedInUsersList")
    # la pantalla de login también cuenta como "usuario conectado" (medido: 'lightdm'): no es una sesión del usuario
    personas = [u for u in (lista or "").replace(" ", ",").split(",") if u and u not in GESTORES_DE_LOGIN]
    return {
        "estado": m.get("VMState", "desconocido"),
        "nivel_adiciones": nivel,
        # la versión del SERVICIO (propiedad) es la buena: showvminfo da la del driver, que en las Guest Additions
        # empaquetadas por Debian/Kali dice "6.0.0" aunque sean 7.2.x (medido)
        "version_adiciones": p.get("/VirtualBox/GuestAdd/Version") or (m.get("GuestAdditionsVersion") or "").split(" ")[0]
                             or None,
        # sesión: usuarios conectados que NO son la pantalla de login; sin esa lista, el nivel 3 (escritorio) basta
        "sesion": bool(personas) if lista is not None else (nivel >= 3 if nivel else None),
        "usuarios": ",".join(personas) or None,
        "ip": p.get("/VirtualBox/GuestInfo/Net/0/V4/IP"),
        "natpf": [v for k, v in m.items() if k.startswith("Forwarding(")],
        "grabacion": {
            "fichero": m.get("rec_screen_dest_filename"),
            "res": m.get("rec_screen_video_res_xy"),
            "fps": m.get("rec_screen_video_fps"),
            "kbps": m.get("rec_screen_video_rate_kbps"),
            "activa": m.get("recording_started") == "on",
        },
    }


def tamano_png(path):
    """(ancho, alto) de un PNG leyendo su cabecera IHDR (sin Pillow)."""
    with open(path, "rb") as f:
        cab = f.read(24)
    if cab[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} no es un PNG")
    return struct.unpack(">II", cab[16:24])


def resolucion():
    """Resolución del invitado: REAL (captura) si está encendida; si no, la última que recuerda VirtualBox
    (GUI/LastGuestSizeHint). None si no se sabe."""
    if maquina().get("VMState") == "running":
        png = os.path.join(TMP, "_vmres.png")
        if vbox("controlvm", VM, "screenshotpng", png, check=False).returncode == 0:
            return tamano_png(png)
    v = vbox("getextradata", VM, "GUI/LastGuestSizeHint", check=False).stdout
    m = re.search(r"(\d+),\s*(\d+)", v)
    return (int(m.group(1)), int(m.group(2))) if m else None
