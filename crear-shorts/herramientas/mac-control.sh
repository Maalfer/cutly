#!/usr/bin/env bash
# mac-control.sh — Biblioteca de control del ordenador para agentes de IA (macOS).
#
# Cada función hace la acción Y la VERIFICA, y falla en voz alta si algo no es como debe ser.
# Nace de errores reales detectados en pruebas (ver METODOLOGIA/07-auditoria-de-pruebas.md).
#
# Uso:   source crear-shorts/herramientas/mac-control.sh
# Requiere: cliclick (brew), osascript, screencapture, python3 y el ctrl-kit compilado
#           (ocr, winlist, mousepos). Ruta del kit: $CTRL_KIT (def. ~/Desktop/ctrl-kit).
# Windows/Linux: misma API, comandos equivalentes en PORTABILIDAD.md §2.
#
# Convenciones: coordenadas en PUNTOS LÓGICOS (las de cliclick y AppleScript).

CTRL_KIT="${CTRL_KIT:-$HOME/Desktop/ctrl-kit}"
# compatible con bash y zsh (macOS usa zsh por defecto: allí no existe BASH_SOURCE)
_SELF="${BASH_SOURCE[0]:-$0}"
_HERR="$(cd "$(dirname "$_SELF")" && pwd)"
_TMP="${TMPDIR:-/tmp}"

_err() { echo "[mac-control] $*" >&2; }

# ---------- percepción ----------

# Nombre del proceso que tiene el foco AHORA (como lo llama System Events; ojo: Warp = "stable").
front() { osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'; }

# Factor de escala real físico/lógico (Retina = 2). NO lo supongas: calcúlalo.
screen_scale() {
  screencapture -x "$_TMP/_sc.png"
  local pw lw
  pw=$(sips -g pixelWidth "$_TMP/_sc.png" | awk '/pixelWidth/{print $2}')
  lw=$(osascript -e 'tell application "Finder" to get item 3 of (get bounds of window of desktop)')
  python3 -c "print($pw/$lw)"
}

# Ventanas en pantalla con z-order y % realmente visible. Opciones de visibilidad.py (--need, --exit-code...)
ventanas() { "$CTRL_KIT/winlist" | python3 "$_HERR/visibilidad.py" "$@"; }

# Espera (con OCR) a que aparezca un texto. wait_for "texto" [segundos=20]. Código 1 si TIMEOUT.
wait_for() {
  local needle="$1" max="${2:-20}" t=0
  while [ "$t" -lt "$max" ]; do
    screencapture -x "$_TMP/_wait.png"
    "$CTRL_KIT/ocr" "$_TMP/_wait.png" | grep -qiF "$needle" && return 0
    sleep 1; t=$((t+1))
  done
  _err "TIMEOUT esperando: $needle"; return 1
}

# ---------- ventanas ----------

# Da foco a una app y ESPERA a que realmente lo tenga. ensure_front "Terminal"
ensure_front() {
  osascript -e "tell application \"System Events\" to set visible of process \"$1\" to true" \
            -e "tell application \"$1\" to activate" 2>/dev/null
  local i=0
  while [ $i -lt 20 ]; do
    [ "$(front)" = "$1" ] && return 0
    sleep 0.25; i=$((i+1))
  done
  _err "no pude dar foco a '$1' (foco actual: $(front))"; return 1
}

# Coloca una ventana POR ID y verifica que quedó donde debía.  place_window APP ID x y w h
# - Fuerza visible=true (do script puede crear ventanas de una app OCULTA: existen pero no se ven).
# - Comprueba los bounds reales (algunas apps imponen mínimos/rejilla y no obedecen).
place_window() {
  local app="$1" id="$2" x="$3" y="$4" w="$5" h="$6"
  osascript -e "tell application \"System Events\" to set visible of process \"$app\" to true" \
            -e "tell application \"$app\" to activate" \
            -e "tell application \"$app\" to set bounds of window id $id to {$x, $y, $((x+w)), $((y+h))}" || {
    _err "no pude mover la ventana $id de $app"; return 1; }
  sleep 0.4
  local b; b=$(osascript -e "tell application \"$app\" to get bounds of window id $id" | tr -d ' ')
  python3 - "$b" "$x" "$y" "$((x+w))" "$((y+h))" <<'PY' || { _err "bounds reales $b != pedidos (la app los ajustó)"; return 1; }
import sys
got=list(map(int,sys.argv[1].split(','))); want=list(map(int,sys.argv[2:6]))
sys.exit(0 if all(abs(g-w)<=12 for g,w in zip(got,want)) else 1)
PY
}

# Cierra TODAS las ventanas de TextEdit duplicadas salvo la primera (activate ya crea una sola).
# Lección: 'activate' + 'make new document' deja DOS ventanas.
textedit_una_ventana() {
  local ids n; ids=$(osascript -e 'tell application "TextEdit" to get id of every window' | tr -d ' ')
  n=$(echo "$ids" | tr ',' '\n' | grep -c .)
  [ "$n" -le 1 ] && return 0
  echo "$ids" | tr ',' '\n' | tail -n +2 | while read -r i; do
    osascript -e "tell application \"TextEdit\" to close window id $i saving no"
  done
}

# ---------- ratón / teclado ----------

# Clic en una PALABRA concreta de la pantalla (OCR por palabra). click_text "Guardar" [n-ésima=1] [dc]
# Lección: el OCR por LÍNEA da la caja de toda la frase; su centro NO es la palabra. Aquí se usa --words.
click_text() {
  local word="$1" n="${2:-1}" mode="${3:-c}"
  screencapture -x "$_TMP/_ct.png"
  local scale; scale=$(screen_scale)
  local xy
  xy=$("$CTRL_KIT/ocr" --words "$_TMP/_ct.png" | python3 "$_HERR/ocr_buscar.py" "$word" "$n" "$scale") || {
    _err "no encontré la palabra '$word' (coincidencia $n) en pantalla"; return 1; }
  cliclick m:"$xy"; sleep 0.3; cliclick "$mode":"$xy"
  echo "$xy"
}

# Escribe texto SOLO si el foco es el esperado. type_in "TextEdit" "hola mundo"
# Lección: keystroke va a la app con el foco; si no lo compruebas, el texto cae en otra ventana.
type_in() {
  local app="$1" text="$2" f; f=$(front)
  if [ "$f" != "$app" ]; then _err "FOCO INCORRECTO: '$f' (esperado '$app') — NO escribo"; return 1; fi
  osascript - "$text" <<'EOF'
on run argv
  tell application "System Events" to keystroke (item 1 of argv)
end run
EOF
}

# Atajo de teclado SOLO si el foco es el esperado. hotkey "Terminal" "t" command
hotkey() {
  local app="$1" key="$2" mod="${3:-command}" f; f=$(front)
  [ "$f" = "$app" ] || { _err "FOCO INCORRECTO: '$f' (esperado '$app') — NO envío el atajo"; return 1; }
  osascript -e "tell application \"System Events\" to keystroke \"$key\" using {$mod down}"
}

key_return() { osascript -e 'tell application "System Events" to key code 36'; }
key_escape() { osascript -e 'tell application "System Events" to key code 53'; }
