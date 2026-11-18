#!/bin/bash
# Detecta huecos de silencio alrededor de un timestamp, para afinar un punto
# de corte dentro de una pausa real en vez de cortar a mitad de palabra.
#
# Uso:
#   ./detectar_silencio.sh <video.mp4> <timestamp_segundos> [duracion_segundos] [umbral_dB]
#
# Ejemplo:
#   ./detectar_silencio.sh ~/Desktop/directo-completo.mp4 910 6 -22

set -euo pipefail

VIDEO="$1"
T="$2"
DUR="${3:-6}"
NOISE="${4:--22dB}"

START=$(echo "$T - ($DUR / 2)" | bc)
if (( $(echo "$START < 0" | bc -l) )); then
  START=0
fi

echo "Ventana: ${START}s -> $(echo "$START + $DUR" | bc)s (objetivo: ${T}s), umbral ${NOISE}"
ffmpeg -ss "$START" -t "$DUR" -i "$VIDEO" -af "silencedetect=noise=${NOISE}:d=0.1" -f null - 2>&1 | grep silence
