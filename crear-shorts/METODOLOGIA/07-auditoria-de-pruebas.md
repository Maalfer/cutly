# 07 — Auditoría de pruebas: fallos reales y protocolo para validar en cualquier sistema

> **⚠️ Vigencia:** este documento nació controlando el anfitrión macOS. Los **principios y fallos** siguen
> vigentes; los **comandos** de los ejemplos (`cliclick`, `osascript`, `type_human`…) fueron sustituidos por
> `herramientas/vm_control.py` dentro de la VM. Punto de entrada: `00-empezar-aqui-vm.md`.

> Este documento nace de **probar de verdad** la navegación (abrir apps, colocar ventanas, dar foco,
> clicar, escribir, esperar) en una máquina real y anotar **cada fallo**. Dos usos:
> 1. **Catálogo de fallos reales** y cómo se evitan (cada uno ya tiene arreglo en el kit).
> 2. **Protocolo de pruebas (§3)** que un agente debe pasar en CADA sistema nuevo antes de fiarse
>    del control, para validar que "siguiendo estas instrucciones se controla bien el ordenador".
>
> Pruebas ejecutadas en: **macOS** (Apple Silicon, pantalla 1280×832 lógico, Retina 2×).
> Windows y Linux: **pendientes de validar** (el protocolo §3 está pensado para ello).

---

## 1. Fallos encontrados y su arreglo

