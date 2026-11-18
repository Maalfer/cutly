# 01 — Control total del Mac desde un agente de IA

## El concepto

El usuario pide cosas → el agente de IA **controla cursor, teclado, ventanas y apps**
del MacBook → el usuario solo graba la pantalla → luego edita el video con su cara y voz.

## Lo que hace falta (en orden de importancia)

### 1. El permiso de Accesibilidad (el desbloqueo maestro)

**Problema:** Los clicks y tecleos sintéticos (`cliclick`, `osascript keystroke`) no funcionan
sin permiso TCC de Accesibilidad para el proceso responsable.

**Solución adoptada:** Añadir el binario del agente a:
```
System Settings → Privacidad y seguridad → Accesibilidad → ➕
⌘⇧G → /Users/mario/.opencode/bin/opencode → Abrir → interruptor ON
```

**Cómo verificar que funciona (test de 10 segundos):**
```bash
# 1. Leer posición real del cursor:
~/Desktop/ctrl-kit/mousepos
# 2. Mover el cursor:
cliclick m:300,600 && ~/Desktop/ctrl-kit/mousepos
# Si el cursor está en (300,600) → CONTROL ACTIVO
# 3. Test de teclado: abrir TextEdit, escribir, verificar con OCR
```

**Diagnóstico si falla:** El "responsible process" de TCC es el ancestro GUI del proceso
que lanza los comandos. Con OpenCode, es `/Users/mario/.opencode/bin/opencode`.
Si el usuario ejecuta desde otra app (Terminal.app, iTerm), hay que añadir ESA app.

### 2. Las capacidades (todas verificadas en esta máquina)

| Capacidad | Herramienta | Ejemplo |
|-----------|-------------|---------|
| Mover/clicar cursor | `cliclick` (/opt/homebrew/bin) | `cliclick c:459,664` |
| Teclear texto | `osascript keystroke` | `osascript -e 'tell app "System Events" to keystroke "hola"'` |
| Combinaciones de teclas | `osascript` | `keystroke "v" using {command down}` |
| Abrir apps | `open -a AppName` | `open -a Safari archivo.html` |
| Posicionar ventanas | AppleScript `set bounds` | Por ID: `set bounds of window id 2487 to {...}` |
| Crear ventanas Terminal | `do script` | `tell app "Terminal" to do script "comando"` |
| Capturar pantalla | `screencapture -x /tmp/x.png` | Silencioso, instantáneo |
| LEER la pantalla | OCR propio (Vision de macOS) | `~/Desktop/ctrl-kit/ocr /tmp/x.png` |
| Portapapeles | `pbcopy` / `pbpaste` | Verificar flujos de copy/paste |
| Procesos y ventanas | `osascript` + System Events | Listar, ocultar, minimizar |
| Shell completo | el propio entorno del agente | Cualquier comando |

### 3. El bucle de verificación (crítico)

**Regla de oro: NUNCA asumas que una acción funcionó — VERIFÍCALA.**

El bucle de cada acción:
```
ACCIÓN → screencapture → OCR/análisis → ¿coincide con lo esperado? → siguiente fase
```

El agente de esta sesión NO puede ver imágenes directamente (el modelo no soporta
input de imagen), por eso se construyó un OCR con el framework Vision de macOS
(100% local, offline, gratis) que devuelve texto CON COORDENADAS en píxeles físicos.
En Retina 2x: **punto lógico (cliclick) = píxel físico / 2**.

### 4. Cómo "ve" el agente sin ojos

1. **OCR con coordenadas** (`ocr`): lee TODO el texto de pantalla + posición exacta
2. **Análisis de píxeles** (PIL + Python): detectar colores de botones, estados, ventanas
3. **Enumeración UI de AppleScript**: `tell app "System Events" to get every window of process X`
   con posición, tamaño y nombre — el "árbol de ventanas" sin capturar nada
4. **AppleScript de app**: `count windows`, `bounds of window`, `name of tabs` — estado interno

Con estas 4 vías el agente tiene percepción completa del escritorio.

### 5. Configuración de pantalla (importante para coordenadas)

- Pantalla: 2560×1664 física (Retina) = **1280×832 puntos lógicos**
- `cliclick` trabaja en puntos lógicos
- `screencapture` devuelve píxeles físicos (2x)
- El OCR devuelve coordenadas en píxeles físicos → **dividir entre 2** para cliclick

### 6. Atajos aprendidos en esta máquina

- El usuario usa **Warp** como terminal, con **OpenCode TUI** dentro (proceso `stable`)
- Tiene **OBS** para grabar (ocultar su ventana NO detiene la grabación)
- Suele tener Brave, WhatsApp y otras apps fullscreen apiladas en (0,29,1280x708)
- El menú está en español
