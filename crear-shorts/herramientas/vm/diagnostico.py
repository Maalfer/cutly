"""`vm_control.py doctor`: diagnóstico de TODO lo que necesita una demo en la VM, con la solución de cada problema.

    recoger()          mide (VBoxManage, canal, anfitrión, invitado) -> dict
    evaluar(datos)     reglas puras sobre ese dict -> [(nivel, punto, detalle, solución)]   (probado sin VM)
    doctor()           imprime y devuelve True si no hay ninguna FALLA

Niveles: OK · INFO · AVISO (funciona, pero algo conviene arreglar) · FALLA (una demo no saldría bien).
"""
import os
import re
import shutil

from nucleo.ffmpeg import localizar

from . import grabacion, info
from .anfitrion import find_tesseract, find_vboxmanage, vbox
from .canales.guestcontrol import CanalGuestControl
from .canales.ssh import diagnosticar
from .config import KEY, PORT, VM
from .conexion import describir, ssh, ssh_ok
from .registro import _state

HERRAMIENTAS_INVITADO = ("xdotool", "xclip", "xdpyinfo", "python3")   # imprescindibles
OPCIONALES_INVITADO = ("wmctrl",)                                   # hay alternativa (maximize usa xdotool)


def recoger():
    d = {"vboxmanage": find_vboxmanage(), "version_host": vbox("--version", check=False).stdout.strip(),
         "existe": info.existe(), "vms": info.vms(), "clave": os.path.exists(KEY), "puerto": PORT,
         "credenciales_gc": CanalGuestControl().credenciales() is not None,
         "anfitrion": {"ffmpeg": bool(localizar("ffmpeg")),
                       "tesseract": bool(find_tesseract()), "ssh": bool(shutil.which("ssh"))},
         "toma_abierta": _state().get("name")}
    if not d["existe"]:
        return d
    r = info.resumen()
    d.update(resumen=r, resolucion=info.resolucion())
    if r["estado"] == "running":
        d["canal_ok"] = ssh_ok()
        d["canal"] = describir()
        d["ssh_diagnostico"] = diagnosticar()
        if d["canal_ok"]:
            faltan = ssh("for c in " + " ".join(HERRAMIENTAS_INVITADO + OPCIONALES_INVITADO) + "; do command -v $c >/dev/null || echo $c; "
                         "done; xdpyinfo >/dev/null 2>&1 && echo __X11_OK", capture=True, check=False)
            d["invitado_faltan"] = [x for x in faltan.split() if x != "__X11_OK"]
            d["x11"] = "__X11_OK" in faltan
    return d


