#!/usr/bin/env python3
"""
vm_control.py — Controla una VM Linux (X11) de VirtualBox con entrada HUMANA, desde CUALQUIER anfitrión
(Windows, macOS o Linux). Es la "mano" de la IA: ve (capturas de VBoxManage), actúa (xdotool en el invitado,
por SSH) y verifica (OCR / plantillas / log del lab).

ESTÁNDAR DEL REPO: todas las tomas se hacen DENTRO de la VM (ver METODOLOGIA/00-empezar-aqui-vm.md).

Requisitos en el ANFITRIÓN: VBoxManage (se localiza solo, ver find_vboxmanage), ssh (OpenSSH; viene con
Windows 10/11), python3 y un OCR (Tesseract en cualquier SO, o el que indique VM_OCR_CMD).
Opcionales: Pillow (OCR por región), opencv-python (clickimg: búsqueda por plantilla).
Requisitos en el INVITADO: Guest Additions, sesión X11 iniciada, xdotool, xclip, x11-utils, wmctrl, python3;
sshd para el canal ssh (ffmpeg solo para `rec start --guest`).

Primera vez (una sola):  vm_control.py doctor  (dice qué falta y cómo arreglarlo)  ->  vm_control.py bootstrap
Canal con el invitado: VM_CANAL=auto (defecto: ssh si responde, si no guestcontrol) | ssh | guestcontrol (vm/canales/)
Variables: VM_NAME (kali) VM_KEY (~/.ssh/cutly_vm) VM_SSH_PORT (2222) VM_USER (kali) VBOXMANAGE (ruta)
           VM_OCR=tesseract (fuerza Tesseract) VM_OCR_CMD (OCR externo, p. ej. ocr.swift compilado) VM_GUEST_PASS (contraseña del invitado, SOLO si la das tú,
           para instalar la clave con `guestcontrol` o para usar el canal guestcontrol; mejor VM_GUEST_PASSFILE=<fichero>;
           el script nunca adivina contraseñas)

CICLO DE VIDA
  doctor                                diagnóstico completo (VirtualBox, Guest Additions, sesión, canal, grabación,
                                         herramientas) con la solución de cada problema; código 1 si algo impide grabar
  start [--headless] [--seg N] [--login]   arranca y espera POR FASES (Guest Additions -> sesión -> canal), diciendo
                                         en cuál se queda; con la VM apagada deja antes la grabación configurada;
                                         --login inicia la sesión si se queda en la pantalla de login
  login                                 inicia la sesión del escritorio con TU contraseña (VM_GUEST_PASSFILE)
  stop | status | bootstrap
  suspend | resume                      guardar el estado (savestate) y reanudarlo en segundos: no es un snapshot
  res W H                               resolución del invitado (setvideomodehint) — p. ej. 1080 1920 para short
VER
  shot [salida.png]                     captura del invitado (~0,08 s)
  waitfor "texto" [seg] [--region x,y,w,h]  espera (OCR) a que aparezca un texto; código 1 si TIMEOUT
  waitstill [seg]                       espera a que la pantalla deje de cambiar
  focus X Y [W H] [motivo]              marca dónde/qué encuadrar (la edición del Short usa esto; waitfor lo hace solo).
                                         CON W H (región, p. ej. una ventana entera): letterbox, SIN recortar — úsalo
                                         siempre que el texto pueda llegar al borde (ver docstring de focus() en el código)
  windows | pos
ACTUAR (siempre con ritmo humano)
  move X Y [--dur S] [--seed N]         trayecto curvo (la posición se recuerda: sin viaje de ida y vuelta extra)
  click [dc]
  clicktext PALABRA [n] [dc] [--sub TROZO] [--region x,y,w,h]   (region: solo busca ahí; n=-1 la última)
  clickimg plantilla.png [dc]           clic en una imagen (botones que el OCR no lee; requiere opencv)
  selecttext PALABRA [n] --sub TROZO
  type "texto" [--wpm 55] [--typos 0.015] [--seed N] [--in "Título"]
  typeurl URL [--wpm 45] [--in "Título"]
  key Return | ctrl+alt+t ...
VERIFICAR SIN OCR
  labcheck "GET /cuenta?id=1002" [seg]  espera a que el lab haya servido esa petición (log del servidor)
TOMA: REGISTRO Y GRABACIÓN (conecta con la Fase 2: editar)
  take start NOMBRE                     abre el registro de la toma (JSONL con la hora de cada paso)
  mark "Acto 1: login"                  marca un momento del guion (aparece en el mapa de edición)
  rec start [W H FPS] [--guest] | rec stop   graba con VirtualBox en el ANFITRIÓN (cursor incluido, sin SSH); --guest: ffmpeg dentro
                                         (antes comprueba que la grabación está a la resolución REAL del invitado)
  rec config [W H]                      configura la grabación (resolución del invitado, 30 fps, 10 Mbps); mejor con la VM apagada
  take end                              cierra el registro, trae el vídeo y escribe el mapa de edición (.md)
  mapa NOMBRE                           regenera el mapa de edición desde el registro
ESTADO DE PARTIDA
  prepare [--cold]                      lab + Burp + Firefox demo; intenta reanudar el estado guardado
APPS Y VENTANAS
  put LOCAL REMOTO | get REMOTO LOCAL   copiar ficheros (scp)
  launch "cmd" | activate "Título" | place "Título" X Y W H | run "cmd"

`--in "Título"` es la GUARDA DE FOCO: si la ventana activa no contiene ese título, NO escribe.
"""
import os
import shlex
import sys

