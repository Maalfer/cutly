# 06 — Reproducir la demo paso a paso (guía exacta)

Guía para reproducir la demo ClickFix v2 desde cero (o rehacer cualquier fase).
Todos los comandos verificados en macOS 27.2.1, pantalla 1280×832 lógico.

## PREPARACIÓN (una sola vez)

```bash
# 1. Verificar permiso de Accesibilidad:
~/Desktop/ctrl-kit/mousepos && /opt/homebrew/bin/cliclick m:300,600 && ~/Desktop/ctrl-kit/mousepos
# Si el cursor se movió → permiso OK. Si no → ver doc 01.

# 2. Limpieza de estado previo:
pkill -f c2_server.py 2>/dev/null
rm -rf ~/Desktop/clickfix-demo/c2_loot
launchctl list | grep systemcheck   # debe salir vacío (v1 ya limpia)
```

## MONTAJE DEL ESCENARIO

```bash
# 3. Ocultar apps que estorban (ajustar lista según diagnóstico):
osascript - <<'EOF'
tell application "System Events"
  set visible of process "stable" to false
  set visible of process "Warp" to false
  set visible of process "Brave Browser" to false
  set visible of process "WhatsApp" to false
  set visible of process "OBS" to false
end tell
EOF

# 4. Crear ventanas de Terminal (víctima primero, C2 después):
osascript -e 'tell application "Terminal" to do script "clear"'
sleep 1.5
osascript -e 'tell application "Terminal" to do script "cd ~/Desktop/clickfix-demo && python3 c2_server.py"'
sleep 2.5

# 5. Listar ventanas y anotar IDs (¡identificar por NOMBRE!):
osascript -e 'tell application "Terminal"
  set s to ""
  repeat with w in windows
    set s to s & (id of w) & " ||| " & (name of w) & linefeed
  end repeat
  return s
end tell'
# "mario — -zsh" = VÍCTIMA | "mario — Python c2_server.py" = C2

# 6. Posicionar POR ID (sustituir IDs reales):
osascript -e 'tell application "Terminal" to set bounds of window id VICTIMA to {650, 80, 1270, 750}'
osascript -e 'tell application "Terminal" to set bounds of window id C2 to {10, 80, 630, 750}'

# 7. Safari al frente con la página:
open -a Safari ~/Desktop/clickfix-demo/fake-page.html
sleep 3
osascript -e 'tell application "Safari" to set bounds of front window to {290, 40, 990, 790}'

# 8. Verificar escenario completo:
screencapture -x /tmp/stage.png
~/Desktop/ctrl-kit/ocr /tmp/stage.png | grep -E "Escuchando|amenazas|COPIAR"
# Debe verse: C2 escuchando (izq), página con botón (centro), franja osca víctima (der)
```

## LA TOMA (una vez anunciado "NO TOQUES")

```bash
sleep 4                                          # leer el señuelo
/opt/homebrew/bin/cliclick m:250,350; sleep 0.6  # glided path
/opt/homebrew/bin/cliclick m:420,550; sleep 0.6
/opt/homebrew/bin/cliclick m:580,660; sleep 0.5
/opt/homebrew/bin/cliclick m:639,684; sleep 0.8  # (¡coords del botón verificadas!)
/opt/homebrew/bin/cliclick c:639,684; sleep 1.5  # CLIC → verde "COPIADO"
pbpaste | head -c 60                              # verificar clipboard

/opt/homebrew/bin/cliclick c:1100,300; sleep 1.5  # foco a víctima
osascript -e 'tell application "System Events" to keystroke "v" using {command down}'
sleep 3.5                                         # pausa dramática
osascript -e 'tell application "System Events" to keystroke return'
sleep 6                                           # payload + exfil + flood
/opt/homebrew/bin/cliclick c:150,400            # REVEAL → C2 con el botín
sleep 2.5
screencapture -x /tmp/take_final.png
```

## VERIFICACIÓN POST-TOMA

```bash
~/Desktop/ctrl-kit/ocr /tmp/take_final.png | grep -E "Limpieza|EXFILTRACIÓN|contraseña|Cookies"
# Esperado: víctima "Limpieza completada ✓" + C2 con el botín completo
ls -la ~/Desktop/clickfix-demo/c2_loot/   # zip del botín presente
```

## NOTAS DE COORDENADAS

- Botón COPIAR con Safari en {290,40→990,790}: ~(639, 684) — RE-verificar siempre
  con `find_button.py` o OCR antes de cada toma
- Franja víctima: x 990-1270 → clic seguro en (1100, 300)
- Franja C2: x 10-290 → clic seguro en (150, 400)
- Retina: píxel físico del OCR / 2 = punto lógico de cliclick
