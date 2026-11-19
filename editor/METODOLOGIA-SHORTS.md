# Metodología de SHORTS verticales (9:16) con hueco para la cara

> **¿Ya tienes el Short de pantalla y te pasan aparte el vídeo con la cara y la voz del usuario?** Eso es una
> fusión: `METODOLOGIA-FUSION-CARA.md`.
>
> **¿La toma viene de `crear-shorts/` (un agente controló la VM)?** Entonces NO sigas este documento:
> usa `editor/scripts/short_desde_toma.py <toma> --titulo ...`, que ya aplica todas estas reglas
> (banda fija, letterbox sin recortar, verificación de píxeles) de forma automática a partir del
> registro `.steps.jsonl`. Este documento manual es para un vídeo que **no** tiene ese registro (un
> directo real, una grabación suelta). Ver el árbol de decisión en `editor/CLAUDE.md` y la arquitectura
> en `crear-shorts/ARQUITECTURA.md`.
>
> Complemento de `CLAUDE.md`. Aquel documento cubre el corte de un directo en **clips 16:9**.
> Este cubre convertir una grabación (de pantalla, normalmente **muda** — la voz se pone
> después) en un **Short vertical 1080×1920** con un **hueco negro arriba** donde el usuario
> superpone luego su cara/cámara, igual que en la maqueta `crudo/referencia.mp4`.
>
> Validado montando el short "ClickFix en Mac" (intro de activación pirata de Windows +
> ejercicio de robo por copiar-y-pegar). Sigue esto al pie de la letra salvo que el usuario
> pida otra cosa.
>
> **Multiplataforma:** todo aquí es ffmpeg/ffprobe/python puro, así que funciona igual en macOS,
> Windows y Linux. Los comandos de ejemplo son de shell POSIX (macOS/Linux); en Windows úsalos en
> **Git Bash/WSL**, o usa directamente `scripts/construir_short.py` (Python, portable). Instalación
> y GPU por sistema: `../PORTABILIDAD.md`.

---

## 0. El disparador y el entregable

- **Entrada típica:** uno o varios vídeos en `crudo/` (p. ej. `editar.mkv` = el ejercicio,
  `intro.mkv` = la intro) + opcionalmente una maqueta `referencia.mp4` que enseña **cómo lo
  quiere el usuario** (proporción del hueco de la cara, estilo de subtítulos, etc.) + a veces
  imágenes sueltas de apoyo (`*.jpg`).
- **Salida:** un `.mp4` vertical **1080×1920 @60fps** en `videos-editados/`, con el hueco de
  la cara arriba y pista de audio **en silencio** (el usuario graba su voz en off luego).
- **Nomenclatura:** `short_<Titulo-Tipo-YouTube>_editado.mp4` (Capitalized-Kebab-Case, sin
  acentos ni símbolos; el título debe servir tal cual como propuesta de título de YouTube).
  Mismo criterio que en `CLAUDE.md`.

---

## 1. Principio NÚMERO UNO: la banda de la cara es un rectángulo FIJO

El usuario pondrá su cámara en la franja de arriba. **Esa franja debe medir EXACTAMENTE lo
mismo en todos y cada uno de los fotogramas del vídeo**, o la cara "baila" entre planos.

- Se define una constante `padtop` (altura en px de la banda negra superior) y **todos** los
  segmentos usan el mismo valor, sin excepción (ni las imágenes, ni los planos letterbox).
- Proporción tomada de `referencia.mp4`: la cámara ocupa el **tercio superior** →
  `padtop = 648` para un lienzo de 1920 de alto (648/1920 ≈ 0.3375, = 432/1280 de la maqueta).
- **Verifícalo midiendo**, no a ojo. Mide cuántas filas negras hay desde arriba en varios
  fotogramas de distintos planos; deben dar el mismo número:
  ```bash
  ffmpeg -v error -ss <t> -i salida.mp4 -frames:v 1 -vf "crop=10:1920:535:0,format=gray" -f rawvideo - \
   | python3 -c "import sys;d=sys.stdin.buffer.read();rows=[d[i*10:(i+1)*10] for i in range(1920)]
  b=0
  for r in rows:
   if max(r)<24: b+=1
   else: break
  print('topblack=',b)"
  ```
  **Error real cometido y corregido:** una imagen (el ransomware) se centró con `padtop=860`
  mientras el resto iba a 648 → la banda de la cara cambiaba de tamaño. Regla: `padtop` es
  una constante global, nunca se centra un plano moviendo su borde superior.