| # | Fallo real (cómo se manifestó) | Causa | Arreglo en el kit |
|---|---|---|---|
| 1 | Brave al **0 %** visible tras Warp, ambos en `(0,29) 1280×708`; el vídeo no lo mostraría | Dos apps a pantalla completa apiladas; solo se ve la de arriba | `visibilidad.py` mide el % visible real con z-order |
| 2 | El enumerador de AppleScript **no daba el orden de capas** y no veía todas las ventanas | System Events no expone el z-order; solo apps con Accesibilidad completa | `winlist` (CGWindowList): z-order, capa y geometría de **todas** |
| 3 | `do script` creó una ventana de Terminal que **nunca se vio** | El proceso Terminal estaba `visible=false`; la ventana existe pero oculta | `place_window` fuerza `visible=true`, activa y verifica bounds |
| 4 | La ventana nueva de Terminal salió **casi a pantalla completa** (1280×737) | Hereda el tamaño anterior | `place_window` la coloca por ID y comprueba los bounds reales |
| 5 | TextEdit acabó con **2 ventanas** (una enterrada al 10 %) | `activate` ya abre un documento y `make new document` crea otro | Regla en doc 03 + `textedit_una_ventana` |
| 6 | Cada `do script` dejaba una **Terminal más enterrada** (2,4 % visible) | `do script` crea ventana NUEVA cada vez | Guardar el ID de cada ventana y cerrarlas; el gate las detecta |
| 7 | Texto tecleado **cayó en la ventana equivocada** (apareció en Terminal, 0 veces en TextEdit) | `keystroke` va a la app con el foco, no a la deseada | `type_in`/`hotkey` se **niegan** a escribir si `front` ≠ app esperada |
| 8 | Clicar el **centro de la línea** de OCR solo acertaba la palabra del medio (1 de 5) | El OCR por línea devuelve la caja de toda la frase | `ocr --words` (caja por palabra) + `click_text`; los 5/5 aciertos |
| 9 | La biblioteca **fallaba en zsh** (no encontraba `visibilidad.py`) | `BASH_SOURCE` no existe en zsh (shell por defecto de macOS) | `_SELF="${BASH_SOURCE[0]:-$0}"`; probado en bash y zsh |
| 10 | `click_text` daba `SyntaxError` | Un `python3 - <<EOF` dentro de un pipe lee los datos del pipe **como si fueran el programa** | Script aparte `ocr_buscar.py` (nunca heredoc + pipe) |
| 11 | Una ventana en `x=1000` de 620 de ancho salía **"100 % visible"** y se sale de la pantalla (1280) | El detector no conocía el borde de la pantalla | Autodetecta la pantalla (ventana "Dock") → "55 % FUERA DE PANTALLA" |
| 12 | El gate marcaba **Warp y Brave** como error aunque eran apps de fondo irrelevantes | Juzgaba todas las ventanas | `--only` (juzga solo las del layout) |
| 13 | Una **notificación** encima del vídeo no se detectaba | Es ventana de capa alta, no una "app" | El gate lista **OVERLAYS** (capa ≠ 0 que no es menú/Dock/cursor) |
| 14 | Warp es `Warp` en una API y `stable` en otra | Cada API nombra el proceso distinto | Usar el nombre que devuelve `front`/`winlist`, no el supuesto |
| 15 | La doc suponía **÷2** (Retina) a pelo | La escala depende de la pantalla | `screen_scale()` la calcula (píxeles físicos / ancho lógico) |
| 16 | La doc decía que el agente "no puede ver imágenes" | Texto obsoleto | Corregido: visión primero; OCR solo para el dónde exacto |
| 17 | El gate marcó **OVERLAY** al abrir una app: era `StatusIndicator` | Es el indicador de privacidad/grabación de macOS en la barra de menús (aparece con `screencapture`/OBS); no tapa contenido | Se ignora lo que está ≥ 80 % dentro de la barra de menús; una notificación real sigue detectándose |
| 18 | Mi primer arreglo del #17 **seguía fallando**: el indicador llega a x=1282 y la barra acaba en 1280 | Comprobaba contención estricta | Proporción de solape (≥ 80 %), tolera 1-2 px de borde. Lo destapó una prueba sintética con las medidas reales |
| 19 | `keystroke "á"` escribió **`a`** (á é ú ü → a; solo ñ y ¿ sobrevivieron) | Teclado Spanish-ISO: AppleScript pierde las vocales con tilde | Emisor `teclear` (eventos Unicode); `tipear.py` avisa si no existe |
| 20 | Trazar un trayecto de ratón de 40 puntos con `cliclick` tardó **4 s** | `cliclick m:` cuesta ~103 ms fijos por movimiento, sea cual sea `-w`; `-e` solo llega a 0,3 s | `teclear` acepta `m x y` (eventos de ratón directos): 1,8 s para 1.100 px |
| 21 | El emisor Swift **perdía pulsaciones** (`ñáéú` y se cortaba) | Sin pausa entre eventos y el proceso terminaba antes de que la app los consumiera | Micropausa de 6 ms por evento + espera final de 150 ms |
| 22 | `click_text "cuatro"` clicó a veces **otra ventana** (y una vez seleccionó vacío) | Busca en toda la pantalla y toma la primera coincidencia: la palabra también estaba en el terminal de fondo | `click_text PALABRA N MODO APP`: busca solo en la ventana de esa app |
| 23 | Tras el clic erróneo, **todo lo siguiente falló en cadena** ("no encontré la palabra") | Clicar otra ventana la sube al frente y entierra la tuya; el OCR ya no ve su texto | `click_text` con APP hace `ensure_front` primero; probado: enterrada a propósito, recupera 4/4 |
| 24 | La salida de `click_text` se llenó de `scale=2.0` (solo en zsh) | En zsh, `local x` repetido dentro de un bucle **imprime** `x=valor` | Declarar todas las variables locales al inicio de la función |
| 25 | El texto verificado en TextEdit no coincidía (`Curl`, comillas “ ”) | Autocorrector de TextEdit (mayúscula inicial, comillas tipográficas) | No es un fallo del tecleo: verificar en Terminal/editor plano o desactivar la autocorrección |
| 26 | Al usar `ensure_front` con **Chrome**, macOS mostró un diálogo "**Warp quiere controlar la app Google Chrome**" y el script se colgó esperando | `tell application "X" to activate` exige un permiso de **Automatización por cada app nueva** (Apple Events) | `ensure_front` usa System Events (`set frontmost`), que ya tiene permiso, y `open -a` de reserva. **No se concede ningún permiso por el usuario**; si aparece uno, es decisión suya |
| 27 | El mismo diálogo aparecía en la captura como **overlay real**: `UserNotificationCenter`, capa 8, 458×432 | Un permiso pendiente es una ventana de sistema encima de todo | El gate lo marcó `<-- saldrá en el vídeo` (**P14 verificada con un overlay real**, no solo sintético) |
| 28 | Chrome se abrió con **tu perfil real**: nombre de cuenta, extensiones y una pestaña "Upgraded - Wappalyzer" abierta por una extensión | `open -a` usa el perfil por defecto | Perfil desechable `--user-data-dir=... --disable-extensions` (doc 06 §1.0): sin cuenta, sin extensiones, sin historial |
| 29 | Tecleando `127.0.0.1:8765/` y Enter, Chrome cargó la página **anterior** (`.../cuenta?id=1002`) | **Autocompletado en línea** con el historial: Enter navega a lo autocompletado | `type_url`: teclear → **Suprimir** (`key code 117`, borra la sugerencia y no toca nada si no la hay) → Enter |
| 30 | `ensure_front "Burp Suite"` falló: "foco actual: JavaApplicationStub" | System Events llama al proceso `JavaApplicationStub`; `winlist` lo llama `Burp Suite` (cf. nº 14, Warp/`stable`) | Resolver la app **por PID** (`_proc_ref`, `front` devuelve el nombre de winlist) |
| 31 | Con Burp, `click_text "Next"` clicó **un campo vacío** y el diálogo no avanzó | El foco ya era de Burp pero su ventana aún **no estaba pintada encima**: la captura/OCR leyó texto de otras ventanas (mis mensajes con la palabra "Next") | `ensure_front` espera a que la ventana de la app sea la **primera del z-order** (foco ≠ visible). Alternar Chrome↔Burp: 4/4 correcto |
| 32 | El clic en el campo se calculó bien pero **el paso siguiente no aparecía** | Un clic sin verificar es un clic que puede no haber hecho nada | Siempre `wait_for` del resultado del clic (lo detectó el `TIMEOUT` de `wait_for "Use Burp defaults"`) |
| 33 | Doble clic sobre `/cuenta?id=1001` seleccionó **`id`**, no el valor | El OCR da la caja de la palabra entera y se clicó su centro (mismo error que el nº 8, un nivel más fino) | `click_text ... SUBCADENA`: posición proporcional del trozo; exacta en fuentes monoespaciadas (editores, Burp) |
| 34 | Un doble clic en Burp **fallaba 1 de cada 3 veces, de forma periódica** (3 de 8, luego 4 de 12...): no seleccionaba nada y Cmd+C copiaba la petición entera | Contador interno de la app (Java): **no** era el punto, ni el OCR, ni el tiempo (igual con 4 s de pausa) ni clicar en el mismo píxel (el desvío no lo arregló) | `select_text`: doble clic → copiar → **comparar con lo esperado** → reintentar (máx. 3) y restaurar el portapapeles. **12/12** |
| 35 | Mi primera hipótesis (clic en el mismo píxel que el anterior) era **errónea** | Correlación aparente: los fallos caían en posiciones repetidas por casualidad | Se descartó midiendo (el desvío de `mover.py` se mantiene: un clic con el cursor ya en el sitio sin movimiento previo tampoco es humano) |
| 36 | Chrome **ignoró Cmd+Q** | Opción "Avisar antes de salir con ⌘Q" (hay que mantenerlo pulsado) | Cerrar con `Cmd+W` por ventana; para la instancia de la demo, `pkill -f chrome-demo-profile` |

