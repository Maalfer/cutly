"""La TOMA: registro de pasos + grabación + mapa de edición. Deja en editor/crudo/ lo que espera la Fase 2
(contrato: nucleo/toma.py): <toma>.mp4 (H.264 30 fps), <toma>.steps.jsonl y <toma>.mapa.md."""
import glob
import os
import re
import subprocess
import time

from nucleo import toma as contrato
from nucleo.ffmpeg import localizar
from nucleo.rutas import CRUDO

from .anfitrion import vbox
from .config import VM, die
from .conexion import scp_from, ssh, ssh_ok
from .registro import _log, _save_state, _state


def take_start(name):
    os.makedirs(CRUDO, exist_ok=True)
    log = contrato.ruta(name, "steps.jsonl")
    open(log, "w", encoding="utf-8").close()
    _save_state({"name": name, "log": log})
    _log(op="take_start", name=name)
    print("registro:", log)


def _crudo(name, ext):
    return contrato.ruta(name, ext)


def rec_start(w=None, h=None, fps=30, guest=False):
    """Empieza a grabar. POR DEFECTO con la grabación NATIVA de VirtualBox, en el ANFITRIÓN: no instala ni
    ejecuta nada dentro de la VM, funciona sin SSH y el cursor del invitado sale en el vídeo (medido).
    `guest=True` usa ffmpeg x11grab dentro del invitado (necesita SSH+ffmpeg): solo como alternativa.

    VirtualBox NO deja cambiar la resolución NI el nombre de fichero de la grabación una vez que
    `recording_enabled` ha estado "on" en esta sesión de la VM — ni siquiera tras `recording off`
    (medido: sigue dando E_INVALIDARG "Cannot change ... while recording is enabled"; `modifyvm` lo
    arreglaría pero exige la VM apagada, imposible entre tomas). Por eso: se configura resolución/fichero
    SOLO la primera vez que `rec_screen_dest_filename` está vacío; las siguientes tomas REUTILIZAN ese
    mismo fichero fijo (`_vbox_rec.webm`) y solo hacen `start`/`stop` — sin tocar más ajustes."""
    st = _state()
    if not st.get("name"):
        die("primero: take start NOMBRE")
    if guest:
        return _rec_start_guest(st, w, h, fps)
    if not w:
        m = ssh("xdpyinfo | grep dimensions | awk '{print $2}'", capture=True, check=False) if ssh_ok() else ""
        w, h = (int(v) for v in m.split("x")) if "x" in m else (1920, 1012)
    info = vbox("showvminfo", VM, "--machinereadable", check=False).stdout
    cur_file = re.search(r'rec_screen_dest_filename="([^"]*)"', info)
    fixed = _crudo("_vbox_rec", "webm")
    if not cur_file or not cur_file.group(1):
        # primera vez: configurar de verdad (aquí SÍ se puede, antes de que nada quede "enabled")
        for args in (["videores", str(w), str(h)], ["videofps", str(fps)], ["videorate", "10000"],
                    ["filename", fixed]):
            r = vbox("controlvm", VM, "recording", *args, check=False)
            if r.returncode:
                die(f"VBoxManage recording {args[0]} falló: {r.stderr.strip()[:150]}")
    elif cur_file.group(1) != fixed:
        print(f"aviso: VirtualBox ya tenía fijado otro fichero de grabación ({cur_file.group(1)}); "
              "se reutiliza tal cual (no se puede cambiar en caliente)")
        fixed = cur_file.group(1)
    if os.path.exists(fixed):
        os.remove(fixed)                       # que la toma anterior no deje restos en el fichero fijo
    vbox("controlvm", VM, "recording", "start", check=False)
    time.sleep(0.8)
    if 'recording_started="on"' not in vbox("showvminfo", VM, "--machinereadable", check=False).stdout:
        die("la grabación de VirtualBox no arrancó")
    st.update(rec_t0=time.time(), rec_backend="vbox", rec_file=fixed)
    _save_state(st)
    _log(op="rec_start", backend="vbox", size=f"{w}x{h}", fps=fps)
    print(f"grabando (VirtualBox, anfitrión) {w}x{h}@{fps} -> {fixed}")


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
    dest = _crudo(st.get("name", "toma"), "mp4")
    if st.get("rec_backend") == "guest":
        ssh("pkill -INT -x ffmpeg; for i in $(seq 1 30); do pgrep -x ffmpeg >/dev/null || break; sleep 0.3; done", check=False)
        if not scp_from("/tmp/cutly_rec.mp4", dest):
            die("no pude traer el vídeo (scp). Sigue en el invitado: /tmp/cutly_rec.mp4")
    else:
        vbox("controlvm", VM, "recording", "stop", check=False)
        time.sleep(2)                                   # VirtualBox cierra el .webm unos instantes después
        # Fichero FIJO (ver rec_start: VBox no deja cambiar el nombre tras la 1ª vez), no uno con el
        # nombre de la toma: VirtualBox lo guarda como "<fijo>-screen0.webm" (sufijo de pantalla).
        fixed = st.get("rec_file") or _crudo("_vbox_rec", "webm")
        webms = sorted(glob.glob(fixed.replace(".webm", "") + "*.webm"))
        if not webms:
            die(f"VirtualBox no dejó el .webm de la grabación (esperado junto a {fixed})")
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


def take_end():
    st = _state()
    if st.get("rec_t0"):
        rec_stop()
    if st.get("log"):
        _log(op="take_end")
        print("mapa:", build_map(st["name"]))
    _save_state({})


def build_map(name):
    """Mapa de edición (doc 04 §Fase 4) generado desde el registro: un bloque por 'mark' con su rango en el vídeo."""
    ev = contrato.cargar_eventos(contrato.ruta(name, "steps.jsonl"))
    t_of = lambda e: e.get("t_video", e["t_wall"] - ev[0]["t_wall"])
    marks = [e for e in ev if e["op"] == "mark"]
    end = t_of(ev[-1])
    rows = ["| # | Momento | Desde (s) | Hasta (s) | Dura | Pasos |", "|---|---|---|---|---|---|"]
    for i, m in enumerate(marks):
        a = t_of(m)
        b = t_of(marks[i + 1]) if i + 1 < len(marks) else end
        n = sum(1 for e in ev if e["op"] not in ("mark", "take_start", "take_end", "rec_start", "rec_stop") and a <= t_of(e) < b)
        rows.append(f"| {i + 1} | {m['label']} | {a:.1f} | {b:.1f} | {b - a:.1f} s | {n} |")
    fails = [e for e in ev if e.get("ok") is False]
    out = f"# Mapa de edición — {name}\n\n" + "\n".join(rows) + "\n"
    if fails:
        out += "\n## Pasos fallidos (rehacer)\n" + "\n".join(f"- t={t_of(e):.1f}s `{e['op']}` {e.get('error', '')}" for e in fails) + "\n"
    out += "\nTiempos en segundos desde el inicio del vídeo (±0,3 s). El Short se construye con editor/shorts/short_desde_toma.py.\n"
    path = contrato.ruta(name, "mapa.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path
