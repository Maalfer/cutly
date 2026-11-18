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

# App que tiene el foco AHORA, con el MISMO nombre que usa winlist/el gate (se resuelve por PID).
# Lección: cada API nombra distinto el mismo proceso (Warp = "stable" en System Events; Burp Suite =
# "JavaApplicationStub"). El PID es lo único que coincide en todas.
front() {
  local pid n
  pid=$(osascript -e 'tell application "System Events" to get unix id of first process whose frontmost is true' 2>/dev/null)
  n=$("$CTRL_KIT/winlist" 2>/dev/null | awk -F'\t' -v p="$pid" '$9==p && $8==0 {print $2; exit}')
  if [ -n "$n" ]; then echo "$n"
  else osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'; fi
}

# Referencia AppleScript al proceso de una app, por PID si winlist la ve (robusto ante nombres distintos).
_proc_ref() {
  local pid; pid=$("$CTRL_KIT/winlist" 2>/dev/null | awk -F'\t' -v a="$1" '$2==a && $8==0 {print $9; exit}')
  if [ -n "$pid" ]; then echo "(first process whose unix id is $pid)"; else echo "process \"$1\""; fi
}

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
# Lección: `tell application "X" to activate` exige un permiso de AUTOMATIZACIÓN por cada app nueva
# (macOS muestra "<agente> quiere controlar la app X" y bloquea hasta que el usuario responde: medido con
# Chrome). System Events (`set frontmost`) usa el permiso de Accesibilidad que ya hace falta, y `open -a`
# no usa Apple Events. Por eso aquí NO se usa `tell application "X"`.
ensure_front() {
  local ref; ref=$(_proc_ref "$1")
  osascript -e "tell application \"System Events\" to set visible of $ref to true" \
            -e "tell application \"System Events\" to set frontmost of $ref to true" 2>/dev/null \
    || open -a "$1" 2>/dev/null
  local i=0
  while [ $i -lt 20 ]; do
    [ "$(front)" = "$1" ] && break
    sleep 0.25; i=$((i+1))
  done
  [ "$(front)" = "$1" ] || { _err "no pude dar foco a '$1' (foco actual: $(front))"; return 1; }
  # Tener el FOCO no es estar VISIBLE encima: la ventana puede tardar unos cientos de ms en pintarse sobre
  # las demás (medido con Burp: el OCR se hizo antes y leyó texto de otras ventanas). Esperar a que su
  # ventana sea la de arriba en el z-order (si la app no tiene ventana en pantalla, no hay nada que esperar).
  i=0
  while [ $i -lt 16 ]; do
    local top; top=$("$CTRL_KIT/winlist" 2>/dev/null | awk -F'\t' '$8==0 {print $2; exit}')
    [ "$top" = "$1" ] && { sleep 0.2; return 0; }
    "$CTRL_KIT/winlist" 2>/dev/null | awk -F'\t' -v a="$1" '$2==a && $8==0 {f=1} END{exit !f}' || return 0
    sleep 0.25; i=$((i+1))
  done
  _err "'$1' tiene el foco pero su ventana no está encima (arriba: $("$CTRL_KIT/winlist" | awk -F'\t' '$8==0{print $2; exit}'))"; return 1
}

# Coloca la ventana N (def. 1 = la de arriba) de una app SIN scripting propio de la app (solo Accesibilidad).
#   place_window_ax "Google Chrome" 10 80 900 600 [N]
# Funciona con cualquier app con ventanas accesibles (Chrome, Brave, Burp...) sin pedir permisos nuevos.
place_window_ax() {
  local app="$1" x="$2" y="$3" w="$4" h="$5" n="${6:-1}"
  ensure_front "$app" || return 1
  local ref; ref=$(_proc_ref "$app")
  osascript -e "tell application \"System Events\" to tell $ref to set position of window $n to {$x, $y}" \
            -e "tell application \"System Events\" to tell $ref to set size of window $n to {$w, $h}" || {
    _err "no pude colocar la ventana $n de $app"; return 1; }
  sleep 0.5
  "$CTRL_KIT/winlist" | awk -F'\t' -v a="$app" -v x="$x" -v y="$y" -v w="$w" -v h="$h" '
    $2==a && $8==0 { ok=(($4-x)<=12 && (x-$4)<=12 && ($5-y)<=12 && (y-$5)<=12 && ($6-w)<=12 && (w-$6)<=12 && ($7-h)<=12 && (h-$7)<=12);
                     printf "ventana real: %d,%d %dx%d\n",$4,$5,$6,$7 > "/dev/stderr"; exit !ok }' \
    || { _err "bounds reales != pedidos (la app los ajustó)"; return 1; }
}

