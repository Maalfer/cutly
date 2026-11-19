# 08 — Controlar una máquina virtual (VirtualBox) en vez del anfitrión

> Alternativa a conducir el ordenador real: la IA maneja un **Kali Linux dentro de VirtualBox** y se graba
> la ventana de la VM. Este documento recoge lo **medido** probándolo (VirtualBox 7.2.22 en un Mac con
> Apple Silicon, invitado Kali ARM64 con XFCE/X11; probado primero en un clon y repetido después en la VM
> `kali` original, con los mismos resultados). Comparación con el anfitrión al final.
>
> Código: `herramientas/vm_control.py` (reutiliza `tipear.py` y `mover.py`; solo cambia el emisor).

---

## 1. Qué canal sirve para qué (medido)

| Necesidad | Canal | Veredicto |
|---|---|---|
| **Ver la pantalla** | `VBoxManage controlvm VM screenshotpng f.png` | ✅ **0,08 s**, sin permisos del anfitrión, independiente de qué haya en el Mac |
| **Teclear texto** | `VBoxManage controlvm VM keyboardputstring` | ❌ **corrompe el texto**: asume teclado US. Con otra distribución se perdían comillas, `\|`, `~`, `?` y todas las tildes (`echo "ñandú á é ü € ¿ok? \| ~ $HOME"` llegó como `echo änd ok_ Ç ª $HOME`) |
| **Teclas sueltas** | `keyboardputscancode` | ✅ funciona (abrió un terminal con `Ctrl+Alt+T`), pero con errores esporádicos de envío |
| **Mover/clicar el ratón** | `VBoxManage` | ❌ **no existe ningún comando de ratón** en `controlvm` |
| **Ratón + teclado reales** | **`xdotool` dentro del invitado, por SSH** | ✅ ver §2 |
| **Ejecutar comandos / copiar ficheros** | SSH (`natpf` 2222→22) + `scp` | ✅ rápido y sin depender del teclado. Es el canal `ssh` de `vm/canales/` |
| **Lo mismo SIN SSH** | `VBoxManage guestcontrol` (Guest Additions) con la contraseña que da el usuario | canal `guestcontrol` de `vm/canales/` (`VM_CANAL`); implementado y probado en simulación, **pendiente de medir** contra la VM |
| **Grabar vídeo** | **grabación nativa de VirtualBox en el anfitrión** (`vm_control.py rec start`) | ✅ medido: cursor incluido, sin SSH. Alternativa: `rec start --guest` (`ffmpeg -f x11grab` dentro del invitado) |
| **Resolución** | `controlvm setvideomodehint W H bpp` (`vm_control.py res W H`) | para fijar el formato del short antes de grabar |

**Conclusión:** VirtualBox da el *ojo* (captura) y la *puerta* (SSH/puertos), pero **no el teclado ni el ratón**
de forma fiable. El control real se hace con `xdotool` dentro del invitado.

---

## 2. El control que sí funciona: `xdotool` por SSH (resultados)

Montaje (una vez, en el invitado): sesión X11 con `xdotool` instalado (Kali XFCE ya lo trae) y una clave SSH
autorizada. Para autorizarla sin contraseña se escribió la línea de `authorized_keys` en un terminal del
invitado **tras poner temporalmente el teclado en US** (`setxkbmap us`, que solo usa letras): así
`keyboardputstring` ya no corrompe símbolos. Se usó una **clave dedicada y nueva**, no la clave personal.

