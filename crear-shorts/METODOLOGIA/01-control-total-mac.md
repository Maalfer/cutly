# 01 — Control total del ordenador desde un agente de IA

> **Este documento detalla la implementación en macOS** (cliclick, AppleScript, OCR con Vision).
> El concepto y la metodología valen igual en **Windows y Linux**; la equivalencia de cada comando
> (mover cursor, teclear, ventanas, OCR, captura, portapapeles, permisos) está en la tabla de
> **`../../PORTABILIDAD.md` §2**. Lee aquí el *porqué*; traduce cada comando a tu SO con esa tabla.

## El concepto (idéntico en cualquier sistema)

El usuario pide cosas → el agente de IA **controla cursor, teclado, ventanas y apps**
del ordenador → el usuario solo graba la pantalla → luego edita el video con su cara y voz.

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
ACCIÓN → screencapture → MIRAR la captura (+ OCR para coordenadas) → ¿coincide? → siguiente fase
```

### 4. Cómo VE la IA (como un humano) + las coordenadas exactas

El objetivo es que la IA **vea la pantalla igual que la vería una persona** y además pueda clicar
con precisión de píxel. Se combinan cuatro vías, en este orden:

1. **VISIÓN directa (la principal).** Un modelo con visión (p. ej. **Claude**) abre la captura
   `screencapture` y la **mira como un humano**: entiende el layout, qué app está delante, si una
   ventana tapa a otra, si un botón está activo, si la página cargó. Es la percepción primaria.
   > Si el modelo que estés usando **no** tiene visión, se apoya en las vías 2-4 (OCR + geometría);
   > por eso se construyeron. Pero con un modelo con visión, **mira la imagen siempre** — es lo que
   > más se parece a navegar como un humano.
2. **OCR con coordenadas** (`ocr`, Vision de macOS; Tesseract en otros SO): da el texto de pantalla
   **con su caja en píxeles**, para convertir "ese botón" en un `cliclick c:x,y` exacto. La visión
   dice *qué* hacer; el OCR da el *dónde* al píxel.
3. **Enumeración de ventanas CON z-order** (`winlist` en macOS vía `CGWindowList`; `wmctrl`/PowerShell
   en otros SO): posición, tamaño y **qué tapa a qué** → montar el layout y medir el **% realmente
   visible** de cada ventana (`visibilidad.py`, doc 03). AppleScript no da el z-order.
4. **Análisis de píxeles / estado de app** (color de un botón, `bounds`, `name of tabs`): detalles
   finos cuando la visión o el OCR no bastan.

Con estas cuatro vías la IA tiene percepción completa del escritorio: **ve** como un humano y
**acierta** al píxel. (Retina 2×: punto lógico de `cliclick` = píxel físico del OCR / 2 — §5.)

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
