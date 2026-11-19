# 09 — Conducir CUALQUIER app de Kali desde la VM (guía general + fichas)

> Lo aprendido haciendo la demo IDOR que **no es específico del IDOR**: sirve para nmap, Wireshark, Metasploit,
> sqlmap, un editor… Las fichas por app (§5) guardan lo propio de cada herramienta. Sin MCP ni APIs de la app:
> solo pantalla, ratón y teclado de la VM (regla del proyecto).

## 1. Bucle universal: mirar → actuar → verificar
1. **Mirar** (`shot` + leer la imagen; `windows`). Nunca asumir el estado.
2. **Actuar** con entrada humana (`clicktext`, `type`, `key`).
3. **Verificar** con algo que pueda fallar, de más a menos fiable: log/salida real (`labcheck`, `run "cmd"`),
   texto en pantalla (`waitfor`), imagen (`clickimg`), y siempre mirar la captura si hay duda.

## 2. Primera sesión con una app nueva (reconocimiento, sin grabar)
- Lanzar (`launch`), `waitstill`, captura. Anotar: título de ventana, **modales de arranque**, regiones fiables
  (barra de menús, botones principales) y textos que el OCR lee bien.
- Probar cada acción 2-3 veces. Anotar lo que falla y por qué. Guardar una **ficha** (§5).
- Terminales/CLI: preferible conducir por teclado y verificar por la salida (`type` + `waitfor`).

## 3. Reglas aprendidas (medidas en esta VM)
| Problema | Causa | Regla / herramienta |
|---|---|---|
| El OCR no lee "Next", "Send" (texto claro sobre botón de color) | Contraste en gris insuficiente | 2.ª pasada automática en **canal mínimo RGB ×2**, recortada a la región. `clicktext` y `waitfor` la usan solos |
| `clicktext "Intercept"` pulsó otra cosa | La palabra se repite (pestaña y botón) | **`--region x,y,w,h`** (y `n=-1` para la última). Acotar siempre que haya repetidas |
| Filas de tabla pequeñas no se leen | Fuente pequeña | `waitfor "texto" --region` (prueba pasada normal y reforzada) |
| Un modal bloquea el foco ("out of date") | Aparece segundos DESPUÉS de abrir | `dismiss` (tabla `MODALES`) con clic verificado; añadir cada modal nuevo a la tabla |
| `waitstill` nunca terminaba | Gráfico de CPU del panel y cursor parpadeante | Comparar por **fracción de píxeles**, ignorando la franja superior |
| `selecttext` falso éxito / fallo | Ctrl+C por xdotool no llega al portapapeles de Java; un valor viejo daba falsos éxitos | Verificar la selección **PRIMARY** de X11 (`xclip -selection primary -o`) con centinela previo. `xclip` siempre con `>/dev/null 2>&1` o retiene el SSH y cuelga el guion |
| `F5` por xdotool se perdía | — | Usar `ctrl+r` |
| Ventana con tamaño de otra máquina | Tamaños fijos | `maximize` con `wmctrl` (pantalla real) |
| `put /home/kali/x` falla en Git Bash | MSYS convierte rutas `/...` a Windows | Rutas relativas al home (`lab/x`) o `MSYS_NO_PATHCONV=1`; en PowerShell no pasa |
| Tooltips/hover en el vídeo | El cursor se queda sobre un icono | Apartar el ratón tras clicar |
| El foco no es el esperado | Diálogos casi homónimos | `--in "Título"` en `type`/`typeurl`; comprobar el título real, no solo que exista |
| `nohup cmd & disown` por SSH tarda MINUTOS en devolver el control (a veces mucho más) aunque el proceso quede bien lanzado | `disown` no crea sesión nueva: el canal SSH espera a que se cierren descriptores compartidos con la sesión | **`setsid cmd </dev/null >log 2>&1 &`** (sin `nohup`/`disown`): `ssh()` vuelve en <1s, medido. Úsalo siempre para lanzar algo en segundo plano en el invitado |
| `ssh()` se cuelga EN SILENCIO para siempre (sin CPU, bloqueado en I/O) | Ni siquiera `setsid` garantiza al 100% que el canal cierre (condición de carrera rara); sin timeout en `subprocess.run`, el guion se queda mudo | `ssh()` lleva `timeout=25` por defecto: si se agota, `die()` con el principio del script que se envió, en vez de colgarse sin avisar |
| `docker rm -f` no mata el script de despliegue (p. ej. `auto_deploy.sh`) de un lab | Solo borra el contenedor; el script sigue en su bucle `while true` esperando Ctrl+C | Antes de redesplegar: `pkill -9 -f auto_deploy.sh` además de `docker rm -f`, o se acumulan procesos colgados |
| En el Short, un comando importante "aparece muy abajo" y la terminal se ve pequeña | `focus` de región muestra la ventana ENTERA: si antes hay mucho texto (p. ej. un nmap largo), el comando nuevo queda enterrado bajo ese historial | Que no quede enterrado: `Ctrl+L` (limpia pantalla, instantáneo, no cuenta como "teclear") + `focus` ANTES de teclear → sale solo, arriba del todo. Para "se ve pequeño", ver la fila siguiente — la solución NO es estrechar el recorte por comando |
| "Se ve pequeño" en TODAS las demos, no solo una (pedido explícito: todo el vídeo debe verse grande) | El recorte letterbox de la ventana completa solo amplía ×1,125 (960→1080); probé primero estrechar el recorte a 700 px por comando (×1,54) pero exige MEDIR cada comando nuevo y falla si alguno es más largo de lo previsto | **Súbele el tamaño de letra al terminal, no estreches el recorte.** `sed -i 's/^fontSize=18/fontSize=24/' ~/.config/qterminal.org/qterminal.ini` (una vez por VM): el texto sale más grande en TODO, sin tocar ninguna geometría de recorte — lo que no cabe en una línea simplemente hace más líneas, nunca se sale de la ventana. A 24pt el rect COMPLETO ya sale más grande que el recorte estrecho de antes a 18pt. Es la palanca por defecto: sube la fuente primero y comprueba con una captura ANTES de complicarte con recortes por comando |
| HTTPS da `SEC_ERROR_UNKNOWN_ISSUER` / "Software is Preventing..." en CUALQUIER web, incluso legítima | El perfil `demo` tiene el proxy fijo a 127.0.0.1:8080 (Burp); su CA no está confiada por Firefox | Para navegación general (no-Burp) usar el perfil **`general`** (sin proxy, ver ficha). No es un aviso real del sitio: revisa primero si el perfil tiene proxy antes de desconfiar de la web |

