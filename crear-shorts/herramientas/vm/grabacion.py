"""Grabación de la toma. POR DEFECTO, la grabación NATIVA de VirtualBox en el ANFITRIÓN: no ejecuta nada dentro de la
VM, funciona sin ningún canal (ni SSH ni guestcontrol) y el cursor del invitado sale en el vídeo (medido).
Alternativa: ffmpeg x11grab DENTRO del invitado (`guest=True`, necesita un canal y ffmpeg en la VM).

Lo que VirtualBox impone (medido) y cómo se resuelve:
  - Con la VM ENCENDIDA, la grabación solo se puede reconfigurar (resolución, fps, fichero) si no ha estado activa en
    esta sesión de la VM; después da E_INVALIDARG "Cannot change ... while recording is enabled".
  - Con la VM APAGADA se puede todo (`modifyvm`). Por eso `start` la deja configurada ANTES de encender, a la última
    resolución conocida del invitado (GUI/LastGuestSizeHint), y `rec_start` comprueba antes de grabar que coincide con
    la resolución REAL (medida en la captura): si no, intenta corregirla y, si VirtualBox no deja, para con la
    solución en vez de grabar una toma que no sirve.
  - Valores de VirtualBox por defecto: 1024x768 a 25 fps y 512 kbps, en <carpeta de la VM>/<vm>-screen0.webm:
    inservibles para un Short. Se usan 30 fps, 10 Mbps y un fichero fijo en editor/crudo/.
  - VirtualBox añade "-screen0" al nombre del fichero; se busca con comodín al parar.
"""
import glob
import os
import subprocess
import time

from nucleo import toma as contrato
from nucleo.ffmpeg import localizar

from . import info
from .anfitrion import vbox
from .config import VM, die
from .conexion import scp_from, ssh
from .registro import _log, _save_state, _state

FPS = 30
KBPS = 10000                 # 10 Mbps en VP8: suficiente para texto de terminal nítido tras recodificar a H.264
RES_DEFECTO = (1920, 1012)   # si VirtualBox no recuerda la resolución del invitado


def fichero_fijo():
    """El .webm donde VirtualBox graba siempre (editor/crudo/_vbox_rec.webm)."""
    return contrato.ruta("_vbox_rec", "webm")


def diferencias(cfg, res, fps=FPS, kbps=KBPS):
    """Qué no cuadra entre la configuración de grabación (info.resumen()['grabacion']) y lo que hace falta."""
    d = []
    if cfg.get("res") != f"{res[0]}x{res[1]}":
        d.append(f"resolución {cfg.get('res')} != invitado {res[0]}x{res[1]}")
    if str(cfg.get("fps")) != str(fps):
        d.append(f"fps {cfg.get('fps')} != {fps}")
    if int(cfg.get("kbps") or 0) < kbps:
        d.append(f"calidad {cfg.get('kbps')} kbps < {kbps}")
    return d


def configurar(res=None, fps=FPS, kbps=KBPS):
    """Deja la grabación configurada a `res` (por defecto, la resolución del invitado). Con la VM apagada usa modifyvm
    (siempre se puede); encendida, controlvm (solo si no se ha grabado en esta sesión). Devuelve la lista de
    diferencias que QUEDAN tras intentarlo (vacía = bien)."""
    res = res or info.resolucion() or RES_DEFECTO
    fijo = fichero_fijo()
    os.makedirs(os.path.dirname(fijo), exist_ok=True)
    estado = info.maquina().get("VMState")
    if estado in ("poweroff", "aborted"):
        vbox("modifyvm", VM, f"--recording-file={fijo}", f"--recording-video-res={res[0]}x{res[1]}",
             f"--recording-video-fps={fps}", f"--recording-video-rate={kbps}", check=False)
    elif estado == "running":
        for args in (["filename", fijo], ["videores", f"{res[0]}x{res[1]}"], ["videofps", str(fps)],
                     ["videorate", str(kbps)]):
            vbox("controlvm", VM, "recording", *args, check=False)
    return diferencias(info.resumen()["grabacion"], res, fps, kbps)


