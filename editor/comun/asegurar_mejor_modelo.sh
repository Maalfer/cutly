#!/bin/bash
# Comprueba que el modelo Whisper RECOMENDADO esta disponible localmente en
# ~/.whisper-models/, y lo descarga si falta. Implementa la directriz del CLAUDE.md:
# usar el modelo MAS PRECISO MEDIDO, que no es el mas grande (ver ../BENCHMARK-WHISPER.md:
# large-v3-turbo igualo o mejoro a large-v3 en nuestro audio, al doble de velocidad y
# con ~40% menos RAM).
#
# Lista de prioridad (de recomendado a respaldo). Un modelo nuevo solo sube AL PRINCIPIO
# de esta lista si gana en una medicion como la del benchmark, no por ser mas grande.
#
# Uso:
#   ./asegurar_mejor_modelo.sh          # descarga el mejor que falte, imprime su ruta
#   ./asegurar_mejor_modelo.sh --check  # solo informa, no descarga nada

set -euo pipefail

MODELS_DIR="$HOME/.whisper-models"
mkdir -p "$MODELS_DIR"

# orden de prioridad: nombre_fichero
PRIORITY=(
  "ggml-large-v3-turbo.bin"
  "ggml-large-v3.bin"
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
  echo "Ya tienes el modelo recomendado: $BEST_PATH" >&2
  echo "$BEST_PATH"
  exit 0
fi

echo "Falta el modelo recomendado ($BEST)." >&2
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

echo "Descargando $BEST desde Hugging Face (puede tardar varios minutos, ~1.6GB)..." >&2
curl -L -o "$BEST_PATH" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${BEST}"
echo "Descarga completa: $BEST_PATH" >&2
echo "$BEST_PATH"
