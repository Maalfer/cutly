---
name: subtitular-short
description: Subtítulos karaoke de un Short ya montado, al estilo del ideal del usuario, con revisión del texto antes de quemarlos y verificación final. Úsala cuando haya un short_<Titulo>_editado.mp4 sin subtitular o el usuario pida subtítulos.
argument-hint: "[editor/videos-editados/short_<Titulo>_editado.mp4]"
---

# Subtitular un Short

Vídeo: $ARGUMENTS (si no se da: el material con papel `short` —`python editor/comun/material.py ruta short`— o el
`short_*_editado.mp4` más reciente de `editor/videos-editados/` sin su `_subtitulado`). Estilo y reglas: `editor/shorts/SHORT-IDEAL.md` §6. **El vídeo ENTERO, llamada final incluida.**

1. `python editor/shorts/subtitular.py preparar <video>` -> escribe `<video>.subtitulos.json` y lo imprime.
2. **Revisa el texto** tú primero (tildes, "cómo" interrogativo, términos técnicos, nombres) y corrige el campo
   "texto" de cada bloque. Un término técnico nuevo mal escrito va además a `editor/comun/glosario.json`.
3. **Pide al usuario que lo revise** (en cutly estudio: la tabla de revisión se abre sola en Resultados, junto al
   vídeo, y lee y guarda ese mismo JSON) y espera a que diga que está revisado. No quemes sin esa confirmación: un
   subtítulo quemado no se corrige.
4. `python editor/shorts/subtitular.py quemar <video>` -> `<video>_subtitulado.mp4`.
5. `python editor/shorts/verificar_short.py <video>_subtitulado.mp4` debe decir "cumple la especificación".
