#!/usr/bin/env python3
"""
demo_masscan.py — Demo COMPLETA dentro de la VM: masscan contra la propia red doméstica del usuario.

    python demo_masscan.py [nombre_toma]        (def. masscan-AAAAMMDD-HHMM)

Marco ético: el objetivo es la red doméstica del propio usuario (su WiFi/LAN de casa) — autorización
propia, no un laboratorio de terceros. La VM `kali` está en modo puente (`bridged`) sobre el WiFi real
del anfitrión (ver 00-recon.md §3), así que `eth0` del invitado es un dispositivo más de esa LAN. Por eso
el canal de control YA NO usa el reenvío NAT 127.0.0.1:2222: hay que exportar VM_HOST=<IP real de la VM>
y VM_SSH_PORT=22 antes de lanzar este script (y cualquier otro comando de vm_control.py mientras la VM
siga en puente). `vm_control.py status` da esa IP sin necesitar SSH.

Hace: una sola terminal a pantalla completa → grabación → Acto 1 (cuál es mi red) → Acto 2 (barrido ICMP:
todos los hosts vivos) → Acto 3 (quién tiene el puerto 80 abierto) → Acto 4 (guardar el resultado y
mostrarlo) → trae el .mp4, el registro .steps.jsonl y el mapa de edición .mapa.md.
Cada paso se verifica (texto en pantalla); si uno falla, se detiene y queda marcado en el mapa.
Entrada humana siempre (vm_control.type_in/move/click). No se despliega ni se limpia ningún laboratorio:
el objetivo (la red de casa) ya está siempre ahí.
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramientas"))
import vm_control as v  # noqa: E402  (también pone nucleo/ en el path)
from nucleo.rutas import SHORTS  # noqa: E402

RED = "192.168.1.0/24"
GATEWAY = "192.168.1.1"       # router de casa: siempre vivo, sirve de verificación fiable en ambos barridos
IFACE = "eth0"                # interfaz puente del invitado (ver 00-recon.md §3)
ARCHIVO_RESULTADO = "~/resultado_masscan.txt"

# Geometría EXACTA de la terminal (resolución del invitado 1920x1012, offset de título 39px medido en
# las demos de terminal anteriores: ver METODOLOGIA/10 §3). NO a pantalla completa: medido en la primera
# toma de esta demo (masscan-20261120-0939) que un rect de 1920x973 (full screen) se encaja en el Short
# vertical a solo 1080x547 (43% de los 1272px disponibles bajo la banda de la cara) -> "se ve pequeño"
# desde el primer plano. DEMO-SSHOLE usa medio ancho (960x973, la misma altura) y llena el 86%: se reusa
# ese mismo ancho probado, centrado, para una sola terminal.
RECT = (480, 39, 960, 973)


def focus_rect(rect, why):
    x, y, w, h = rect
    v.focus(x + w // 2, y + h // 2, why, w=w, h=h)


def clear_and_focus(rect, why):
    """Limpia la terminal (Ctrl+L, instantáneo) y fija el foco en `rect`: el siguiente comando sale solo,
    arriba del todo, en vez de enterrado bajo el resultado del paso anterior (METODOLOGIA/10 §3.3)."""
    v.ssh("xdotool key ctrl+l")
    time.sleep(0.3)
    focus_rect(rect, why)


def verificar(ok, msg):
    if not ok:
        v.die("VERIFICACIÓN FALLIDA: " + msg)


def comprobar_entorno():
    """Sanidad previa, SIN grabar (Fase 0): masscan instalado y la interfaz puente con IP real de la LAN,
    no el NAT aislado de VirtualBox. Si esto falla no tiene sentido empezar la toma."""
    which = v.ssh("which masscan", capture=True, check=False)
    if not which.strip():
        v.die("masscan no está instalado en el invitado")
    ip_iface = v.ssh(f"ip -4 -o addr show {IFACE} | awk '{{print $4}}'", capture=True, check=False)
    if not ip_iface.strip():
        v.die(f"la interfaz {IFACE} no tiene IPv4 (¿la VM sigue en NAT en vez de en puente?)")
    print(f"entorno OK: {IFACE} = {ip_iface.strip()}")


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("masscan-%Y%m%d-%H%M")

    print("comprobando el entorno (sin grabar)...")
    comprobar_entorno()

    term = v.launch_terminal("Red")
    v.place_id(term, *RECT)
    v.activate_id(term)

    v.take_start(nombre)
    v.rec_start()
    focus_rect(RECT, "inicio: terminal a pantalla completa")   # ANTES del primer mark (METODOLOGIA/10 §3.5)
    try:
        v.mark("Acto 1: cuál es mi red")
        v.type_in(term, f"ip -br a show {IFACE}", wpm=42, typos=0.015, seed=1)
        v.ssh("xdotool key Return")
        verificar(v.waitfor("192.168.1", 8), "no se ve la IP de la interfaz puente")
        time.sleep(3)                                                  # pausa de lectura
        # waitfor() deja el foco en el PUNTO donde encontró el texto (recorte de 816x961, sin w/h): si se
        # teclea el siguiente comando con ese foco todavía puesto, una línea larga se sale del recorte y
        # parece que la cámara "se desplaza" al escribir (medido aquí; mismo fallo que sshole-run7, ver
        # METODOLOGIA/10 §3.4 y el docstring de vm/registro.py:focus). Hay que volver al rect completo
        # ANTES de teclear otra vez.
        focus_rect(RECT, "de vuelta a la ventana completa antes de teclear")
        v.type_in(term, "ip route | grep default", wpm=42, typos=0.01, seed=2)
        v.ssh("xdotool key Return")
        verificar(v.waitfor(GATEWAY, 6), "no se ve la puerta de enlace")
        time.sleep(3)

        v.mark("Acto 2: escaneo masivo — todos los hosts vivos")
        clear_and_focus(RECT, "barrido ICMP, limpio y arriba del todo")
        v.type_in(term, f"sudo masscan {RED} --ping --rate 2000 --wait 2", wpm=42, typos=0.01, seed=3)
        v.ssh("xdotool key Return")
        # NO se fija en la IP del gateway concreto: el ICMP real es con pérdidas, y qué host responde
        # primero varía de una toma a otra (medido: la puerta de enlace no siempre contesta a tiempo).
        # NO se fija tampoco en "0/icmp": Tesseract lo lee sistemáticamente como "@/ic" en esta fuente
        # (medido). "Discovered" solo sale cuando masscan encuentra un host de verdad: es la palabra fiable.
        verificar(v.waitfor("Discovered", 25), "el barrido ICMP no encontró ningún host vivo")
        time.sleep(4)                                                  # momento importante: se deja ver

        v.mark("Acto 3: quién tiene el puerto 80 abierto")
        clear_and_focus(RECT, "escaneo de puerto 80, limpio y arriba del todo")
        v.type_in(term, f"sudo masscan -p80 {RED} --rate 2000 --wait 2", wpm=42, typos=0.01, seed=4)
        v.ssh("xdotool key Return")
        verificar(v.waitfor("open port 80", 25), "el escaneo de puerto 80 no encontró nada")
        time.sleep(4)

        v.mark("Acto 4: guardamos el resultado")
        clear_and_focus(RECT, "escaneo final con -oL, limpio y arriba del todo")
        v.type_in(term, f"sudo masscan -p80 {RED} --rate 2000 --wait 2 -oL {ARCHIVO_RESULTADO}",
                  wpm=42, typos=0.01, seed=5)
        v.ssh("xdotool key Return")
        time.sleep(6)                                                  # deja correr el escaneo + su espera final
        # el momento más importante del vídeo (el resultado guardado) no puede quedar enterrado bajo el
        # escaneo anterior: Ctrl+L + focus_rect ANTES de teclear, igual que antes de cada comando clave
        # (METODOLOGIA/10 §3.3) — pedido explícito del usuario tras ver la toma: que salga arriba del todo.
        clear_and_focus(RECT, "resultado guardado, limpio y arriba del todo")
        v.type_in(term, f"cat {ARCHIVO_RESULTADO}", wpm=42, typos=0.01, seed=6)
        v.ssh("xdotool key Return")
        verificar(v.waitfor("open tcp 80", 8), "el fichero guardado no tiene resultados")
        time.sleep(4)
        v.mark("Cierre")
    finally:
        v.take_end()

    script = os.path.join(SHORTS, "short_desde_toma.py")  # ruta del repo: nucleo/rutas.py
    import subprocess
    subprocess.run([sys.executable, script, nombre,
                    "--titulo", "Asi-Escaneo-Toda-Mi-Red-Wifi-En-Segundos-Con-Masscan"], check=True)


if __name__ == "__main__":
    main()