try:  # la consola de Windows (cp1252) no imprime tildes/emoji del invitado: forzar UTF-8 con reemplazo
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vm import *  # noqa: E402,F401,F403  toda la API (la lógica vive en vm/, un módulo por responsabilidad)


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)

    def opt(n, d=None, c=str):
        if n not in a:
            return d
        if a.index(n) + 1 >= len(a):
            die(f"falta el valor de {n}")
        return c(a[a.index(n) + 1])

    cmd = a[0]
    if cmd == "doctor":
        sys.exit(0 if doctor() else 1)
    elif cmd == "start":
        ok = start(opt("--seg", 150, float), headless="--headless" in a, login="--login" in a)
        print("OK" if ok else "NO LISTA: mira la última fase de arriba (o `vm_control.py doctor`)")
        sys.exit(0 if ok else 1)
    elif cmd == "login":
        iniciar_sesion()
    elif cmd == "stop":
        print("apagada" if stop() else "no se apagó a tiempo (se dejó como está)")
    elif cmd == "suspend":
        print("estado guardado" if suspend() else "no se pudo guardar")
    elif cmd == "resume":
        ok, s = resume()
        print(f"{'OK' if ok else 'TIMEOUT'} en {s}s")
        sys.exit(0 if ok else 1)
    elif cmd == "res":
        set_res(int(a[1]), int(a[2]))
    elif cmd == "status":
        r = info.resumen()
        ok = r["estado"] == "running" and ssh_ok()
        print(f"VM {VM}: {r['estado']} | invitado: {'responde' if ok else 'no responde'} | canal: {describir()}")
        if r["estado"] == "running":
            print(f"Guest Additions: {r['version_adiciones']} (nivel {r['nivel_adiciones']}) | sesión: "
                  f"{r['usuarios'] or ('sí' if r['sesion'] else 'no' if r['sesion'] is False else '?')} | IP: {r['ip']}")
        g = r["grabacion"]
        print(f"grabación: {g['res']} @ {g['fps']} fps, {g['kbps']} kbps -> {g['fichero']}")
        if ok:
            print("pantalla:", ssh("xrandr | grep '\\*' | head -1", capture=True))
            print("ventana activa:", active_title())
    elif cmd == "bootstrap":
        bootstrap()
    elif cmd == "prepare":
        prepare("--cold" in a)
    elif cmd == "take":
        {"start": lambda: take_start(a[2]), "end": take_end}[a[1]]()
    elif cmd == "mark":
        mark(a[1])
    elif cmd == "rec":
        if a[1] == "config":
            nums = [int(x) for x in a[2:] if x.isdigit()]
            quedan = grabacion.configurar(tuple(nums[:2]) if len(nums) >= 2 else None)
            print("grabación configurada" if not quedan else "NO se pudo: " + "; ".join(quedan))
            sys.exit(0 if not quedan else 1)
        elif a[1] == "start":
            nums = [x for x in a[2:] if x.isdigit()]
            rec_start(int(nums[0]) if len(nums) > 0 else None, int(nums[1]) if len(nums) > 1 else None,
                      int(nums[2]) if len(nums) > 2 else 30, guest="--guest" in a)
        else:
            rec_stop()
    elif cmd == "mapa":
        print(build_map(a[1]))
    elif cmd == "shot":
        print(shot(a[1] if len(a) > 1 else None))
    elif cmd == "pos":
        print("%d,%d" % pos(fresh=True))
    elif cmd == "move":
        move(int(a[1]), int(a[2]), opt("--dur", None, float), opt("--seed", None, int))
    elif cmd == "click":
        click("dc" in a)
    elif cmd == "type":
        type_human(a[1], opt("--wpm", 55.0, float), opt("--typos", 0.015, float), opt("--seed", None, int), opt("--in"))
    elif cmd == "typeurl":
        typeurl(a[1], opt("--wpm", 45.0, float), opt("--in"))
    elif cmd == "key":
        ssh("xdotool key " + " ".join(shlex.quote(k) for k in a[1:]))
        _log(op="key", args=a[1:])
    elif cmd == "windows":
        print(ssh('for w in $(xdotool search --onlyvisible --name ""); do '
                  'n=$(xdotool getwindowname $w 2>/dev/null); [ -n "$n" ] && '
                  'echo "$w | $n | $(xdotool getwindowgeometry --shell $w | tr "\\n" " ")"; done; true', capture=True))
    elif cmd == "waitfor":
        reg = tuple(float(v) for v in opt("--region").split(",")) if "--region" in a else None
        seg = float(a[2]) if len(a) > 2 and not a[2].startswith("--") else 20
        ok = waitfor(a[1], seg, region=reg)
        print("OK" if ok else "TIMEOUT")
        sys.exit(0 if ok else 1)
    elif cmd == "dismiss":
        print("cerrados:", dismiss_modals())
    elif cmd == "focus":
        # focus X Y [W H] [motivo]  — W H opcionales (región, letterbox sin recortar); motivo es lo que sobre
        wh = a[3:5] if len(a) > 4 and a[3].isdigit() and a[4].isdigit() else None
        resto = a[5:] if wh else a[3:]
        focus(int(a[1]), int(a[2]), " ".join(resto), *(int(v) for v in wh) if wh else (None, None))
    elif cmd == "waitstill":
        ok = waitstill(float(a[1]) if len(a) > 1 else 10)
        print("OK" if ok else "TIMEOUT")
        sys.exit(0 if ok else 1)
    elif cmd == "labcheck":
        ok = labcheck(a[1], float(a[2]) if len(a) > 2 else 10)
        print("OK" if ok else "NO VISTO")
        sys.exit(0 if ok else 1)
    elif cmd == "clicktext":
        n = int(a[2]) if len(a) > 2 and a[2].lstrip('-').isdigit() else 1
        reg = tuple(float(v) for v in opt("--region").split(",")) if "--region" in a else None
        print("%d,%d" % clicktext(a[1], n, "dc" in a, opt("--sub", ""), reg=reg))
    elif cmd == "clickimg":
        print("%d,%d" % clickimg(a[1], "dc" in a))
    elif cmd == "selecttext":
        n = int(a[2]) if len(a) > 2 and a[2].lstrip('-').isdigit() else 1
        selecttext(a[1], n, opt("--sub", ""))
        print("OK")
    elif cmd == "launch":
        launch(a[1])
    elif cmd == "activate":
        activate(a[1])
        print("OK")
    elif cmd == "place":
        print(place(a[1], int(a[2]), int(a[3]), int(a[4]), int(a[5])))
    elif cmd == "put":
        print("OK" if scp_to(a[1], a[2]) else "FALLÓ")
    elif cmd == "get":
        print("OK" if scp_from(a[1], a[2]) else "FALLÓ")
    elif cmd == "run":
        print(ssh(a[1], capture=True))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