| Prueba | Resultado |
|---|---|
| Posición del cursor y movimiento a 5 destinos | **5/5 exactos**, incluido uno a 1 px |
| Trayecto de ratón humano (curvo, lento-rápido-lento) | 1,38 s para 1.300 px |
| Clic en un icono del panel → se lanza Firefox | ✅ |
| Teclear una URL con ritmo humano y errores simulados | ✅ la página cargó |
| Texto con `ñandú á é ü € ¿ok? \| ~ $HOME "q" 's' \n`, 3 % de errores, **comparación exacta** | ✅ **idéntico** (tras los dos arreglos de §3) |
| Burp Suite (Java ARM) arranca en el invitado | ✅ (~1,4 GB de RAM en una VM de 4 GB); **pendiente aceptar su EULA** (decisión del usuario) |
| `curl "…" \| grep -o …` tecleado en el terminal y su salida leída por OCR | ✅ |
| **Fiabilidad:** 10 repeticiones de "teclear URL (3 % de errores) → Enter → verificar por OCR el usuario cargado" | **10/10**, 10,5 s de media por iteración |

Los trayectos y el ritmo son los **mismos planes** que en macOS (`mover.trayecto`, `tipear.plan`); solo cambia
el emisor (`xdotool` en vez de `teclear` Swift). Así la regla "entrada humana siempre" (doc 04) se mantiene.

---

## 3. Fallos hallados (continúa la numeración del doc 07)

| # | Fallo | Causa | Arreglo |
|---|---|---|---|
| 37 | `keyboardputstring` corrompía símbolos y tildes | Asume teclado US; el invitado tenía otro | No usarlo para texto. Para el arranque, `setxkbmap us` y luego sí; el control real va por `xdotool` |
| 38 | `xdotool type` perdía **todas** las tildes, `ñ`, `€`, `¿` ("Invalid multi-byte sequence") | La sesión SSH no tenía **locale UTF-8** | `export LC_ALL=C.UTF-8 LANG=C.UTF-8` en cada llamada (`vm_control.ssh`) |
| 39 | Con UTF-8, los caracteres no ASCII **seguían desapareciendo** con `--delay 0` (incluso uno a uno) | xdotool reasigna una tecla al vuelo y, si el proceso termina enseguida, **restaura el teclado antes de que la app lea la tecla** | `--delay 40` solo para caracteres no ASCII (con ≥ 30 ms acierta; con 0 falla siempre) |
| 40 | Un `cat > fichero` interrumpido por un error dejó el terminal **esperando entrada** y las órdenes siguientes se perdieron | Estado residual del terminal tras abortar una prueba | Mirar la captura antes de suponer; resetear con `Ctrl+C`/`Ctrl+D` |
| 41 | Una línea de `chmod` a mitad de comando salió **truncada** ("authori…") | `keyboardputscancode` devolvió "Failed to send a scancode" y se perdió parte del texto | Confirmar el resultado (aquí SSH funcionó porque la línea de la clave sí llegó); no fiarse del envío ciego |
| 42 | El tooltip "Firefox ESR" se quedó en pantalla | El cursor se quedó sobre el icono tras clicar | Apartar el ratón tras clicar (también en el anfitrión) |

---

## 4. Seguridad y decisiones que NO son de la IA

- **EULA de Burp:** en el invitado, el primer arranque pide aceptar los Términos y Condiciones. **Un agente no
  debe aceptar acuerdos legales por el usuario**: se dejó pendiente.
- **Contraseñas:** SSH pedía contraseña y la clave del anfitrión no estaba autorizada. **No se probaron ni
  adivinaron contraseñas.** Se usó la sesión ya iniciada del escritorio del propio invitado.
- **Se clonó la VM** (`VBoxManage clonevm kali --name kali-demo`) y se trabajó solo sobre el clon; la VM
  original no se tocó.

---

## 5. ¿VM o anfitrión? Comparación medida