def _mayor_menor(v):
    m = re.match(r"(\d+)\.(\d+)", v or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def evaluar(d):
    out = []
    a = out.append
    a(("OK", "VirtualBox", f"{d['version_host']} ({d['vboxmanage']})", ""))
    if not d["existe"]:
        a(("FALLA", "VM", f"no existe '{VM}'; hay: {', '.join(d['vms']) or 'ninguna'}", "define VM_NAME=<nombre>"))
        return out
    r = d["resumen"]
    a(("INFO", "estado", r["estado"], "vm_control.py start" if r["estado"] in ("poweroff", "aborted") else
       ("vm_control.py resume (la reanuda en segundos)" if r["estado"] == "saved" else "")))
    # --- grabación: lo único que se puede dejar perfecto con la VM apagada
    res = d.get("resolucion")
    if res:
        dif = grabacion.diferencias(r["grabacion"], res)
        if dif:
            a(("AVISO" if r["estado"] != "running" else "FALLA", "grabación", "; ".join(dif),
               "vm_control.py start la configura antes de encender" if r["estado"] != "running" else
               "rec start intentará corregirla; si VirtualBox no deja: vm_control.py stop + start"))
        else:
            a(("OK", "grabación", f"{r['grabacion']['res']} @ {r['grabacion']['fps']} fps, {r['grabacion']['kbps']} kbps",
               ""))
    # --- canal SSH: montaje
    if not any(f",{d['puerto']},," in f for f in r["natpf"]):
        a(("AVISO", "regla NAT ssh", f"no hay reenvío 127.0.0.1:{d['puerto']} -> 22", "vm_control.py start / bootstrap "
           "con la VM apagada (o usa VM_CANAL=guestcontrol)"))
    if not d["clave"]:
        a(("AVISO", "clave SSH", f"no existe {KEY}", "vm_control.py bootstrap (o VM_CANAL=guestcontrol)"))
    a(("INFO", "guestcontrol", "con credenciales" if d["credenciales_gc"] else "sin credenciales",
       "" if d["credenciales_gc"] else "opcional: VM_GUEST_PASSFILE=<fichero con TU contraseña>"))
    # --- con la VM encendida
    if r["estado"] == "running":
        host, inv = _mayor_menor(d["version_host"]), _mayor_menor(r["version_adiciones"])
        if not r["nivel_adiciones"]:
            a(("FALLA", "Guest Additions", "no responden", "instálalas en el invitado (Dispositivos > Insertar imagen "
               "de CD de las Guest Additions) o espera a que termine de arrancar"))
        elif inv and host and inv != host:
            a(("AVISO", "Guest Additions", f"{r['version_adiciones']} en el invitado, VirtualBox {d['version_host']}",
               "actualízalas (Dispositivos > Insertar imagen de CD de las Guest Additions)"))
        else:
            a(("OK", "Guest Additions", f"{r['version_adiciones']} (nivel {r['nivel_adiciones']}: "
               f"{info.NIVELES.get(r['nivel_adiciones'], '?')})", ""))
        if r["sesion"] is False:
            a(("FALLA", "sesión", "nadie ha iniciado sesión en el escritorio del invitado",
               "inicia sesión en la VM (la contraseña la pones tú)"))
        elif r["sesion"]:
            a(("OK", "sesión", r["usuarios"] or "iniciada", ""))
        if d.get("canal_ok"):
            a(("OK", "canal", d["canal"], ""))
            imprescindibles = [x for x in d.get("invitado_faltan", []) if x not in OPCIONALES_INVITADO]
            opcionales = [x for x in d.get("invitado_faltan", []) if x in OPCIONALES_INVITADO]
            if imprescindibles:
                a(("FALLA", "herramientas del invitado", "faltan: " + ", ".join(imprescindibles),
                   "sudo apt install " + " ".join(imprescindibles).replace("xdpyinfo", "x11-utils")))
            if opcionales:
                a(("INFO", "herramientas opcionales del invitado", "faltan: " + ", ".join(opcionales) +
                   " (hay alternativa)", "opcional: sudo apt install " + " ".join(opcionales)))
            if d.get("x11") is False:
                a(("FALLA", "sesión X11", "xdpyinfo no abre :0 (¿Wayland o sin sesión?)", "inicia sesión en Xfce (X11)"))
        else:
            a(("FALLA", "canal", "el invitado no responde por ningún canal", "SSH: " + d.get("ssh_diagnostico", "")))
    # --- anfitrión
    for herramienta, necesaria in (("ffmpeg", "grabar y editar"), ("tesseract", "OCR (waitfor, clicktext)"),
                                   ("ssh", "canal ssh")):
        if not d["anfitrion"][herramienta]:
            a(("FALLA" if herramienta != "ssh" else "AVISO", herramienta, f"no está en el anfitrión ({necesaria})",
               "ver PORTABILIDAD.md"))
    if d.get("toma_abierta"):
        a(("AVISO", "toma abierta", f"'{d['toma_abierta']}' sigue abierta", "vm_control.py take end"))
    return out


def doctor():
    filas = evaluar(recoger())
    for nivel, punto, detalle, sol in filas:
        print(f"[{nivel:<5}] {punto}: {detalle}" + (f"\n          -> {sol}" if sol else ""))
    fallas = sum(1 for f in filas if f[0] == "FALLA")
    print("\n" + ("todo listo para grabar una demo" if not fallas else f"{fallas} problema(s) que impiden una demo"))
    return not fallas
