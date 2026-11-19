#!/bin/bash
# Verifica un punto de union/corte en un video: extrae una ventana de audio
# alrededor del timestamp dado y la transcribe, para comprobar que la frase
# fluye sin cortarse a medias.
#
# Uso:
#   ./verificar_corte.sh <video.mp4> <timestamp_segundos> [duracion_segundos]
#
# Ejemplo:
#   ./verificar_corte.sh ~/Desktop/fragmentos-directos/clip.mp4 214.5 8
#   (extrae de 211.5 a 219.5 y transcribe, centrado en el timestamp)

set -euo pipefail

VIDEO="$1"
T="$2"
DUR="${3:-8}"
# Modelo recomendado (large-v3-turbo, ver ../BENCHMARK-WHISPER.md). Si la ventana sale ambigua,
# repitela con large-v3 como segunda opinion: MODEL=~/.whisper-models/ggml-large-v3.bin ./verificar_corte.sh ...
MODEL="${MODEL:-$HOME/.whisper-models/ggml-large-v3-turbo.bin}"
TMP="$(mktemp /tmp/verificar_corte_XXXXXX.wav)"

if [ ! -f "$MODEL" ]; then
  echo "ERROR: no se encuentra el modelo whisper en $MODEL" >&2
  exit 1
fi

# centra la ventana en el timestamp dado (mitad antes, mitad despues)
START=$(echo "$T - ($DUR / 2)" | bc)
if (( $(echo "$START < 0" | bc -l) )); then
  START=0
fi

echo "Ventana: ${START}s -> $(echo "$START + $DUR" | bc)s (objetivo: ${T}s)"
ffmpeg -y -ss "$START" -t "$DUR" -i "$VIDEO" -ar 16000 -ac 1 -c:a pcm_s16le "$TMP" 2>&1 | tail -1
whisper-cli -m "$MODEL" -f "$TMP" -l es 2>&1 | grep -E "^\[00"

rm -f "$TMP"
