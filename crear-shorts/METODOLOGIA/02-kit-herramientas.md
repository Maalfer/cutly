# 02 — Kit de herramientas del agente

> **macOS.** Equivalente de cada herramienta (cursor, teclado, OCR, captura, ventanas,
> portapapeles) para Windows y Linux en `../../PORTABILIDAD.md` §2, con cómo instalarlas.

Ubicación en vivo (macOS): `~/Desktop/ctrl-kit/` (compilados y funcionando)
Copias del código fuente: `crear-shorts/herramientas/` (dentro de este repo)

## Herramienta 1: `ocr` — Leer texto de pantalla CON coordenadas

**Compilación (solo una vez):**
```bash
cd ~/Desktop/ctrl-kit && swiftc -O -o ocr ocr.swift
# Requiere Command Line Tools: xcode-select --install
```

**Dos modos:**
```bash
~/Desktop/ctrl-kit/ocr captura.png            # una línea por BLOQUE de texto:  <texto>\t[x,y WxH]
~/Desktop/ctrl-kit/ocr --words captura.png    # una línea por PALABRA:          <palabra>\t[x,y WxH]
# Coordenadas en píxeles FÍSICOS. Punto lógico para cliclick = px / ESCALA (Retina = 2).
```

> **⚠️ Lección medida en pruebas reales:** el modo por línea da la caja de **toda la frase**, y su
> centro **NO es la palabra que buscas**. Con la línea "uno dos tres cuatro cinco seis siete ocho",
> clicar el centro de la línea acertó solo "cinco" (la del medio); con `--words` se acertaron las 5
> palabras probadas. **Para clicar una palabra o un enlace dentro de una frase, usa `--words`.**
> El modo por línea sirve para *comprobar que un texto existe* (p. ej. `wait_for`), no para clicar.

**Clicar una palabra (lo normal): usa `click_text`** de `herramientas/mac-control.sh`:
```bash
source crear-shorts/herramientas/mac-control.sh
click_text "Guardar"        # 1ª coincidencia; click_text "Guardar" 2  -> la 2ª; click_text "X" 1 dc -> doble clic
```
Ignora mayúsculas, tildes y puntuación ("Sesión:" == "sesion") y calcula la escala Retina real.

**Ejemplo manual (botón de una sola palabra o frase corta):**
```
$ ocr --words /tmp/stage_v3.png | grep -iE "^COPIAR"
COPIAR   [956,1314 130x33]
# centro lógico = (956+130/2)/2 , (1314+33/2)/2  ->  cliclick c:510,665
```

**Trucos aprendidos:**
- Filtra por zona con awk: `awk -F'\t' '$0 ~ /\[(9[7-9][0-9],/'` (columna x)
- El OCR confunde algunos símbolos (% por ⌘, v por ✓) — el texto correcto está casi siempre
- `recognitionLanguages = ["es-ES", "en-US"]` — ya configurado para español (tildes y ñ funcionan)
- Rendimiento medido: captura + OCR de pantalla completa Retina ≈ 0,3 s

## Herramienta 2: `mousepos` — Posición exacta del cursor

```bash
~/Desktop/ctrl-kit/mousepos
# cursor_x=500 cursor_y=589 (coords cliclick)
```

**Uso crítico:** verificar que cliclick funciona tras conceder el permiso.
Mueve el cursor con `cliclick m:X,Y`, lee de nuevo, compara — precisión perfecta.

## Herramienta 3: `cliclick` — control del cursor (homebrew)

```bash
/opt/homebrew/bin/cliclick m:640,416    # mover (visible en la grabación)
/opt/homebrew/bin/cliclick c:459,664   # clic
/opt/homebrew/bin/cliclick dc:639,684  # doble clic
```

**Movimiento cinematográfico (muy visual para el video):**
```bash
# Glided path hacia el botón — la cámara ve el cursor "pensar":
cliclick m:250,350; sleep 0.6
cliclick m:420,550; sleep 0.6
cliclick m:580,660; sleep 0.5
cliclick m:639,684; sleep 0.8
cliclick c:639,684
```

## Herramienta 4: `find_button.py` — localizar botones por color

Requiere Python con Pillow:
```bash
python3 -m venv /tmp/pilenv && /tmp/pilenv/bin/pip install pillow
/tmp/pilenv/bin/python find_button.py captura.png
```

**Qué hace:** Busca bandas de color (rojo por defecto — botones de acción) en la mitad
inferior de la captura. Devuelve el centro en coordenadas cliclick (ya divididas entre 2).

