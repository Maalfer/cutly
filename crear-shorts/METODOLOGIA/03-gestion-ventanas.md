# 03 — Gestión de ventanas: lecciones duramente aprendidas

> **macOS** (AppleScript/System Events). Las *lecciones* (diagnosticar antes de construir,
> direccionar por ID y no por "front window", orden back-to-front, no tocar durante la toma) valen
> en cualquier SO. Equivalentes para mover/listar/ocultar ventanas en Windows (`nircmd`/PowerShell)
> y Linux (`wmctrl`/`xdotool`): `../../PORTABILIDAD.md` §2.

## El problema raíz

En un Mac real del usuario hay una **pila de ventanas fullscreen** que nadie ve:
en esta máquina eran `stable` (el TUI de OpenCode), `Brave`, `WhatsApp` — TODAS en
posición (0,29) tamaño 1280×708, apiladas. Debajo: Warp. Debajo: el escritorio.

Cuando el agente crea sus ventanas (Safari, Terminal), macOS las pone DONDE TOCA
según qué esté arriba de la pila. Resultado: la ventana víctima quedó invisible
detrás de Warp y el usuario no entendía nada.

## Las 7 lecciones

### 1. Diagnostica ANTES de construir

```bash
osascript - <<'EOF'
tell application "System Events"
  repeat with p in (every process whose visible is true)
    try
      repeat with w in (every window of p)
        log (name of p) & " ||| " & (name of w) & " ||| pos:" & ((position of w) as text)
      end repeat
    end try
  end repeat
end tell
EOF
```
Con esto descubres la pila completa y sus tamaños reales.

### 2. Ocultar apps estorbosas con `set visible to false`

```applescript
tell application "System Events"
  set visible of process "Warp" to false
  set visible of process "stable" to false
end tell
```

- **`set visible to false` = Cmd+H de toda la app** — desaparece y NO afecta al proceso
  (el agente vive dentro de Warp/`stable` y siguió funcionando perfectamente oculto)
- **`AXMinimize` NO funciona en todas las apps** (falló en Warp) — no confíes en él
- Ocultar OBS NO detiene la grabación de pantalla (proceso independiente de la ventana)
- Al terminar: `set visible to true` para devolverlo todo

### 3. Direcciona ventanas por ID, jamás por "front window"

**Bug real de esta sesión:** `set bounds of front window` justo tras `do script`
tiene una carrera — la ventana creada puede no ser aún "front", y los bounds
se asignan a la ventana equivocada (la víctima acabó fullscreen).

**Correcto:**
```bash
# 1. Listar ventanas con ID y nombre:
osascript -e 'tell app "Terminal" to repeat with w in windows... (get id & name)'
# 2. Identificar por NOMBRE (zsh vs Python es obvio):
#    "mario — -zsh — 54×27"        → víctima (shell limpio)
#    "mario — Python c2_server.py" → el C2
# 3. Posicionar POR ID:
osascript -e 'tell application "Terminal" to set bounds of window id 2487 to {650,80,1270,750}'
```

### 4. Orden de construcción del escenario (back-to-front)

```bash
# 1º la ventana de FONDO (víctima):
do script "clear" → bounds derecha
# 2º la del medio (C2):
do script "python3 c2_server.py" → bounds izquierda
# 3º activar Terminal (sube sus dos ventanas)
# 4º activar Safari (queda al frente, encima de las Terminals)
```
Safari al frente tapa el centro; las Terminals asoman en franjas laterales.
Esas franjas son los "puntos de clic" para cambiar el foco durante la toma.

### 5. Cambiar el plano enfocando con clics en las franjas

Durante el video, para pasar de una app a otra sin ⌘Tab (más natural y visual):

```bash
cliclick c:1100,300   # clic en la franja derecha → víctima al frente + foco
cliclick c:150,400     # clic en la franja izquierda → C2 al frente (el "reveal")
```

### 6. La pestaña de Safari correcta

- Safari puede tener la pestaña del señuelo DE FONDO y una pestaña vacía al frente
- Listar pestañas: `tell app "Safari" to get name of every tab of front window`
- Activarla: `set current tab of front window to t`
- Si se perdió: reabrir con `open -a Safari ruta/página.html`
- **Recargar tras cambiar el payload:** Cmd+R — el HTML viejo sigue cargado si no

### 7. El usuario NO debe tocar el Mac durante la toma

**Incidente real:** en mitad de la toma, el usuario interactuó con su máquina →
Warp/TUI volvió a primer plano → el clic del agente cayó en la ventana equivocada
→ el ⌘V pegó 1982 caracteres en el input del chat del TUI.

**Protocolo:** anunciar "NO TOQUES NADA HASTA 'CORTEN'" y hacer la toma en UNA
secuencia continua de ~15s. Si se contamina el input del TUI:
```bash
# Limpiar SIN pulsar Enter:
osascript -e 'tell application "System Events" to keystroke "a" using {command down}'
osascript -e 'tell application "System Events" to key code 51'  # Delete
```

## Layout de pantalla que funcionó (1280×832 lógico)

```
┌──────────┬───────────────────────────┬──────────┐
│  C2      │        SAFARI             │ VÍCTIMA  │
│ {10,80   │      {290,40              │ {650,80  │
│  →630,   │        →990,790}          │  →1270,  │
│  750}    │   (al frente, centro)     │   750}   │
│ franja   │                           │ franja   │
│ izq exp.│                           │ der exp. │
└──────────┴───────────────────────────┴──────────┘
  cliclick c:150,400        cliclick c:1100,300
  (reveal del C2)           (foco para pegar)
```
