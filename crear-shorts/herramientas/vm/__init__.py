"""
vm — control de la VM de VirtualBox con entrada HUMANA, desde cualquier anfitrión. Un módulo por responsabilidad
(de arriba abajo: cada uno solo importa de los anteriores):
    config      variables de entorno (VM, clave, puerto, usuario, canal) y die()
    anfitrion   VBoxManage (errores legibles) y Tesseract en el anfitrión
    registro    registro de la toma: @logged, focus, mark (lo lee la edición)
    conexion    puerta única con el invitado: elige el canal (canales/: ssh | guestcontrol; VM_CANAL)
    info        lo que VirtualBox sabe SIN credenciales: estado, Guest Additions, sesión, IP, resolución
    pantalla    VER: capturas, OCR, waitfor / waitstill / waitgone
    entrada     ACTUAR: ratón y teclado humanos, clic por texto/imagen, selección, guarda de foco
    ventanas    lanzar apps, terminales por ID, foco, colocar, maximizar
    grabacion   grabación de VirtualBox (configurada a la resolución real del invitado) o ffmpeg en el invitado
    maquina     ciclo de vida: start por fases (Guest Additions -> sesión -> canal), stop, suspend/resume, bootstrap
    toma        take start/end y mapa de edición
    escenario   estado de partida de las demos (lab, Burp, Firefox) y labcheck
    diagnostico doctor: comprueba todo y da la solución de cada problema
    canales/    los canales intercambiables con el invitado (ssh, guestcontrol)

CLI y API pública de siempre: `vm_control.py` (`import vm_control as v` en las demos). Para añadir una capacidad,
ponla en el módulo de su responsabilidad y expórtala aquí; la CLI, en vm_control.main().
Lógica pura sin VM (y probada aparte, pruebas/): ../tipear.py (teclado), ../mover.py (ratón), ../ocr_buscar.py (OCR).
"""
import os
import sys

_HERRAMIENTAS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.abspath(os.path.join(_HERRAMIENTAS, "..", ".."))
for _p in (_HERRAMIENTAS, _REPO):      # tipear/mover/ocr_buscar y nucleo/
    if _p not in sys.path:
        sys.path.insert(0, _p)

from .config import VM, KEY, PORT, USER, TMP, STATE_FILE, IS_WIN, die, contrasena_invitado  # noqa: E402,F401
from .anfitrion import find_vboxmanage, find_tesseract, vbox  # noqa: E402,F401
from .registro import _state, _save_state, _log, logged, focus, mark  # noqa: E402,F401
from .conexion import (canal, reiniciar, ssh, ssh_ok, scp_from, scp_to, describir, ejecutar,
    invitado_ok, traer, enviar)  # noqa: E402,F401
from . import info  # noqa: E402,F401
from .pantalla import shot, _tess_tsv, _ocr_words, _words_text, waitfor, waitstill, waitgone  # noqa: E402,F401
from .entrada import (_pos_cache, pos, active_title, require_focus, PLAYER, compile_plan, play, move, click,
    type_human, typeurl, _find, clicktext, clickimg, _find_detail, selecttext, type_in)  # noqa: E402,F401
from .ventanas import (launch_terminal, place_id, activate_id, launch, _wid, activate, maximize, place, _is_running)  # noqa: E402,F401
from . import grabacion  # noqa: E402,F401  (grabacion.configurar, grabacion.fichero_fijo...)
from .grabacion import rec_start, _rec_start_guest, rec_stop  # noqa: E402,F401
from .maquina import (vm_state, ensure_natpf, esperar, iniciar_sesion, start, stop, suspend, resume, set_res, bootstrap)  # noqa: E402,F401
from .toma import take_start, take_end, build_map  # noqa: E402,F401
from .escenario import labcheck, burp_up, MODALES, dismiss_modals, prepare  # noqa: E402,F401
from .diagnostico import doctor  # noqa: E402,F401

# API pública (vm_control.py la reexporta con `from vm import *`; incluye los _privados que usan las demos)
__all__ = [
    "VM", "KEY", "PORT", "USER", "TMP", "STATE_FILE", "IS_WIN", "die", "contrasena_invitado", "find_vboxmanage", "find_tesseract", "vbox",
    "_state", "_save_state", "_log", "logged", "focus", "mark", "canal", "reiniciar", "ssh",
    "ssh_ok", "scp_from", "scp_to", "describir", "ejecutar", "invitado_ok", "traer", "enviar", "info", "grabacion",
    "shot",
    "_tess_tsv", "_ocr_words", "_words_text", "waitfor", "waitstill", "waitgone", "_pos_cache", "pos",
    "active_title", "require_focus", "PLAYER", "compile_plan", "play", "move", "click", "type_human", "typeurl",
    "_find", "clicktext", "clickimg", "_find_detail", "selecttext", "type_in", "launch_terminal", "place_id",
    "activate_id", "launch", "_wid", "activate", "maximize", "place", "_is_running",
    "rec_start", "_rec_start_guest", "rec_stop", "vm_state", "ensure_natpf", "esperar", "iniciar_sesion", "start", "stop", "suspend",
    "resume", "set_res", "bootstrap", "take_start", "take_end", "build_map", "labcheck", "burp_up", "MODALES",
    "dismiss_modals", "prepare", "doctor",
]
