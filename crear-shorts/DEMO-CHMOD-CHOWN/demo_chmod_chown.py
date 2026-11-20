#!/usr/bin/env python3
"""
demo_chmod_chown.py — Demo COMPLETA dentro de la VM: permisos de Linux de la forma más básica e intuitiva
posible: una carpeta y un documento de texto normales, y lo que pasa de verdad al leerlos/escribirlos/
entrar en ellos según cambian sus permisos (`chmod` con letras, `chmod` con números, `chown`).

    python demo_chmod_chown.py [nombre_toma]        (def. chmod-chown-AAAAMMDD-HHMM)

Marco ético: no hay objetivo remoto ni laboratorio de terceros — todo ocurre sobre una carpeta y un
documento propios, creados y borrados dentro de la propia VM del usuario (~/carpeta-permisos). Nada de
scripts ni de sintaxis avanzada (sin `stat -c`, sin comandos encadenados con `&&`): cada paso es un
comando suelto y su efecto se ve intentando leer/escribir/entrar de verdad. Ver 00-recon.md.

Si la VM sigue en modo puente de una demo de red anterior (p. ej. DEMO-MASSCAN), exporta
VM_HOST=<IP real> VM_SSH_PORT=22 antes de lanzar este script (y cualquier otro comando de vm_control.py):
esta demo no usa la red para nada, pero el CANAL de control sí depende de cómo esté el adaptador ahora.

Hace: limpiamos (NO grabado) → una terminal centrada → grabación → Acto 1 (creamos la carpeta y el
documento, y lo leemos) → Acto 2 (chmod con letras: cuando NO se puede leer) → Acto 3 (chmod con letras:
cuando NO se puede escribir) → Acto 4 (chmod con números: el mismo permiso, como una suma) → Acto 5 (las
carpetas también tienen permisos: hace falta "x" para poder entrar) → Acto 6 (chown: cambiar el
propietario, y por qué eso también puede dejarte sin acceso) → trae el .mp4, el .steps.jsonl y el mapa de
edición .mapa.md. Cada paso se verifica intentando la acción real (texto leído, o "Permission denied").
Entrada humana siempre (vm_control.type_in/move/click).
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramientas"))
import vm_control as v  # noqa: E402  (también pone nucleo/ en el path)
from nucleo.rutas import SHORTS  # noqa: E402

CARPETA = "carpeta-permisos"
DOC = "notas.txt"
TEXTO_1 = "Hola, esto es un documento de prueba."
TEXTO_2 = "Ahora si puedo escribir."

# Una sola terminal, medio ancho y CENTRADA (no a pantalla completa): a pantalla completa (1920x973,
# ~2:1) el letterbox del Short vertical solo llena el 43% del alto bajo la banda de la cara ("se ve
# pequeño", medido en la primera toma de DEMO-MASSCAN); a medio ancho (960x973, centrada) llena el 86%
# (METODOLOGIA/10 §3.2b). Fuente del terminal ya comprobada a 24pt en esta VM.
RECT = (480, 39, 960, 973)

# Pausa mínima tras CADA Return antes de teclear el siguiente comando (no solo entre actos): medido en
# esta sesión que con 0,3 s el siguiente `type_in` puede empezar antes de que el terminal haya acabado de
# procesar el anterior, y el comando sale mal tecleado (el que lo sufrió: una comprobación OCR que debía
# dar verdadero dio falso 5 de 5 veces seguidas). Con >=1 s no ha vuelto a fallar.
PAUSA = 1.2


def focus_rect(rect, why):
    x, y, w, h = rect
    v.focus(x + w // 2, y + h // 2, why, w=w, h=h)


def clear_and_focus(rect, why):
    """Limpia la terminal (Ctrl+L, instantáneo) y fija el foco en `rect`: el siguiente comando sale solo,
    arriba del todo, en vez de enterrado bajo el resultado del paso anterior (METODOLOGIA/10 §3.3). Se usa
    una vez al EMPEZAR cada acto (pantalla limpia por concepto) y también sirve para volver al rect
    completo tras un `waitfor()` dentro del mismo acto (METODOLOGIA/10 §3.4)."""
    v.ssh("xdotool key ctrl+l")
    time.sleep(0.3)
    focus_rect(rect, why)


def comando(term, texto, wpm=44, typos=0.012, seed=0):
    """Teclea UN comando suelto, Enter, y la pausa mínima antes de que se pueda teclear otro (ver PAUSA)."""
    v.type_in(term, texto, wpm=wpm, typos=typos, seed=seed)
    v.ssh("xdotool key Return")
    time.sleep(PAUSA)


def verificar(ok, msg):
    if not ok:
        v.die("VERIFICACIÓN FALLIDA: " + msg)


def modo_real(ruta):
    """Permiso real del fichero, leído por el canal de control (NUNCA tecleado en pantalla: `stat` es
    sintaxis que el usuario pidió explícitamente no mostrar). Se usa solo para verificar `chmod` con
    números: una racha larga de guiones ("rw-------") es ilegible para Tesseract aunque se vea perfecta en
    el vídeo real (medido esta sesión: con Fira Code los guiones se fusionaban en una línea por la
    ligadura de la fuente — ya cambiada a DejaVu Sans Mono — y aun sin ligadura, Tesseract sigue leyendo
    una racha de 5+ guiones como ruido en vez de guiones sueltos). `ls -l` en pantalla sigue siendo la
    prueba real para quien mira el vídeo; esto solo confirma que el paso no haya fallado de verdad."""
    return v.ssh(f"stat -c '%a' ~/{CARPETA}/{ruta}", capture=True).strip()


def preparar_entorno():
    """Deja la carpeta de pruebas limpia ANTES de grabar (Fase 0): así la toma es repetible."""
    v.ssh(f"rm -rf ~/{CARPETA}", check=False)


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("chmod-chown-%Y%m%d-%H%M")

    print("preparando el entorno (sin grabar)...")
    preparar_entorno()

    term = v.launch_terminal("Permisos")
    v.place_id(term, *RECT)
    v.activate_id(term)

    v.take_start(nombre)
    v.rec_start()
    focus_rect(RECT, "inicio: terminal centrada")   # ANTES del primer mark (METODOLOGIA/10 §3.5)
    s = 0  # semilla de tecleo: distinta en cada comando para que el "humano" no teclee siempre igual

    def sig():
        nonlocal s
        s += 1
        return s

    try:
        v.mark("Acto 1: creamos la carpeta y el documento, y lo leemos")
        clear_and_focus(RECT, "Acto 1, pantalla limpia")
        comando(term, f"mkdir {CARPETA}", seed=sig())
        comando(term, f"cd {CARPETA}", seed=sig())
        comando(term, f"echo '{TEXTO_1}' > {DOC}", seed=sig())
        comando(term, f"ls -l {DOC}", seed=sig())
        time.sleep(1.5)                                             # pausa de lectura: permisos por defecto
        comando(term, f"cat {DOC}", seed=sig())
        verificar(v.waitfor("documento de prueba", 8), "no se pudo leer el documento recién creado")
        time.sleep(3)

        v.mark("Acto 2: chmod con letras — cuando NO se puede leer")
        clear_and_focus(RECT, "Acto 2, pantalla limpia")
        comando(term, f"chmod u-r {DOC}", seed=sig())
        comando(term, f"cat {DOC}", seed=sig())
        verificar(v.waitfor("Permission denied", 8), "quitar la lectura (u-r) no bloqueó la lectura")
        time.sleep(3)                                               # momento importante: el bloqueo
        focus_rect(RECT, "de vuelta al rect completo tras el waitfor (METODOLOGIA/10 §3.4)")
        comando(term, f"chmod u+r {DOC}", seed=sig())
        comando(term, f"cat {DOC}", seed=sig())
        verificar(v.waitfor("documento de prueba", 8), "devolver la lectura (u+r) no la restauró")
        time.sleep(2)

        v.mark("Acto 3: chmod con letras — cuando NO se puede escribir")
        clear_and_focus(RECT, "Acto 3, pantalla limpia")
        comando(term, f"chmod u-w {DOC}", seed=sig())
        comando(term, f"echo '{TEXTO_2}' >> {DOC}", seed=sig())
        verificar(v.waitfor("Permission denied", 8), "quitar la escritura (u-w) no bloqueó el añadido")
        time.sleep(3)
        focus_rect(RECT, "de vuelta al rect completo tras el waitfor (METODOLOGIA/10 §3.4)")
        comando(term, f"chmod u+w {DOC}", seed=sig())
        comando(term, f"echo '{TEXTO_2}' >> {DOC}", seed=sig())
        comando(term, f"cat {DOC}", seed=sig())
        verificar(v.waitfor("Ahora si puedo escribir", 8), "devolver la escritura (u+w) no la restauró")
        time.sleep(2)

        v.mark("Acto 4: chmod con números — el mismo permiso, como una suma")
        clear_and_focus(RECT, "Acto 4, pantalla limpia")
        comando(term, f"chmod 644 {DOC}", seed=sig())
        comando(term, f"ls -l {DOC}", seed=sig())
        verificar(modo_real(DOC) == "644", "chmod 644 no dejó el documento en 644")
        time.sleep(3)                                               # pausa: dueño lee/escribe, el resto solo lee
        comando(term, f"chmod 600 {DOC}", seed=sig())
        comando(term, f"ls -l {DOC}", seed=sig())
        verificar(modo_real(DOC) == "600", "chmod 600 no dejó el documento en 600")
        time.sleep(3)                                               # momento importante: "privado"

        v.mark('Acto 5: las carpetas también tienen permisos — hace falta "x" para entrar')
        clear_and_focus(RECT, "Acto 5, pantalla limpia")
        comando(term, "cd ..", seed=sig())
        comando(term, f"chmod u-x {CARPETA}", seed=sig())
        comando(term, f"cd {CARPETA}", seed=sig())
        verificar(v.waitfor("Permission denied", 8), "quitar la x a la carpeta no bloqueó el cd")
        time.sleep(3)
        focus_rect(RECT, "de vuelta al rect completo tras el waitfor (METODOLOGIA/10 §3.4)")
        comando(term, f"chmod u+x {CARPETA}", seed=sig())
        comando(term, f"cd {CARPETA}", seed=sig())
        comando(term, "pwd", seed=sig())
        verificar(v.waitfor(CARPETA, 8), "devolver la x a la carpeta no permitió volver a entrar")
        time.sleep(2)

        v.mark("Acto 6: chown — cambiar el propietario (y por qué también importa)")
        clear_and_focus(RECT, "Acto 6, pantalla limpia")
        comando(term, f"ls -l {DOC}", seed=sig())
        time.sleep(2)                                               # se ve: dueño kali, modo 600 de antes
        comando(term, f"sudo chown root {DOC}", seed=sig())
        comando(term, f"cat {DOC}", seed=sig())
        verificar(v.waitfor("Permission denied", 8),
                  "cambiar el dueño a root no bloqueó la lectura (debería, con permiso 600)")
        time.sleep(4)                                               # momento clave: ya no soy el dueño
        focus_rect(RECT, "de vuelta al rect completo tras el waitfor (METODOLOGIA/10 §3.4)")
        comando(term, f"sudo chown kali {DOC}", seed=sig())
        comando(term, f"cat {DOC}", seed=sig())
        verificar(v.waitfor("documento de prueba", 8), "devolver el dueño a kali no restauró la lectura")
        time.sleep(3)
        v.mark("Cierre")
    finally:
        v.take_end()

    print("limpiando la máquina (fuera de grabación)...")
    v.ssh(f"rm -rf ~/{CARPETA}", check=False)

    script = os.path.join(SHORTS, "short_desde_toma.py")  # ruta del repo: nucleo/rutas.py
    import subprocess
    subprocess.run([sys.executable, script, nombre,
                    "--titulo", "Permisos-En-Linux-De-Verdad-Chmod-Con-Letras-Numeros-Y-Chown"],
                   check=True)


if __name__ == "__main__":
    main()