# Coloca una ventana POR ID y verifica que quedó donde debía.  place_window APP ID x y w h
# OJO: usa el AppleScript PROPIO de la app (`tell application "X"`), que pide permiso de Automatización por
# app. Úsalo con apps ya autorizadas y con ventanas con id (Terminal, TextEdit). Para el resto (Chrome,
# Burp...) usa place_window_ax, que solo necesita Accesibilidad.
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

# Clic en una PALABRA concreta de la pantalla (OCR por palabra, cursor humano).
#   click_text "Guardar" [n-ésima=1] [modo=c|dc] [APP] [SUBCADENA]
# - SUBCADENA: apunta a un trozo DENTRO de la palabra (p. ej. click_text "id=1001" 1 dc Burp 1001 selecciona
#   solo el valor). Exacto en fuentes monoespaciadas.
# - APP (muy recomendado): busca SOLO dentro de la ventana superior de esa app. Sin APP se busca en toda
#   la pantalla y se clica la primera coincidencia, que puede ser de OTRA ventana (error real medido:
#   la palabra también aparecía en el terminal de fondo y el clic fue allí).
# - Reintenta hasta $CLICK_TEXT_TIMEOUT s (def. 5) por si el texto aún no se ha pintado.
# Lección: el OCR por LÍNEA da la caja de toda la frase; su centro NO es la palabra. Aquí se usa --words.
click_text() {
  # (todas las variables se declaran AQUÍ: en zsh, un `local x` dentro de un bucle imprime "x=valor")
  local word="$1" n="${2:-1}" mode="${3:-c}" app="${4:-}" sub="${5:-}" max="${CLICK_TEXT_TIMEOUT:-5}" t=0 xy="" region="" scale=""
  if [ -n "$app" ]; then
    # Un clic en otra ventana la sube al frente y entierra la tuya: asegúrate de que la app está delante.
    ensure_front "$app" || return 1
    sleep 0.3
    region=$("$CTRL_KIT/winlist" | awk -F'\t' -v a="$app" '$2==a && $8==0 {printf "%d,%d,%d,%d",$4,$5,$6,$7; exit}')
    [ -n "$region" ] || { _err "no hay ventana visible de '$app'"; return 1; }
  fi
  while [ "$t" -le "$max" ]; do
    screencapture -x "$_TMP/_ct.png"
    scale=$(screen_scale)
    xy=$("$CTRL_KIT/ocr" --words "$_TMP/_ct.png" | python3 "$_HERR/ocr_buscar.py" "$word" "$n" "$scale" "$region" "$sub") && break
    xy=""; sleep 0.5; t=$((t+1))
  done
  [ -n "$xy" ] || { _err "no encontré la palabra '$word' (coincidencia $n${app:+ en $app}) tras ${max}s"; return 1; }
  mover_humano "${xy%,*}" "${xy#*,}"; sleep 0.25; cliclick "$mode":.
  echo "$xy"
}