---

## 2. El lienzo y cómo encaja cada plano

```
0 ─────────────────────────┐  ┐
   BANDA NEGRA (la cara)    │  │ padtop = 648 px  ← CONSTANTE en todo el vídeo
648 ────────────────────────┤  ┘
   CONTENIDO (el recorte    │
   de la grabación, escalado│  1272 px de alto
   a 1080 de ancho)         │
1920 ───────────────────────┘
        1080 px de ancho
```

Cada segmento se construye así (cadena de filtros ffmpeg, por segmento):

```
trim=start=S:end=E, setpts=PTS-STARTPTS,
crop=CW:CH:CX:CY,                       # recorte de la zona interesante de la fuente
scale=1080:DH:flags=lanczos, setsar=1,  # DH = round(CH*1080/CW)  (mantiene proporción)
pad=1080:1920:0:648:black,              # mete el recorte bajo la banda de la cara
fps=60, format=yuv420p
```

y al final se concatenan todos: `[v0][v1]…concat=n=N:v=1:a=0[outv]`.

### Dos maneras de encuadrar un plano

1. **Rellenar el marco.** Recorte con proporción **816×961** (≈ 0.85, igual que
   `1080×1272`): al escalar llena de 648 a 1920 sin bordes. Es el aspecto "nativo de short".
   Se usa para páginas, imágenes o un punto concreto, eligiendo `CX,CY` sobre la zona que importa.
2. **Encajar entero (letterbox).** Si el contenido es apaisado (una imagen, un comando muy
   ancho) y recortarlo a 816 de ancho perdería información, se escala a 1080 de ancho con su
   alto natural (`DH < 1272`) y queda negro debajo. La banda de arriba **sigue en 648**.

> Consejo: (1) llena mejor el móvil, pero solo si SABES que todo lo importante cabe en 816 px. Una
> **ventana de terminal va SIEMPRE en (2), entera** (el texto puede llegar al borde; medido: "22/tcp" salía
> como "cp"), con la fuente del terminal a 24 pt para que se lea: es lo que hace `short_desde_toma.py`.

---

## 3. Técnica estrella: PANEO para mostrar algo ancho a tamaño completo

**Problema real:** un comando de terminal largo
(`curl https://microchoft/activate…`) no cabe en un recorte vertical de 816 px de ancho. Si
lo metes en letterbox se ve **pequeño**; si lo recortas, se **corta**.

**Solución que encantó al usuario:** recorte a **tamaño completo** (816×961, como el resto)
pero **desplazando horizontalmente el recorte en el tiempo** (un paneo) para que la línea
entera desfile por el encuadre, grande y legible, de principio a fin.

En ffmpeg el `x` del `crop` admite expresión con `t` (segundos del segmento, empieza en 0):

```
crop=w=816:h=961:x='CX0 + ((CX1-CX0)/DUR)*t':y=CY
```

- `CX0` = posición inicial (muestra el principio de la línea), `CX1` = final (muestra el final).
- Linealiza: a `t=DUR` el recorte llega a `CX1`. Mantén `CX1 + 816 ≤ ancho_fuente` y `CX0 ≥ 0`.
- **Importante de sintaxis:** si usas expresión en `x`, nombra TODAS las opciones del crop
  (`w=…:h=…:x='…':y=…`), si no ffmpeg da `No option name near '…'`.
- Hazlo **lento**. Un paneo de ~290 px a lo largo de ~4-6 s es suave y cinematográfico.

Esto sirve para cualquier contenido más ancho que alto que quieras ver completo sin empequeñecer.

---

## 4. Ritmo: mejor pecar de LENTO (en el Short MUDO; el final con voz va al grano)

