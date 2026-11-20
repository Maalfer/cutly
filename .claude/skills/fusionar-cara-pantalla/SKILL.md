---
name: fusionar-cara-pantalla
description: Junta el Short de pantalla (mudo, banda negra arriba) con el vídeo de la cara y la voz del usuario en un Short final al estilo del usuario. Úsala cuando el usuario lo pida o lo lance desde la sección «Cara + pantalla» de cutly estudio (con los dos archivos como argumentos).
argument-hint: "[cara.mp4] [pantalla.mp4] [Titulo-Con-Gancho]"
---

# Fusionar cara + pantalla

Argumentos: $ARGUMENTS (cara, pantalla y título opcional). Si faltan, el material con papel `cara` y `pantalla`:
`python editor/comun/material.py ruta cara` / `... ruta pantalla` (el usuario los suelta en la sección «Cara + pantalla»; nadie
los coloca a mano en carpetas). Si hay varios candidatos, pregunta cuál.

Sigue **`editor/shorts/METODOLOGIA-FUSION-CARA.md` al pie de la letra** (es la fuente de verdad; aquí solo el orden):

1. `python editor/comun/transcribir.py <cara>` (en segundo plano: ~1 min por cada 1,7 min de audio).
2. `python editor/shorts/analizar_fusion.py informe <cara> <pantalla> --trans <cara>_transcripcion.json` y el mapa de
   la pantalla con `python editor/shorts/analizar_fusion.py hojas <pantalla>` (el informe dice `padtop`/`pantalla_y`).
3. Decide el guion de voz (última toma buena, fuera falsos arranques y conectores titubeantes; los insertos de la
   pantalla del usuario SE QUEDAN).
4. Afina cada corte a 10 ms: `python editor/comun/energia.py <cara> T0 T1`.
5. Escribe `editor/crudo/fusion_plan.json` (plantilla: `editor/shorts/plantillas/fusion_plan.ejemplo.json`) y
   `python editor/shorts/fusionar_cara_pantalla.py editor/crudo/fusion_plan.json`.
6. Verifica: `python editor/shorts/verificar_short.py <salida> --sin-subtitulos`,
   `python editor/shorts/analizar_fusion.py comprobar editor/crudo/fusion_plan.json` (sin ningún [FALTA]) y
   `python editor/shorts/analizar_fusion.py fotogramas <salida> <palabras clave…>` (lo que se dice, en pantalla).
7. Entrada APPEND en `editor/videos-editados/_cortes.log`.
8. **Sigue directamente con `/subtitular-short`** sobre el Short (lo que se publica lleva subtítulos; no preguntes).

Si pide además una versión sin la llamada final, o verlo en el móvil: METODOLOGIA-FUSION-CARA.md §8 y §9.
El objetivo de todo: `editor/shorts/SHORT-IDEAL.md`.
