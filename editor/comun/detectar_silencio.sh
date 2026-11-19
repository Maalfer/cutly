#!/bin/bash
# Detecta huecos de silencio alrededor de un timestamp, para afinar un punto
# de corte dentro de una pausa real en vez de cortar a mitad de palabra.
#
# Uso:
#   ./detectar_silencio.sh <video.mp4> <timestamp_segundos> [duracion_segundos] [umbral_dB]
#
# Ejemplo:
#   ./detectar_silencio.sh editor/crudo/directo4-completo.mp4 910 6 -22dB
#
# (Para afinar a 10 ms con rms + alta frecuencia, mejor: python editor/comun/energia.py VIDEO T0 T1)

set -euo pipefail

VIDEO="$1"
T="$2"
DUR="${3:-6}"
NOISE="${4:--22dB}"

# awk y no bc: Git Bash (Windows) no trae bc
START=$(awk -v t="$T" -v d="$DUR" 'BEGIN { s = t - d / 2; print (s < 0 ? 0 : s) }')
END=$(awk -v s="$START" -v d="$DUR" 'BEGIN { print s + d }')

echo "Ventana: ${START}s -> ${END}s (objetivo: ${T}s), umbral ${NOISE}"
ffmpeg -ss "$START" -t "$DUR" -i "$VIDEO" -af "silencedetect=noise=${NOISE}:d=0.1" -f null - 2>&1 | grep silence || true
