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

**Uso:**
```bash
~/Desktop/ctrl-kit/ocr captura.png
# Salida: <texto>\t[x,y WxH] en píxeles FÍSICOS (Retina: /2 para cliclick)
```

**Ejemplo real de esta sesión:**
```
$ ocr /tmp/stage_v3.png | grep -iE "COPIAR"
• COPIAR COMANDO DE LIMPIEZA (%C)   [956,1314 643x33]
# → centro del botón = (956+643/2)/2 = 639 lógico x, 1314+16)/2 ≈ 684 lógico y
# → cliclick c:639,684
```

**Trucos aprendidos:**
- Filtra por zona con awk: `awk -F'\t' '$0 ~ /\[(9[7-9][0-9],/'` (columna x)
- El OCR confunde algunos símbolos (% por ⌘, v por ✓) — el texto correcto está casi siempre
- `recognitionLanguages = ["es-ES", "en-US"]` — ya configurado para español

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

## Herramienta 8: `solapes.py` — detectar ventanas superpuestas (multiplataforma)

Garantiza que ninguna ventana tape a otra antes de grabar (el fallo que más estropea un vídeo).
Lee por stdin la lista de ventanas (`etiqueta x y w h`) y avisa de las que se solapan; con
`--exit-code` sirve de "puerta" (no grabar hasta `0 solapamientos`). La matemática es universal;
solo cambia el comando que enumera las ventanas en cada SO.

```bash
# macOS (enumerar + comprobar). Linux X11: wmctrl -lG | awk '...'; Windows: PowerShell. Ver PORTABILIDAD §2.
osascript <<'EOF' | python3 crear-shorts/herramientas/solapes.py --min-pct 80 --exit-code
tell application "System Events"
  set out to ""
  repeat with p in (every process whose visible is true and background only is false)
    try
      repeat with w in (every window of p)
        set out to out & (name of p) & "\t" & (item 1 of (position of w)) & "\t" & (item 2 of (position of w)) & "\t" & (item 1 of (size of w)) & "\t" & (item 2 of (size of w)) & "\n"
      end repeat
    end try
  end repeat
  return out
end tell
EOF
```

Procedimiento completo (gate anti-solape) en `03-gestion-ventanas.md`.