> Esto vale para el Short mudo que luego se monta con la voz. Cuando ya hay voz, el usuario quiere el
> resultado lo más al grano posible, sin pausas: ver `METODOLOGIA-FUSION-CARA.md` (estilo medido).

El usuario corta a mano después, así que **es mejor que cada plano dure de más que de menos**.

- Planos holgados (≈ 5-8 s cada uno). Nada de cortes rápidos encadenados.
- Dos palancas para "ir más lento": (a) **alargar** el `trim` (in/out) cuando el contenido de
  la fuente sigue siendo válido, o (b) **ralentizar** la reproducción con `setpts=K*PTS`
  (útil en planos con movimiento: cursor, scroll, paneo). Para planos estáticos, alargar el
  trim equivale a mantener más tiempo.
- **Verifica los nuevos límites.** Al alargar un `trim`, comprueba con un fotograma que el
  nuevo inicio/fin no mete basura (en estas grabaciones las ventanas se mueven: una ventana
  puede no estar donde esperas 2 s antes/después). Extrae el fotograma del límite y míralo.

---

## 5. Montaje multi-fuente en UNA sola pasada (sin perder calidad)

Cuando el short junta intro + imagen + ejercicio, **constrúyelo todo en un único `ffmpeg`**
desde los originales (no recodifiques un clip ya codificado): un `-i` por fuente, un segmento
de imagen con `-loop 1 -framerate 60 -t <dur>`, una pista muda con
`-f lavfi -t <total> -i anullsrc=r=48000:cl=stereo`, y `concat` de todos los `[vN]`.

Usa el script `scripts/construir_short.py` (plantilla parametrizada que implementa todo lo
anterior: banda fija, recorte/relleno, paneo, imagen y audio mudo). Edita su lista `SEGS` y
ejecútalo. Parámetros de codificación de referencia (ajusta `-b:v` al material):
`libx264 -preset slow -b:v 8M -maxrate 9M -bufsize 16M -c:a aac -b:a 128k -movflags +faststart`.

---

## 6. Verificación (obligatoria antes de dar por bueno)

1. **Duración** = suma de las duraciones de los tramos (`ffprobe -show_entries format=duration`).
2. **Banda de la cara constante** (sección 1): mídela en 4-5 planos distintos, debe dar igual.
3. **Cada unión y cada plano clave:** extrae un fotograma y míralo (tienes visión de imágenes):
   ```bash
   ffmpeg -v error -ss <t> -i salida.mp4 -frames:v 1 -vf scale=300:-1 /tmp/f.png
   ```
   La frase/acción debe leerse bien y no cortarse a mitad; el paneo debe revelar la línea entera.
4. **Fuentes mudas:** confirma con `volumedetect` que la fuente está en silencio real
   (`mean_volume ≈ -91 dB`) y no es un fallo — estas grabaciones de pantalla no llevan voz.

---

## 7. Registro: `videos-editados/_cortes.log`

Igual que en `CLAUDE.md`: cada vez que termines (o revises) un short, añade (APPEND, nunca
reescribir) una entrada con los tramos exactos en segundos de cada segmento, los parámetros de
recorte `CX:CY:CW:CH`, el `padtop`, los paneos, y qué se descartó y por qué. Es lo único que
permite auditar o rehacer el short después sin reconstruirlo desde cero. Si el log aparece
ausente/truncado, es transitorio (mira la Papelera): nunca lo recrees desde cero.

---

## 8. Checklist rápido de un short

- [ ] `padtop` constante (medido) en todos los planos, incluidas imágenes.
- [ ] Terminales en letterbox de la ventana entera; recorte 816×961 solo si todo lo importante cabe.
- [ ] Contenido ancho (comandos largos) → paneo lento a tamaño completo, no empequeñecido.
- [ ] Ritmo holgado (pecar de lento); límites de trim verificados con fotograma.
- [ ] Montaje en una pasada desde los originales; pista de audio muda para la voz en off.
- [ ] Duración, banda de la cara y cada unión verificadas con fotogramas.
- [ ] Entrada añadida a `_cortes.log`.