### Lo que **sí** funcionó a la primera (medido)
- **Control del cursor:** `cliclick m:300,600` → `mousepos` devuelve `300,600` exacto.
- **Clic por OCR + Retina:** clic en el punto calculado → el cursor cayó **exactamente** ahí.
- **`wait_for`:** 0,3 s con el texto presente; entiende tildes/ñ; con texto inexistente da TIMEOUT y código 1.
- **Foco por clic:** clicar una ventana cambia `frontmost` (verificado con System Events).
- **Doble clic + Cmd+C + `pbpaste`:** forma fiable de comprobar *qué palabra* se seleccionó.

---

## 2. Reglas de oro que salen de estas pruebas

1. **Verifica siempre, también el éxito.** Cada fallo anterior fue silencioso: no daba error, solo
   un vídeo malo. Por eso las funciones del kit **comprueban** y **fallan en voz alta**.
2. **El foco manda.** Antes de teclear/atajar, comprueba quién tiene el foco (`type_in` lo hace).
3. **Mide lo que se ve, no lo que existe.** Una ventana puede existir, estar "abierta" y no verse
   (oculta, enterrada, fuera de pantalla). Usa el gate (`ventanas`) **y** mira la captura.
4. **Nombres y escalas se leen, no se suponen** (proceso, escala Retina, tamaño de pantalla).
5. **Limpia al terminar** lo que creaste (ventanas de prueba, documentos sin guardar).

---

## 3. Protocolo de pruebas para un SO nuevo (Windows / Linux / otro Mac)

Pasa estas pruebas en la máquina nueva, **en orden**, con tus equivalentes de `PORTABILIDAD.md` §2.
Si alguna falla, **arregla el kit de ese SO y documenta el fallo en la tabla de arriba**.
Usa solo ventanas **creadas por ti** (no toques las apps del usuario) y límpialas al acabar.

