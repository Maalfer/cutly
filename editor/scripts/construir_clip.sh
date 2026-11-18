#!/bin/bash
# Construye un clip final a partir de una lista de tramos a mantener (start end),
# aplicando automaticamente un micro-fade de 20ms en cada segmento para evitar
# clics en los cortes (ver seccion 6.9 del CLAUDE.md). Evita tener que calcular
# a mano la duracion de cada segmento para el parametro "st" del afade de salida,
# que ha sido fuente de errores manuales.
#
# Uso:
#   ./construir_clip.sh <video_origen> <video_salida> [-b BITRATE] [-a ABITRATE] <start1> <end1> [<start2> <end2> ...]
#
# -b BITRATE: bitrate de video para el reencode (ej. 1.5M, 5M). Por defecto 5M.
# -a ABITRATE: bitrate de audio para el reencode (ej. 128k, 192k). Por defecto 192k.
# COMPRUEBA SIEMPRE el bitrate nativo (video Y audio) de la fuente con ffprobe antes de
# elegir estos valores (ver seccion "Errores de proceso" del CLAUDE.md) -- usar 5M/192k en
# una fuente de, por ejemplo, 720p/839kbps video o 128k audio infla el archivo sin ganar
# nada de calidad real. Regla practica: ~1.5x-2x el bitrate nativo de la fuente, y el audio
# igualado (o como mucho 1.5x) al nativo, nunca muy por encima.
#
# Los tiempos pueden ir en segundos (516.2) o en HH:MM:SS(.ms) (00:08:36.2) -- el
# script los normaliza a segundos el mismo para evitar errores de conversion manual.
#
# Ejemplo:
#   ./construir_clip.sh ~/Desktop/directo.mp4 ~/Desktop/clip.mp4 -b 1.5M \
#     00:08:36.2 00:08:52.3  00:09:25.3 00:09:29.95  00:09:42.7 00:12:32.0

set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "Uso: $0 <origen> <salida> [-b BITRATE] <start1> <end1> [<start2> <end2> ...]" >&2
  exit 1
fi

SRC="$1"; shift
OUT="$1"; shift

VBITRATE="5M"
ABITRATE="192k"
while [ "$1" = "-b" ] || [ "$1" = "-a" ]; do
  if [ "$1" = "-b" ]; then VBITRATE="$2"; else ABITRATE="$2"; fi
  shift 2
done

if [ $(( $# % 2 )) -ne 0 ]; then
  echo "Uso: $0 <origen> <salida> [-b BITRATE] <start1> <end1> [<start2> <end2> ...]" >&2
  exit 1
fi

to_seconds() {
  # convierte HH:MM:SS(.ms) o un numero de segundos ya plano a segundos (float)
  local t="$1"
  if [[ "$t" == *:* ]]; then
    python3 -c "
t = '$t'.split(':')
h, m, s = (float(x) for x in ([0]*(3-len(t)) + t))
print(h*3600 + m*60 + s)
"
  else
    echo "$t"
  fi
}

FADE=0.02
FILTERS=""
VALABELS=""
N=0

while [ "$#" -gt 0 ]; do
  START_RAW="$1"; END_RAW="$2"; shift 2
  START=$(to_seconds "$START_RAW")
  END=$(to_seconds "$END_RAW")
  DUR=$(python3 -c "print($END - $START)")
  FADE_OUT_ST=$(python3 -c "print(max(0, $DUR - $FADE))")

  FILTERS="${FILTERS}[0:v]trim=start=${START}:end=${END},setpts=PTS-STARTPTS[v${N}];"
  FILTERS="${FILTERS}[0:a]atrim=start=${START}:end=${END},asetpts=PTS-STARTPTS,afade=t=in:d=${FADE},afade=t=out:st=${FADE_OUT_ST}:d=${FADE}[a${N}];"
  VALABELS="${VALABELS}[v${N}][a${N}]"

  echo "Segmento $N: ${START_RAW} -> ${END_RAW}  (${START}s -> ${END}s, dur ${DUR}s)" >&2
  N=$((N + 1))
done

FILTERS="${FILTERS}${VALABELS}concat=n=${N}:v=1:a=1[outv][outa]"

MAXRATE=$(python3 -c "
v = '$VBITRATE'.upper().rstrip('M')
print(f'{float(v) * 1.1}M')
")
BUFSIZE=$(python3 -c "
v = '$VBITRATE'.upper().rstrip('M')
print(f'{float(v) * 2}M')
")

echo "--- construyendo $OUT con $N segmentos (bitrate video: $VBITRATE, audio: $ABITRATE) ---" >&2
ffmpeg -y -i "$SRC" -filter_complex "$FILTERS" \
  -map "[outv]" -map "[outa]" \
  -c:v libx264 -preset medium -b:v "$VBITRATE" -maxrate "$MAXRATE" -bufsize "$BUFSIZE" \
  -c:a aac -b:a "$ABITRATE" "$OUT"

echo "--- duracion final ---" >&2
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT"
