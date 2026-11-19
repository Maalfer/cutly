# Historial de sesiones (archivo, no leer entero cada vez)

> **Las rutas citadas son las de cada momento** (p. ej. `editor/scripts/…` hoy es `editor/shorts/`, `editor/comun/`
> o `editor/directos/`; mapa actual en `README.md`).
>
> **Esto es un archivo histórico, append-only** (añade al final de una sesión a otra; no reescribas lo
> anterior). Para el estado ACTUAL y lo pendiente de verdad, lee `../../PENDIENTE.md` (raíz del repo) — es
> deliberadamente corto. Este fichero queda como registro de CÓMO se llegó hasta ahí, útil para entender el
> porqué de una decisión, pero no hace falta leerlo entero al retomar el trabajo.

---

# Sesión 2026-11-19 (control de VM, demo sshole completa)

> Actualizado el 2026-11-19 (demo sshole, run10, dada por buena por el usuario: "está perfecto"). Decisión
> vigente: **todas las demos se graban dentro de una VM de VirtualBox, desde cualquier anfitrión**. Para una
> demo de TERMINAL (nmap/ssh/exploits) **empieza por `crear-shorts/METODOLOGIA/10-plantilla-demo-terminal.md`**
> — condensa las 10 iteraciones de esta sesión para no repetir el mismo camino de prueba y error.

## Decisiones del usuario (vigentes)
- Siempre VirtualBox para grabar; no se usa el anfitrión. La IA actúa y se mueve; el usuario solo graba (o graba la VM con `rec`).
- Sin copias ni snapshots de la VM `kali`. `suspend`/`resume` (savestate) es otra cosa y está permitido.
- EULA de Burp aceptado por el usuario (Community). Entrada humana (tecleo y ratón realistas) siempre.

## Hecho en esta sesión (código y docs; sin probar en vivo en Windows)
- `vm_control.py` reescrito y multiplataforma: localiza `VBoxManage`, Tesseract y `tempfile`; SSH en bytes (fix `\r\n`);
  reproductor de planes sin deriva en el invitado; posición del cursor cacheada.
- Registro JSONL + `mark` + `rec` (ffmpeg x11grab) + mapa de edición automático (`take`/`mark`/`rec`/`mapa`). Probado
  el registro y el mapa sin VM.
- `waitstill`, `labcheck` (el lab ahora registra cada petición), `clickimg` (OpenCV), `suspend`/`resume`, `res`.
- Regla NAT `ssh,tcp,127.0.0.1,2222,,22` añadida a la VM `kali` (x86-64). Instalados en el anfitrión Windows: Tesseract, ffmpeg.
- Docs: `00-empezar-aqui-vm.md`, `CLAUDE.md` raíz, `PORTABILIDAD.md` (sección Windows), README, 04, 08.
  Retirado lo del anfitrión macOS (docs 01-03, DEMO-CLICKFIX, mac-control, teclear, winlist, visibilidad, mousepos, find_button).

## Verificado en vivo (2026-11-19, anfitrión Windows 11, invitado Kali x86-64, VirtualBox 7.2.22)
- Montaje: regla NAT, clave SSH dedicada, xdotool/xclip/wmctrl/ffmpeg en el invitado, perfil Firefox `demo`, lab, Burp sin EULA pendiente.
- Control: ratón/tecleo humano (tildes OK), OCR Tesseract con 2.ª pasada para botones de color, `waitstill`, `dismiss` (modal de Burp),
  `selecttext` por teclado (3/3), `maximize`, `labcheck`, `prepare` (29 s en frío).
- **Demo IDOR de punta a punta** (`DEMO-IDOR/demo_idor.py`, run7): Firefox + Burp, 6 actos, 0 pasos fallidos, vídeo 1920×1012@30 con cursor
  grabado DENTRO de la VM (sin OBS) + `.steps.jsonl` + `.mapa.md`. Una ejecución limpia; fallos anteriores (run1-6) corregidos uno a uno.

## Grabación y edición automáticas (2026-11-19)
- Grabación: `rec start` usa la grabación NATIVA de VirtualBox en el anfitrión (cursor visible, sin SSH ni nada en la VM, sin OBS); resolución
  con DOS argumentos (`videores 1920 1012`). Alternativa `--guest` (ffmpeg dentro).
- Edición: `editor/scripts/short_desde_toma.py` genera el Short 1080×1920@60 mudo con banda negra superior fija (648 px) y planos que
  siguen el foco (ratón, `typeurl`, `waitfor`, `focus`). `demo_idor.py` hace el ciclo entero (run8: demo → grabación → Short, OK).
