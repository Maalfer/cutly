#!/usr/bin/env python3
"""
demo_idor.py — Demo IDOR COMPLETA dentro de la VM: Firefox + Burp Suite contra el lab local (127.0.0.1:8765).

    python demo_idor.py [nombre_toma]        (def. idor-AAAAMMDD-HHMM)

Hace: prepare → grabación → Acto 1 (login legítimo, id=1001) → Acto 2 (Burp intercepta, Repeater, 1001→1002,
Send) → Acto 3 (lo mismo SIN Burp) → trae el .mp4, el registro .steps.jsonl y el mapa de edición .mapa.md.
Cada paso se verifica (log del lab y/o OCR); si uno falla, se detiene y queda marcado en el mapa.
Graba con VirtualBox (en el anfitrión, sin OBS ni nada dentro de la VM) y al final genera el Short 1080x1920 con la
banda negra superior fija (editor/shorts/short_desde_toma.py).
Todo es entrada humana (vm_control.type/move/click). Solo contra el lab propio.
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramientas"))
import vm_control as v  # noqa: E402  (también pone nucleo/ en el path)
from nucleo.rutas import SHORTS  # noqa: E402

LAB = "http://127.0.0.1:8765/cuenta?id="
BURP = "Temporary Project"
FF = "Mozilla Firefox"
TOGGLE = (0, 250, 300, 70)          # interruptor "Intercept on/off" (pestaña Proxy > Intercept)
SEND = (0, 270, 100, 70)            # botón Send de Repeater
FORWARD = (240, 255, 220, 60)       # botón Forward de Proxy > Intercept


def verificar(ok, msg):
    if not ok:
        v.die("VERIFICACIÓN FALLIDA: " + msg)


def intercept(estado):
    """Deja el interruptor en 'on'/'off' (comprueba antes y después por OCR)."""
    v.activate(BURP)
    v.clicktext("Proxy", reg=(200, 120, 120, 40))
    v.waitstill(4)
    actual = v._words_text(region=TOGGLE, thorough=True)
    if f"intercept {estado}" in actual:
        return
    v.clicktext("off" if estado == "on" else "on", reg=TOGGLE)
    verificar(v.waitfor(f"intercept {estado}", 5, region=TOGGLE), f"el interruptor no quedó en '{estado}'")


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("idor-%Y%m%d-%H%M")
    v.prepare()
    intercept("off")
    v.activate(FF)

    v.take_start(nombre)
    v.rec_start()
    try:
        # ---- Acto 1: la víctima ve SUS datos
        v.mark("Acto 1: usuarioA ve su cuenta (id=1001)")
        v.activate(FF)
        v.typeurl(LAB + "1001", in_title=FF)
        verificar(v.labcheck("GET /cuenta?id=1001"), "el lab no recibió id=1001")
        verificar(v.waitfor("usuarioA", 8), "no se ve 'usuarioA'")
        time.sleep(3)                                              # pausa de lectura

        # ---- Acto 2: Burp intercepta y se manipula el id
        v.mark("Acto 2: Burp intercepta la petición")
        intercept("on")
        v.activate(FF)
        # ctrl+r recarga; F5 por xdotool se perdía (medido)
        v.ssh("xdotool key ctrl+r")
        v.activate(BURP)
        verificar(v.waitfor("cuenta?id=1001", 8, region=(0, 330, 1500, 120)), "Burp no interceptó la petición")
        time.sleep(2)
        v.mark("Acto 2b: a Repeater, 1001 -> 1002")
        v.ssh("xdotool key ctrl+r")                                 # Send to Repeater
        time.sleep(0.8)
        v.clicktext("Forward", reg=FORWARD)                         # libera la petición retenida
        intercept("off")
        v.clicktext("Repeater", reg=(300, 120, 200, 40))
        verificar(v.waitfor("Send", 6, region=SEND), "Repeater no abrió")
        v.selecttext("1001", reg=(0, 440, 750, 30))      # el 1001 de la 1.ª línea de la petición
        v.type_human("1002", wpm=40, typos=0)
        verificar(v.waitfor("id=1002", 5, region=(0, 440, 750, 40)), "el id no quedó en 1002 en la petición")
        time.sleep(1.5)                                             # pausa dramática antes de enviar
        v.mark("Acto 2c: Send -> datos de usuarioB (IDOR)")
        v.clicktext("Send", reg=SEND)
        verificar(v.waitfor("usuarioB", 8), "la respuesta no contiene 'usuarioB'")
        verificar(v.labcheck("GET /cuenta?id=1002"), "el lab no recibió id=1002")
        time.sleep(4)

        # ---- Acto 3: sin Burp, directamente en el navegador
        v.mark("Acto 3: lo mismo sin Burp, en la barra del navegador")
        v.activate(FF)
        v.typeurl(LAB + "1002", in_title=FF)
        verificar(v.waitfor("usuarioB", 8), "el navegador no muestra 'usuarioB'")
        time.sleep(3)
        v.mark("Cierre")
    finally:
        v.take_end()

    # ---- Edición automática: Short vertical con la banda negra superior fija para la cara del usuario
    import subprocess
    script = os.path.join(SHORTS, "short_desde_toma.py")  # ruta del repo: nucleo/rutas.py
    subprocess.run([sys.executable, script, nombre, "--titulo", "Demo-IDOR-Cambiando-El-Id-Para-Ver-Datos-De-Otro-Usuario"], check=True)


if __name__ == "__main__":
    main()