## 4. Ritmo (fluidez en el vídeo)
- Tecleo 35-45 wpm para que se lea; ratón con trayecto curvo (`move`); pausa de lectura 3-4 s en pantallas densas y 1,5-2 s
  antes del paso "peligroso". Las esperas por OCR (1-3 s) no se notan si caen entre actos; ponlas dentro de pausas.
- Una toma = un `take start`, `mark` por acto, `rec`. Si un paso falla, el guion se detiene y el mapa lo marca: se rehace ese acto.
- Toda ejecución pasa antes **sin grabar** al menos una vez en limpio (estado de partida: `prepare`).

## 5. Fichas por app
### Firefox — DOS perfiles, no confundirlos
- **`demo`** (`~/.mozilla/firefox-demo`, lanzar `firefox --no-remote -P demo`): proxy FIJO a Burp (127.0.0.1:8080), sin
  autocompletado/sugerencias/telemetría, sin barra de marcadores. Solo para demos que pasan por Burp. Cualquier HTTPS normal
  da error de certificado aquí (la CA de Burp no está confiada) — no es un fallo del sitio.
- **`general`** (`~/.mozilla/firefox-general`, lanzar `firefox --no-remote -P general`): SIN proxy, descargas a `~/Downloads`,
  igual de limpio en telemetría/autoupdate. Úsalo para navegar sitios reales (DockerLabs, documentación, descargar labs…).
- Avisos de certificado en sitios conocidos (DockerLabs, BunkerLabs) suelen ser un **certificado propio/autofirmado del sitio**
  (`SEC_ERROR_UNKNOWN_ISSUER` sin mención a PortSwigger) — en ese caso sí es del sitio: "Advanced…" → "Accept the Risk and
  Continue" (el botón puede quedar fuera de pantalla: baja con `Page_Down` antes de buscarlo por OCR).
- URL: `typeurl` (Ctrl+L, teclea, Supr, Enter). Recargar: `ctrl+r` (F5 por xdotool se pierde).
### Burp Suite Community 2026.7 (Swing/Java)
- Título principal: "…Temporary Project". Arranque: diálogo de proyecto (Next → Start, clic con 2.ª pasada de OCR) y modal
  "Burp Suite is out of date" (`dismiss`).
- Regiones (1920×1012): pestañas principales `y≈120-165`; subpestañas Proxy `y≈190-230`; interruptor Intercept `0,250,300,70`;
  Forward `240,255,220,60`; Send de Repeater `0,270,100,70`; petición de Repeater `y≈440-640`.
- Enter no activa botones Swing: clic. `ctrl+r` en Proxy→Intercept envía a Repeater.
- Flujo IDOR completo: `DEMO-IDOR/demo_idor.py`.
### Terminal (qterminal)
`ctrl+alt+t` abre una (puede abrir pestaña nueva). Teclear con `type --in "kali@kali"`; verificar la salida con `waitfor`.
Varias terminales a la vez (p. ej. atacante + listener): dos ventanas comparten el mismo título por
defecto ("usuario@host: ~") — `vm_control.py launch_terminal("Título")` las abre y las distingue por **ID**
de ventana (estable), no por título (frágil). `fontSize` por defecto (18pt) sale pequeño en un Short: súbelo
a 24 en `~/.config/qterminal.org/qterminal.ini` (una vez por VM) — ver tabla de arriba.
### nmap
Es solo un comando de terminal: no necesita conducción especial, pero sí verificación de que terminó de
verdad, no que "parece que terminó": `waitfor("Nmap done", 25)` (el texto final de cualquier escaneo) +
`waitfor("ssh", 5)` (o el servicio que toque) para confirmar que el resultado tiene lo que buscas, no solo
que el proceso acabó. `-p-` (todos los puertos) con `--min-rate 2000` tarda ~5 s contra un solo host
Docker: no hace falta recortar el escaneo para que la toma vaya rápida.
### Docker (despliegue de laboratorios)
Ver §3 de la tabla de arriba (`docker rm -f` no mata el script de despliegue). Para desplegar una imagen
`.tar` de un laboratorio: `docker load -i archivo.tar` + `docker run -d --name X imagen` + `docker inspect
-f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' X` para la IP — los tres EN PRIMER PLANO y
SÍNCRONOS, nunca el script `auto_deploy.sh` del propio laboratorio en segundo plano (ver tabla, fila de
`nohup`/`setsid`). La IP del bridge de Docker (`172.17.0.0/16` típico) es la misma red donde vive el
propio Kali (`docker0`, normalmente `172.17.0.1`): úsala para que el objetivo pueda conectar DE VUELTA al
Kali (p. ej. una reverse shell), sin tocar nada de red del anfitrión Windows/macOS.
### (añadir aquí: Wireshark, Metasploit, sqlmap… cada una con su ficha tras su primera sesión de reconocimiento)
