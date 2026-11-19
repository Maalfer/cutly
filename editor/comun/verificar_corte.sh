#!/bin/bash
# Verifica un punto de union/corte en un video: extrae una ventana de audio
# alrededor del timestamp dado y la transcribe, para comprobar que la frase
# fluye sin cortarse a medias.
#
# Uso:
#   ./verificar_corte.sh <video.mp4> <timestamp_segundos> [duracion_segundos]
#
# Ejemplo:
#   ./verificar_corte.sh editor/videos-editados/clip.mp4 214.5 8
#   (extrae de 210.5 a 218.5 y transcribe, centrado en el timestamp)
#
# Motor: whisper-cli (whisper.cpp) si esta instalado; si no, transcribir.py (faster-whisper),
# que es lo que se usa en Windows. Mismo modelo en ambos: large-v3-turbo (../BENCHMARK-WHISPER.md).
# Si la ventana sale ambigua, repitela con large-v3 como segunda opinion:
#   MODEL=~/.whisper-models/ggml-large-v3.bin ./verificar_corte.sh ...   (whisper.cpp)
#   MODELO=large-v3 ./verificar_corte.sh ...                              (faster-whisper)

set -euo pipefail

VIDEO="$1"
T="$2"
DUR="${3:-8}"
MODEL="${MODEL:-$HOME/.whisper-models/ggml-large-v3-turbo.bin}"
MODELO="${MODELO:-large-v3-turbo}"
DIR="$(cd "$(dirname "$0")" && pwd)"
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT

# centra la ventana en el timestamp dado (mitad antes, mitad despues); awk y no bc (Git Bash no trae bc)
START=$(awk -v t="$T" -v d="$DUR" 'BEGIN { s = t - d / 2; print (s < 0 ? 0 : s) }')
END=$(awk -v s="$START" -v d="$DUR" 'BEGIN { print s + d }')

echo "Ventana: ${START}s -> ${END}s (objetivo: ${T}s)"
ffmpeg -v error -y -ss "$START" -t "$DUR" -i "$VIDEO" -ar 16000 -ac 1 -c:a pcm_s16le "$TMPD/v.wav"

if command -v whisper-cli >/dev/null 2>&1; then
  if [ ! -f "$MODEL" ]; then
    echo "ERROR: no se encuentra el modelo whisper en $MODEL (ver asegurar_mejor_modelo.sh)" >&2
    exit 1
  fi
  whisper-cli -m "$MODEL" -f "$TMPD/v.wav" -l es 2>&1 | grep -E "^\[00"
else
  # python (no python3): en Windows "python3" es un alias de la Store que no ejecuta nada
  PY="$(command -v python || command -v python3)"
  "$PY" "$DIR/transcribir.py" "$TMPD/v.wav" --modelo "$MODELO" --salida "$TMPD/v" | grep -E "^\["
fi