def rec_start(w=None, h=None, fps=FPS, guest=False):
    """Empieza a grabar (VirtualBox en el anfitrión salvo guest=True). Antes comprueba que la grabación está
    configurada a la resolución REAL del invitado; si no lo está y VirtualBox no deja cambiarla, para."""
    st = _state()
    if not st.get("name"):
        die("primero: take start NOMBRE")
    if guest:
        return _rec_start_guest(st, w, h, fps)
    res = (w, h) if w and h else info.resolucion()
    if not res:
        die("no puedo medir la resolución del invitado (¿VM encendida? vm_control.py status)")
    pendientes = diferencias(info.resumen()["grabacion"], res, fps)
    if pendientes:
        pendientes = configurar(res, fps)
    if pendientes:
        die("la grabación de VirtualBox no está bien configurada (" + "; ".join(pendientes) + ") y VirtualBox no deja "
            "cambiarla con la VM encendida tras haber grabado en esta sesión. Solución: `vm_control.py stop` y "
            "`vm_control.py start` (start la configura antes de encender), o `rec start --guest`.")
    fichero = info.resumen()["grabacion"]["fichero"] or fichero_fijo()
    for f in glob.glob(os.path.splitext(fichero)[0] + "*.webm"):
        os.remove(f)                                   # que la toma anterior no deje restos
    vbox("controlvm", VM, "recording", "start", check=False)
    time.sleep(0.8)
    if not info.resumen()["grabacion"]["activa"]:
        die("la grabación de VirtualBox no arrancó")
    st.update(rec_t0=time.time(), rec_backend="vbox", rec_file=fichero)
    _save_state(st)
    _log(op="rec_start", backend="vbox", size=f"{res[0]}x{res[1]}", fps=fps)
    print(f"grabando (VirtualBox, anfitrión) {res[0]}x{res[1]}@{fps} -> {fichero}")


def _rec_start_guest(st, w, h, fps):
    if not w:
        m = ssh("xdpyinfo | grep dimensions | awk '{print $2}'", capture=True)
        w, h = (int(v) for v in m.split("x"))
    # setsid, no nohup+disown: con disown el canal SSH tarda MINUTOS en devolver el control aunque el
    # proceso quede bien lanzado (medido); setsid lo desengancha de la sesión y ssh() vuelve al instante.
    ssh(f"rm -f /tmp/cutly_rec.mp4; setsid ffmpeg -y -f x11grab -draw_mouse 1 -framerate {fps} "
        f"-video_size {w}x{h} -i :0 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p "
        f"-movflags +faststart /tmp/cutly_rec.mp4 </dev/null >/tmp/cutly_rec.log 2>&1 &")
    for _ in range(20):
        if ssh("pgrep -x ffmpeg >/dev/null && test -s /tmp/cutly_rec.mp4 && echo ok", capture=True, check=False) == "ok":
            break
        time.sleep(0.3)
    else:
        die("ffmpeg no arrancó en el invitado (¿instalado? sudo apt install ffmpeg). Log: /tmp/cutly_rec.log")
    st.update(rec_t0=time.time(), rec_backend="guest")
    _save_state(st)
    _log(op="rec_start", backend="guest", size=f"{w}x{h}", fps=fps)
    print(f"grabando (ffmpeg DENTRO de la VM) {w}x{h}@{fps}")


def rec_stop():
    """Para la grabación y deja editor/crudo/<toma>.mp4 (H.264, 30 fps constantes: lo que espera la Fase 2)."""
    st = _state()
    _log(op="rec_stop")
    dest = contrato.ruta(st.get("name", "toma"), "mp4")
    if st.get("rec_backend") == "guest":
        ssh("pkill -INT -x ffmpeg; for i in $(seq 1 30); do pgrep -x ffmpeg >/dev/null || break; sleep 0.3; done", check=False)
        if not scp_from("/tmp/cutly_rec.mp4", dest):
            die("no pude traer el vídeo. Sigue en el invitado: /tmp/cutly_rec.mp4")
    else:
        vbox("controlvm", VM, "recording", "stop", check=False)
        time.sleep(2)                                   # VirtualBox cierra el .webm unos instantes después
        fichero = st.get("rec_file") or fichero_fijo()
        webms = sorted(glob.glob(os.path.splitext(fichero)[0] + "*.webm"))
        if not webms:
            die(f"VirtualBox no dejó el .webm de la grabación (esperado junto a {fichero})")
        ff = localizar("ffmpeg")
        if not ff:
            die("falta ffmpeg en el anfitrión (Windows: winget install Gyan.FFmpeg)")
        # VP8 de VirtualBox -> H.264 CFR 30 fps: calidad alta y compatible con construir_short/construir_clip
        r = subprocess.run([ff, "-v", "error", "-y", "-i", webms[0], "-c:v", "libx264", "-preset", "medium", "-crf", "14",
                            "-r", "30", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", dest],
                           capture_output=True, text=True)
        if r.returncode:
            die(f"ffmpeg no pudo convertir la grabación: {r.stderr.strip()[:200]}")
        for f in webms:
            os.remove(f)
    st.pop("rec_t0", None)
    _save_state(st)
    print("vídeo:", dest)
    return dest