| # | Prueba | Cómo | Pasa si |
|---|---|---|---|
| P1 | **Mover cursor** | mover a (300,600) y leer la posición | lee (300,600) |
| P2 | **Escala** | captura → ancho físico / ancho lógico | obtienes el factor (1, 1.25, 1.5, 2…) |
| P3 | **Ver** | captura de pantalla y mírala | identificas lo que hay abierto |
| P4 | **OCR por palabra** | escribe "uno dos tres cuatro cinco" en un editor; OCR; clic en cada palabra con doble clic+copiar | las palabras seleccionadas = las pedidas (5/5) |
| P5 | **Acentos** | texto "Contraseña sesión" → buscarlo | lo encuentra con tildes y sin ellas |
| P6 | **Abrir + esperar** | abrir una app; `wait_for` un texto de su interfaz | aparece antes del timeout; con texto inexistente da TIMEOUT (código ≠ 0) |
| P7 | **Colocar por ID/título** | crea 2 ventanas y colócalas lado a lado | los bounds reales coinciden (±12 px) |
| P8 | **App oculta/minimizada** | oculta la app; crea ventana; colócala | queda **visible** tras colocarla |
| P9 | **Foco** | clic en cada ventana; lee la ventana activa | la activa cambia a la clicada |
| P10 | **Foco equivocado** | teclea con el foco en otra ventana (a propósito) | tu función **se niega** y el texto no cae donde no debe |
| P11 | **Gate: enterrada** | pon dos ventanas en la misma posición | el gate da **≈ 0 %** a la de detrás y sale con código ≠ 0 |
| P12 | **Gate: layout limpio** | ventanas en paralelo | ambas ≈ 100 % y código 0 |
| P13 | **Gate: fuera de pantalla** | ventana que sobresale del borde | marca "% FUERA DE PANTALLA" |
| P14 | **Gate: overlay** | provoca una notificación (o simula una línea de capa alta) | aparece como OVERLAY |
| P15 | **Limpieza** | cierra tus ventanas/documentos | solo quedan las ventanas originales |
| P16 | **Tecleo humano** | teclea una frase con tildes, `€`, `¿`, comillas, `\|`, `~` y errores simulados (3-5 %); compara el texto final **exacto** en un editor sin autocorrector; mide cuánto tardó y que aparece **progresivamente** | texto idéntico, duración ≈ estimada, y a mitad se ve a medias |
| P17 | **Ratón humano** | mueve a 6 destinos (incluido uno a 1 px del anterior); muestrea la posición durante un trayecto largo | llega exacto 6/6; el muestreo pasa por puntos intermedios con perfil lento-rápido-lento; < 2 s |
| P18 | **Clic dirigido a una app con texto repetido** | repite una palabra en dos ventanas; `click_text` con la app; entierra la ventana a propósito | clica en la ventana correcta 4/4 y la recupera del fondo |
| P19 | **Barra de URL con autocompletado** | teclea una URL cuyo prefijo exista en el historial; Enter | carga la URL **tecleada**, no la autocompletada (`type_url`) |
| P20 | **Campo de una página web** | clic por OCR en un `<input>` y tecleo con tildes/`€`/`¿`/errores | el valor del campo = el texto pedido; al enviar, llega en la URL |
| P21 | **Campo de una app Java/Swing (Burp)** | teclea una petición con saltos de línea en el editor; selecciona un trozo y reescríbelo | el contenido es exacto; la selección se verifica (12/12 con `select_text`) |
| P22 | **Ciclo de vida de una app lenta** | `open -a`, avanzar diálogos con `click_text` + `wait_for` verificando cada paso, usarla, cerrarla | llega al estado esperado sin clics perdidos; al cerrar no quedan procesos |

Resultado en **macOS**: P1-P22 ejecutadas sobre ventanas reales (Terminal, TextEdit, Chrome y Burp Suite); **P14
(overlay) verificada con un overlay real** (diálogo de permisos del sistema). Los fallos
1-36 de la tabla se encontraron y corrigieron.
Resultado en **Windows / Linux X11 / Linux Wayland**: ⏳ pendiente — ejecutar el protocolo, anotar
fallos aquí y construir el kit equivalente a `mac-control.sh`.

> Pista para quien implemente el kit de otro SO: replica la **misma API** (`front`, `ventanas`,
> `place_window`, `ensure_front`, `type_in`, `hotkey`, `click_text`, `wait_for`, `screen_scale`) para
> que los documentos 05/06 y las demos funcionen sin cambios; solo cambia el cuerpo de cada función.