| | **Anfitrión (macOS)** | **VM (Kali, X11)** |
|---|---|---|
| Fallos encontrados hasta dejarlo estable | **36**, casi todos por **interferencias del propio ordenador**: foco robado, overlays, diálogos de permisos, perfil personal, ventanas apiladas, autocompletado del historial | **6** (nº 37-42), todos **de montaje** (teclado/locale/ratón), resueltos una sola vez en `vm_control.py` |
| Fiabilidad al repetir | no medida con repeticiones | **10/10** a la primera |
| ¿Puede el usuario usar su ordenador mientras tanto? | **No** (un solo cursor y teclado) | **Sí** (la VM tiene los suyos) |
| Notificaciones, permisos, perfil personal en el vídeo | hay que vigilarlos (gate, perfil limpio, evitar `tell application`) | **no existen** dentro de la VM |
| Captura de pantalla | `screencapture` (~0,3 s) + permiso de grabación | `screenshotpng` **0,08 s**, sin permisos |
| Montaje inicial | enseguida (ya estaba el kit) | más trabajo: SSH, locale, `xdotool`, sin API de ratón |
| Qué demos admite | **macOS** (ClickFix de Mac, Safari, Terminal de Mac) | **Linux/Kali**: pentesting, Burp, navegador, comandos. Un invitado **macOS no es posible** aquí; Windows requeriría otro emisor |
| Dependencia del sistema anfitrión | un kit por SO (macOS, Windows, Linux) | **`VBoxManage` + `ssh`**, iguales en los tres; el control en sí no cambia de un anfitrión a otro |
| Sesión gráfica | cualquiera | **X11** (con Wayland `xdotool` no funcionaría) |

**Veredicto:** para demostraciones de **ciberseguridad con herramientas de Kali** (navegador, Burp, terminal,
laboratorios), la VM es **más fiable y más cómoda de operar**, aunque **algo más costosa de montar una vez**.
No es "mucho más fácil" en todo: el montaje tiene sus trampas (nº 37-42) y hay demos que solo existen en el
anfitrión (las de macOS). Lo razonable es un **enfoque mixto**: VM para Kali, anfitrión para lo específico de
macOS y, en el futuro, una VM Windows para lo de Windows.

### Sin verificar todavía
- **Burp dentro de la VM de punta a punta** (bloqueado por el EULA).
- **Grabación:** OBS sobre la ventana de la VM, o `controlvm recording`; y si el **cursor** del invitado
  aparece en esa grabación.
- **Snapshots:** una toma *en caliente* con 4 GB de RAM llevaba más de 4 minutos (se canceló por indicación del
  usuario, que no quiere snapshots). No se midió restaurar.
- **Windows** (`Win11-25H2`) como invitado, y Wayland.

---

## 6. Cambios posteriores (diseño, no mediciones)

- **Línea de tiempo sin deriva.** Antes el plan era un bash con `sleep` encadenados: el tiempo de cada `xdotool` se
  acumulaba. Ahora el plan se compila a una línea de tiempo absoluta y un reproductor Python **en el invitado** la
  ejecuta (una sola conexión SSH por plan; en Windows no hay `ControlMaster`). La posición del cursor se recuerda en
  el anfitrión para no consultar al invitado antes de cada movimiento.
- **Registro y mapa de edición** (`take`, `mark`, `rec`): cada paso queda en JSONL con su hora; el mapa de edición se
  genera solo. Conecta la Fase 1 con la Fase 2.
- **Verificación sin OCR:** `labcheck` (el lab imprime cada petición) y `waitstill` (pantalla asentada).
  `clickimg` (OpenCV) para botones que el OCR no lee.
- **Estado de partida:** `suspend`/`resume` usan `savestate` (no es snapshot ni copia).
- **Montaje:** regla NAT añadida con `modifyvm --natpf1` (VM apagada); clave instalada con `guestcontrol` si el usuario
  da la contraseña (`VM_GUEST_PASS`), si no, tecleándola con el teclado en US (solo letras).
- **Anfitrión Windows:** bytes con `
` en la entrada de SSH (con `text=True` llegaban `
`), `VBoxManage` localizado
  fuera del PATH, Tesseract en su ruta de instalación. Ver `PORTABILIDAD.md` §1.
- **Sin implementar (candidatos):** Marionette/Playwright para Firefox (sin MCP en ningún caso: regla del proyecto);
  AT-SPI/`dogtail` para apps GTK. Se evaluarán cuando el flujo base esté medido en Windows.

> Estos cambios **no están medidos todavía en Windows/x86**: la tabla de resultados de arriba es del Mac/ARM.
