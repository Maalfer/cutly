#!/bin/bash
# Comprueba que el mejor modelo Whisper conocido esta disponible localmente en
# ~/.whisper-models/, y lo descarga si falta. Implementa la directriz del CLAUDE.md:
# "descarga siempre el MEJOR modelo que la maquina pueda mover de forma razonable".
#
# Lista de prioridad (de mejor a peor). Si Hugging Face publica un modelo mejor que
# large-v3 (p.ej. una version futura), anade su nombre AL PRINCIPIO de esta lista.
#
# Uso:
#   ./asegurar_mejor_modelo.sh          # descarga el mejor que falte, imprime su ruta
#   ./asegurar_mejor_modelo.sh --check  # solo informa, no descarga nada

set -euo pipefail

MODELS_DIR="$HOME/.whisper-models"
mkdir -p "$MODELS_DIR"

# orden de prioridad: nombre_fichero
PRIORITY=(
  "ggml-large-v3.bin"
  "ggml-large-v2.bin"
  "ggml-medium.bin"
  "ggml-small.bin"
)

CHECK_ONLY=false
[ "${1:-}" = "--check" ] && CHECK_ONLY=true

{
  echo "Modelos ya presentes en $MODELS_DIR:"
  ls -la "$MODELS_DIR" 2>/dev/null | grep ggml || echo "  (ninguno)"
} >&2

BEST="${PRIORITY[0]}"
BEST_PATH="$MODELS_DIR/$BEST"

if [ -f "$BEST_PATH" ]; then
  echo "Ya tienes el mejor modelo conocido: $BEST_PATH" >&2
  echo "$BEST_PATH"
  exit 0
fi

echo "Falta el mejor modelo conocido ($BEST)." >&2
if [ "$CHECK_ONLY" = true ]; then
  echo "Modo --check: no se descarga nada." >&2
  # informa cual es el mejor que SI esta disponible localmente, por si hace falta usarlo mientras tanto
  for m in "${PRIORITY[@]}"; do
    if [ -f "$MODELS_DIR/$m" ]; then
      echo "Mejor disponible localmente ahora mismo: $MODELS_DIR/$m" >&2
      echo "$MODELS_DIR/$m"
      exit 0
    fi
  done
  echo "No hay NINGUN modelo descargado todavia." >&2
  exit 1
fi

echo "Descargando $BEST desde Hugging Face (puede tardar varios minutos, ~3GB)..." >&2
curl -L -o "$BEST_PATH" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${BEST}"
echo "Descarga completa: $BEST_PATH" >&2
echo "$BEST_PATH"
