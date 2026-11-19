---
name: fusionar-cara-pantalla
description: Junta el Short de pantalla (mudo, banda negra arriba) con el vídeo de la cara y la voz del usuario en un Short final al estilo del usuario. Úsala cuando haya editor/crudo/pantalla.mp4 + editor/crudo/cara.mp4 (o el usuario los nombre).
argument-hint: "[cara.mp4] [pantalla.mp4] [Titulo-Con-Gancho]"
---

# Fusionar cara + pantalla

Argumentos (opcionales): $ARGUMENTS. Por defecto `editor/crudo/cara.mp4` y `editor/crudo/pantalla.mp4`.

Sigue **`editor/shorts/METODOLOGIA-FUSION-CARA.md` al pie de la letra** (es la fuente de verdad; aquí solo el orden):

1. `python editor/comun/transcribir.py <cara>` (en segundo plano: ~1 min por cada 1,7 min de audio).
2. `python editor/shorts/analizar_fusion.py informe <cara> <pantalla> --trans <cara>_transcripcion.json`.
3. Decide el guion de voz (última toma buena, fuera falsos arranques y conectores titubeantes; los insertos de la
   pantalla del usuario SE QUEDAN).
4. Afina cada corte a 10 ms: `python editor/comun/energia.py <cara> T0 T1`.
5. Escribe `editor/crudo/fusion_plan.json` (plantilla: `editor/shorts/plantillas/fusion_plan.ejemplo.json`) y
   `python editor/shorts/fusionar_cara_pantalla.py editor/crudo/fusion_plan.json`.
6. Verifica: `python editor/shorts/verificar_short.py <salida> --sin-subtitulos`, re-transcribe cada empalme y saca un
   fotograma por cada momento clave.
7. Entrada APPEND en `editor/videos-editados/_cortes.log`.

Al terminar, dile al usuario dónde está el Short y ofrécele `/subtitular-short` (el entregable lleva subtítulos).
El objetivo de todo: `editor/shorts/SHORT-IDEAL.md`.