# Selecciona una palabra (o un trozo) con doble clic y VERIFICA que se seleccionó lo esperado, reintentando.
#   select_text "id=1001" 1 "Burp Suite" "1001"        # selecciona solo "1001" dentro de "/cuenta?id=1001"
#   select_text PALABRA [n=1] [APP] [SUBCADENA] [ESPERADO]   (ESPERADO por defecto = SUBCADENA o PALABRA)
# Lección (medida en Burp/Java): un doble clic ciego FALLABA 1 de cada 3 veces, de forma periódica, aunque
# el punto fuera exacto, el OCR leyera bien y se esperase 4 s entre intentos (es un contador interno de la
# app). Los fallos nunca eran consecutivos: verificar (copiando) y reintentar lo deja en 100 %.
# Efecto lateral: usa el portapapeles; se restaura el texto que hubiera (si era texto).
select_text() {
  local word="$1" n="${2:-1}" app="${3:-}" sub="${4:-}" want="" tries=0 saved r
  want="${5:-${sub:-$word}}"
  saved=$(pbpaste 2>/dev/null)
  while [ "$tries" -lt 3 ]; do
    click_text "$word" "$n" dc "$app" "$sub" >/dev/null || { printf %s "$saved" | pbcopy; return 1; }
    sleep 0.4
    osascript -e 'tell application "System Events" to keystroke "c" using {command down}'
    sleep 0.3
    r=$(pbpaste 2>/dev/null)
    if [ "$r" = "$want" ]; then printf %s "$saved" | pbcopy; return 0; fi
    tries=$((tries+1))
  done
  printf %s "$saved" | pbcopy
  _err "no pude seleccionar '$want' tras 3 intentos (última selección: '${r:0:30}')"; return 1
}

# Escribe texto INSTANTÁNEO solo si el foco es el esperado. type_in "TextEdit" "hola mundo"
# Para VÍDEO usa type_human (ritmo humano). OJO: keystroke pierde las tildes con teclado Spanish-ISO.
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

# --- Entrada HUMANA (para grabar vídeos): usa esto, no type_in, mientras OBS graba -------------------

# Mueve el cursor con trayecto curvo y velocidad variable (1-2 s según distancia). mover_humano X Y [seg]
mover_humano() {
  python3 "$_HERR/mover.py" "$1" "$2" ${3:+--dur "$3"}
}

# Clic humano en un punto: mueve como una persona, hace una pequeña pausa y clica. clic_humano X Y
clic_humano() { mover_humano "$1" "$2" && sleep 0.2 && cliclick c:.; }

# Teclea como una persona (ritmo variable, pausas, errores corregidos) SOLO si el foco es el esperado.
#   type_human "Terminal" "curl -s https://..." [--wpm 55] [--typos 0.015] [--seed N]
# Usa el emisor `teclear` (Unicode): á é ú ü ñ ¿ € funcionan; `keystroke` de AppleScript pierde las tildes.
type_human() {
  local app="$1" text="$2" f; shift 2; f=$(front)
  if [ "$f" != "$app" ]; then _err "FOCO INCORRECTO: '$f' (esperado '$app') — NO escribo"; return 1; fi
  python3 "$_HERR/tipear.py" "$text" "$@"
}

# Suprimir (borrado hacia DELANTE, fn+Delete). Quita el texto autocompletado seleccionado si lo hay y NO hace
# nada si no hay selección al final del texto (un retroceso borraría una letra real).
key_forward_delete() { osascript -e 'tell application "System Events" to key code 117'; }

# Escribe una URL en la barra de direcciones de un navegador y navega, a ritmo humano.
#   type_url "Google Chrome" "127.0.0.1:8765/" [--wpm 45] [--typos 0.02]
# Lección (medida): el navegador AUTOCOMPLETA en línea con el historial ("127.0.0.1:8765/" -> ".../cuenta?id=1002")
# y Enter navega a lo autocompletado, no a lo tecleado. Por eso: teclear -> Suprimir -> Enter.
type_url() {
  local app="$1" url="$2"; shift 2
  hotkey "$app" l command || return 1; sleep 0.4
  type_human "$app" "$url" "$@" || return 1
  sleep 0.3; key_forward_delete; sleep 0.2; key_return
}

key_return() { osascript -e 'tell application "System Events" to key code 36'; }
key_escape() { osascript -e 'tell application "System Events" to key code 53'; }