**Limitación aprendida:** si el botón cambia de estado (rojo→verde tras el clic),
la segunda pasada no lo encuentra. Para estado verde, modificar el umbral de color
(buscar `g>140, r<100, b<110`).

## Herramienta 5: teclado sintético (osascript)

```bash
# Texto normal:
osascript -e 'tell application "System Events" to keystroke "Terminal"'
# Combinaciones:
osascript -e 'tell application "System Events" to keystroke "v" using {command down}'
osascript -e 'tell application "System Events" to keystroke (ASCII character 32) using {command down}'  # ⌘Espacio
osascript -e 'tell application "System Events" to keystroke return'  # Enter
# Teclas especiales (key code): 51=Delete, 36=Return, 53=Escape
```

## Herramienta 6: gestión de ventanas (AppleScript)

```bash
# Listar TODAS las ventanas visibles del sistema con posición:
osascript - <<'EOF'
tell application "System Events"
  repeat with p in (every process whose visible is true)
    try
      repeat with w in (every window of p)
        log (name of p) & " | " & (name of w) & " | " & (position of w as text)
      end repeat
    end try
  end repeat
end tell
EOF

# Posicionar ventana POR ID (NUNCA por "front window" — hay carrera):
osascript -e 'tell application "Terminal" to set bounds of window id 2487 to {650, 80, 1270, 750}'

# Identificar ventana por nombre (más fiable que "front"):
osascript -e 'tell application "Terminal" to get name of window id 2489'
# → "mario — Python c2_server.py" (es la del C2)

# Ocultar app (NO minimiza — desaparece, reversible, no afecta al proceso):
osascript -e 'tell application "System Events" to set visible of process "Warp" to false'
# Restaurar: set visible to true

# Crear ventana de Terminal que ejecuta un comando:
osascript -e 'tell application "Terminal" to do script "python3 ~/demo/c2_server.py"'
# Cada do script crea una ventana NUEVA — apuntar sus IDs inmediatamente
```

## Herramienta 7: verificación de portapapeles

```bash
echo "comando" | pbcopy     # cargar el portapapeles
pbpaste | head -c 60        # verificar su contenido
```
**Lección:** tras simular un "copiar" en una web, SIEMPRE verificar con pbpaste
que el JS realmente cargó el portapapeles antes de continuar.

## Herramienta 8: `winlist` + `visibilidad.py` — qué ve REALMENTE una persona (anti-solape)

**El problema:** el fallo que más arruina un vídeo es que una ventana quede tapada/enterrada, o se
salga de la pantalla, o le caiga encima una notificación.

**`winlist`** (Swift, API `CGWindowList`) lista TODAS las ventanas en pantalla **en orden de capas**
(z-order, la primera = la de más arriba) con su geometría, capa y proceso. Mejor que enumerar con
AppleScript, que **no da el z-order** y solo ve apps con Accesibilidad completa.
```bash
cd ~/Desktop/ctrl-kit && swiftc -O -o winlist winlist.swift      # una sola vez
~/Desktop/ctrl-kit/winlist      # z \t app \t título \t x \t y \t w \t h \t layer \t pid
```

**`visibilidad.py`** calcula el **% realmente visible de cada ventana** (pinta de atrás hacia delante
sobre una rejilla), detecta lo **enterrado**, lo que **sobresale de la pantalla** y los **overlays**
(notificaciones…). Dos ventanas solapadas pueden verse perfectas (la de delante completa y la de
detrás asomando): por eso mide *visibilidad*, no solape.
```bash
~/Desktop/ctrl-kit/winlist | python3 crear-shorts/herramientas/visibilidad.py \
    --only Terminal,TextEdit --need Terminal=95 --need TextEdit=95 --exit-code
#   2   100.0%  TextEdit | ...
#   3   100.0%  Terminal | ...
#   4     9.3%  Warp | ...   (fondo, ignorada)
```
- `--only A,B` juzga solo las ventanas del layout; las de fondo tapan pero no cuentan como error.
- `--need App=PCT` exige un mínimo (p. ej. una terminal que debe asomar por una franja ≥ 25 %).
- `--exit-code` devuelve ≠ 0 si algo falla → úsalo como **puerta antes de grabar**.

**`mac-control.sh`** reúne funciones que **hacen y verifican**: `ventanas` (gate), `place_window`,
`ensure_front`, `type_in`/`hotkey` (se niegan a escribir si el foco no es el esperado),
`click_text`, `wait_for`, `screen_scale`. Funciona en **bash y zsh**. Ver `07-auditoria-de-pruebas.md`
para los fallos reales que motivaron cada una.

Procedimiento completo (gate anti-solape) en `03-gestion-ventanas.md`.
