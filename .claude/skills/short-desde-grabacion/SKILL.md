---
name: short-desde-grabacion
description: Monta un Short vertical mudo (1080x1920, banda negra arriba para la cara) a partir de grabaciones sueltas que NO vienen de crear-shorts (sin registro de pasos), con intro o imágenes opcionales. Úsala cuando el usuario suelte grabaciones en la sección "Grabación → Short" o lo pida.
argument-hint: "<fuente1> [fuente2 ...] [Titulo-Con-Gancho]"
---

# Grabación suelta -> Short mudo

Fuentes, en el orden en que el usuario las quiere: $ARGUMENTS (vídeos e imágenes; si el último argumento no es un
archivo, es el título). Si no hay argumentos: el material con papel `grabacion` e `imagen`
(`python editor/comun/material.py`). Si la toma viene de crear-shorts (tiene `.steps.jsonl`), usa
`editor/shorts/short_desde_toma.py` en su lugar: es automático.

Sigue **`editor/shorts/METODOLOGIA-SHORTS.md`** (fuente de verdad):

1. Mide cada fuente (`ffprobe`) y mira fotogramas cada pocos segundos para decidir los planos: qué tramo, qué
   recorte (896x962 llena el marco; una ventana de terminal va ENTERA en letterbox), paneos para lo ancho.
2. Escribe `editor/crudo/short_plan.json` (plantilla: `editor/shorts/plantillas/short_manual.ejemplo.json`) y
   `python editor/shorts/construir_short.py editor/crudo/short_plan.json`.
3. Verifica la banda (constante en 760) y cada unión con un fotograma; entrada APPEND en
   `editor/videos-editados/_cortes.log`.
4. El resultado es el Short MUDO: dile al usuario que grabe su cara y su voz y que los suelte en la sección
   "Cara + pantalla" (`/fusionar-cara-pantalla`).
