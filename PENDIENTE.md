# Estado y trabajo pendiente (leer al retomar)

> Escrito al cerrar la sesión del 2026-11-18. El repo está **a medio migrar**: la decisión ya tomada es que
> **todas las demos se graban dentro de una VM de VirtualBox (Kali) y nunca en el anfitrión**, pero la
> documentación sigue describiendo mayoritariamente el control del anfitrión macOS.

## Decisiones del usuario (vigentes)
- **Siempre VirtualBox** para grabar demos; no se usará el anfitrión. Quitar de la documentación todo lo de macOS.
- No hacer copias ni snapshots de la VM `kali` (se trabaja directamente en ella; no hay nada delicado).
- El clon `kali-demo` ya se **eliminó**. El EULA de Burp se **aceptó** (autorizado por el usuario) y se eligió Community.
- La IA debe ser quien actúe y se mueva; el usuario solo graba con OBS.
- Entrada humana (tecleo y ratón realistas) siempre que se grabe.

## Qué funciona (verificado en la VM `kali`, Kali ARM64, VirtualBox 7.2.22, Apple Silicon)
- `crear-shorts/herramientas/vm_control.py`: captura (0,08 s), ratón (5/5 exacto), tecleo humano idéntico con tildes y
  símbolos, `typeurl`, `selecttext`, `clicktext`, `waitfor`, `activate`, `place`, `start/stop/status/bootstrap/prepare`.
- Control por **SSH + xdotool** (clave dedicada en `~/.ssh/cutly_vm`, redirección 2222→22). `VBoxManage keyboardputstring`
  corrompe el texto y no hay comando de ratón: no usarlos para teclear.
- Fiabilidad medida: 10/10 repeticiones de "teclear URL y verificar por OCR".
- Entorno persistente en la VM: perfil Firefox `demo` (proxy a Burp, sin autocompletado ni tráfico de fondo, en
  `~/.mozilla/firefox-demo/user.js`), lab en `~/lab/lab_idor.py`, salvapantallas/bloqueo desactivados, no molestar.
- Cadena **Firefox → Burp → lab verificada** (el historial de Burp muestra `GET /cuenta?id=1001`).

## Pendiente (en este orden)
1. **Reescribir la documentación solo para la VM** y **borrar lo del anfitrión**: `METODOLOGIA/01-03`, `07` (parte macOS),
   `PORTABILIDAD.md` (kit por SO), `DEMO-CLICKFIX/`, y las herramientas `mac-control.sh`, `teclear.swift`, `winlist.swift`,
   `visibilidad.py`, `mousepos.swift`, `find_button.py`. Reducir `tipear.py`/`mover.py` a generadores de plan (sin emisor macOS).
   Crear `METODOLOGIA/00-empezar-aqui-vm.md` (montaje único, protocolo de toma, referencia de comandos) y adaptar 04/05/06 y `DEMO-IDOR`.
   Un `CLAUDE.md` en la raíz con la regla "todo en la VM". (Fuera del repo: `~/Desktop/ctrl-kit` y `~/Desktop/clickfix-demo`
   son restos del anfitrión; preguntar antes de borrarlos.)
2. **Arreglar `vm_control.py prepare`** (deja la VM lista: lab + Burp + Firefox). Última sesión: la lógica de `burp_up`
   tenía falsos éxitos y problemas de orden de ventanas; se corrigió varias veces pero **no llegó a verificarse de punta a punta**.
   Estado en que se dejó la VM: Burp mostrando el aviso "Delete old temporary files?". Reintentar desde cero.
3. **Investigar una forma mejor de controlar la VM** (petición del usuario, sin empezar): candidatos a evaluar —
   API Main de VirtualBox (`IMouse.putMouseEventAbsolute`, `IKeyboard`) vía `vboxapi`; VNC con `vncdotool`; accesibilidad AT-SPI
   (`dogtail`) y Java Access Bridge para Burp; Playwright/Marionette para Firefox; el **servidor MCP de Burp** (hay una pestaña
   "MCP" en Burp 2026) para manejar Burp sin OCR; búsqueda de imágenes (OpenCV/SikuliX) para botones que el OCR no lee.
4. Primer **guion con comprobaciones** del ejercicio IDOR y medir fiabilidad con 10-20 repeticiones.
5. Sin verificar: grabación de la ventana de la VM con OBS (¿sale el cursor del invitado?), Windows como invitado
   (`Win11-25H2`), Wayland, snapshots (descartados por el usuario).

## Lecciones recientes (VM)
- Vision (macOS) lee botones de interfaz que Tesseract no encuentra; **ningún OCR lee texto claro sobre botones de color**
  (p. ej. "I Accept"): ahí manda la visión (coordenada vista en la captura) más verificación.
- Enter no activa los botones de los diálogos Swing de Burp: clic verificado por OCR.
- Un aviso modal tapa el diálogo de debajo pero el OCR sigue viendo su texto: tratar siempre primero el modal.
- Comprobar el nombre de una ventana no basta (los diálogos se llaman casi igual que la ventana principal).
- Un script que "informa" sin verificar da falsos éxitos: terminar siempre con una comprobación que falle de verdad.
