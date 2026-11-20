---
name: directo-a-clips
description: Convierte un directo (Twitch/YouTube) o una grabación sin registro de pasos en clips 16:9 para YouTube. Úsala cuando el usuario pase un directo completo o un enlace a uno.
argument-hint: "<directoN-completo.mp4 | URL>"
---

# Directo -> clips 16:9

Fuente: $ARGUMENTS (un archivo o una URL; si no se da, el material con papel `directo`:
`python editor/comun/material.py ruta directo`). Sigue **`editor/directos/CLAUDE.md`** (metodología completa; es la
fuente de verdad).

Por defecto, al recibir un directo nuevo y sin pedir permiso para estos dos pasos:

1. Si es una URL, descárgala a `editor/crudo/` en la máxima calidad (sección 0).
2. Transcríbelo entero (`python editor/comun/transcribir.py`, o whisper-cli con `-mc 0` y VAD).
3. Analiza y muestra la **tabla de fragmentos interesantes** (cronológica, con estrella en los mejores) y escríbela
   también en `<directo>.candidatos.json` junto al directo (formato en `nucleo/candidatos.py`: n, inicio y fin en
   segundos del directo, titulo en Capitalized-Kebab-Case, tema, estrella). La sección "Directo → clips" de cutly
   estudio la muestra con el directo al lado para que el usuario salte a cada fragmento y marque los que quiere.
   **Espera** a que elija (te escribirá los números, y quedan con `"elegido": true` en ese JSON). No cortes nada
   todavía.

Cuando elija: afina cada corte (`editor/comun/energia.py`, `editor/comun/detectar_silencio.sh`), construye con
`editor/directos/construir_clip.sh`, normaliza el audio a -14 LUFS (`editor/directos/normalizar_audio.py`,
OBLIGATORIO, CLAUDE.md §5.1), decide y aplica el zoom estratégico a cámara si corresponde
(`editor/directos/aplicar_zoom.py`, CLAUDE.md §5.5), verifica cada empalme (`editor/comun/verificar_corte.sh`) y
añade la entrada APPEND a `editor/videos-editados/_cortes.log`.