- Pendiente de afinar: el encuadre automático es un BORRADOR (sigue el cursor/texto; Burp a veces queda parcialmente recortado): usar
  `focus X Y` en los guiones o `--plan`. Sin subtítulos ni voz (la pones tú). Medir la banda exacta es imposible si el contenido de
  debajo es negro: la altura la fija el filtro `pad`.

## Demo de referencia: DEMO-SSHOLE (2026-11-19) — CERRADA, dada por buena
`crear-shorts/DEMO-SSHOLE/demo_sshole.py`: nmap + bypass SSH (CVE ficticio "sshole", musl `crypt()` con
contraseña >256 car.) + reverse shell, contra un laboratorio Docker de BunkerLabs. 10 iteraciones hasta
el OK final del usuario ("está perfecto"). Es ahora la **plantilla de código** a copiar para demos nuevas
de terminal; la metodología destilada está en `METODOLOGIA/10-plantilla-demo-terminal.md`. Resumen de lo
que se fijó (detalle en esa guía):
- Despliegue del objetivo SÍNCRONO y en primer plano (nunca el script del lab en segundo plano por SSH).
- Ventanas por ID (`launch_terminal`/`place_id`/`activate_id`), nunca por título.
- Encuadre: `focus(x,y,w,h)` con la REGIÓN completa de la ventana (letterbox, nunca recorta); `Ctrl+L` +
  `focus` antes de un comando corto importante para que no quede enterrado; **fuente del terminal a 24pt**
  (no recorte estrecho) para que todo se vea grande; cuidado con dejar una región "heredada" activa antes
  de un comando largo.
- Pausas generosas en momentos clave (p. ej. el listener se queda 4 s en pantalla, no 1,5 s).
- Memoria persistente creada: `user-mario-cutly.md` y `proyecto-cutly.md` (preferencias de Mario y
  arquitectura del repo) — se cargan solas en próximas sesiones.

## Pendiente (en este orden)
1. **Fiabilidad:** repetir una demo end-to-end 10-20 veces y medir (de momento 1 ejecución limpia por demo,
   contando solo la última iteración corregida de cada una).
2. **Sin SSH (petición del usuario):** separar `vm_control.py` en cerebro + backends intercambiables: SSH+xdotool (actual) →
   `VBoxManage guestcontrol` → API de VirtualBox (ratón absoluto/scancodes; necesario para invitado Windows). Sin probar.
   `rec` (grabación) YA no depende de SSH; el CONTROL (ratón/teclado) todavía sí.
3. `suspend`/`resume`: medir tiempos (savestate) y si las apps quedan bien al reanudar.
4. Fichas de otras apps de Kali (Wireshark, Metasploit, sqlmap…) en `METODOLOGIA/09-conducir-apps-kali.md` tras su primera sesión.
   nmap, Docker y terminal (qterminal): fichas ya abiertas.
5. Windows como invitado, Wayland. Sin MCP en ningún caso (regla del usuario).

## Lecciones (VM) — resumen; detalle completo en `METODOLOGIA/09-conducir-apps-kali.md`
- Ningún OCR lee texto claro sobre botones de color ("I Accept"): usar `clickimg` o coordenada vista + verificación.
- Enter no activa los botones de los diálogos Swing de Burp: clic verificado.
- Un modal tapa el diálogo de debajo pero el OCR sigue viendo su texto: tratar primero el modal.
- Comprobar el nombre de una ventana no basta (los diálogos se llaman casi igual que la principal).
- Un script que "informa" sin verificar da falsos éxitos: termina siempre con una comprobación que pueda fallar.
- En Windows: `text=True` en `subprocess` convierte `\n` en `\r\n` y rompe bash por SSH; usar bytes.
- `nohup cmd & disown` por SSH se cuelga minutos (a veces para siempre) con `sudo` de por medio → `setsid`, o mejor,
  ejecución síncrona en primer plano cuando sea viable.
- `vm_control.ssh()` lleva `timeout=` (antes se colgaba en silencio sin avisar).
- VirtualBox no deja cambiar resolución/fichero de grabación tras la primera vez habilitada en la sesión: fichero
  fijo reutilizado entre tomas (`rec_start()` ya lo gestiona solo).
- Encuadre del Short y "se ve pequeño": ver sección de arriba y `METODOLOGIA/10-plantilla-demo-terminal.md`.
