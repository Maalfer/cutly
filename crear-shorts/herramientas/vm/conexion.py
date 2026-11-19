"""Puerta única con el invitado: TODO lo que se ejecuta o se copia dentro de la VM pasa por aquí, y aquí se decide
por qué canal viaja (vm/canales/: ssh o guestcontrol; VM_CANAL=ssh|guestcontrol|auto).

Los nombres ssh()/ssh_ok()/scp_from()/scp_to() se conservan porque son la API de siempre (demos, CLI); hoy
significan "en el invitado, por el canal activo". Sinónimos neutros: ejecutar, invitado_ok, traer, enviar.
"""
import os

from .canales import CANALES, ORDEN_AUTO, CanalTimeout
from .config import die

_activo = None          # canal confirmado (en auto se fija el primero que responde)


def _pedido():
    v = os.environ.get("VM_CANAL", "auto").strip().lower()
    if v != "auto" and v not in CANALES:
        die(f"VM_CANAL={v!r} no existe: usa {', '.join(CANALES)} o auto")
    return v


def canal():
    """El canal activo. Con VM_CANAL fijo, ese; en auto, el primero de ORDEN_AUTO que responde (si ninguno responde
    todavía, ssh, para que los mensajes de error sean los de siempre)."""
    global _activo
    if _activo is not None:
        return _activo
    pedido = _pedido()
    if pedido != "auto":
        _activo = CANALES[pedido]()
        return _activo
    for nombre in ORDEN_AUTO:
        c = CANALES[nombre]()
        if c.disponible():
            _activo = c
            return c
    return CANALES[ORDEN_AUTO[0]]()          # sin fijar: se reintenta en la próxima llamada


def reiniciar():
    """Olvida el canal elegido (p. ej. tras reiniciar la VM o cambiar VM_CANAL)."""
    global _activo
    _activo = None


def ssh(script, capture=False, check=True, timeout=25):
    """Ejecuta `script` (bash) en el invitado. capture=True devuelve su salida; si no, True/False según el código.
    `timeout` es obligatorio: un proceso en segundo plano mal desenganchado puede dejar el canal colgado."""
    c = canal()
    try:
        rc, out, err = c.ejecutar(script, timeout)
    except CanalTimeout as e:
        die(f"{c.nombre} TIMEOUT tras {timeout}s ({e}; ¿algo en segundo plano sigue enganchado a la salida?) — "
            f"script:\n{script[:200]}")
    except PermissionError as e:
        die(str(e))
    out = out.decode("utf-8", "replace").strip()
    err = err.decode("utf-8", "replace").strip()
    if rc and check:
        die(f"{c.nombre} falló: {err or out}")
    return out if capture else (rc == 0)


def ssh_ok():
    """¿Responde el invitado? (por el canal fijado o, en auto, por cualquiera)."""
    if _activo is not None:
        return _activo.disponible()
    pedido = _pedido()
    nombres = ORDEN_AUTO if pedido == "auto" else (pedido,)
    return any(CANALES[n]().disponible() for n in nombres)


def scp_from(remote, local):
    return canal().traer(remote, local)


def scp_to(local, remote):
    return canal().enviar(local, remote)


def describir():
    return canal().describir()


# sinónimos neutros (el canal ya no es necesariamente SSH)
ejecutar = ssh
invitado_ok = ssh_ok
traer = scp_from
enviar = scp_to
