# Editor de directos → clips para YouTube

> **Contexto del repo:** este documento vive en `cutly/editor/` y cubre el corte de un
> directo/grabación en **clips 16:9**. Para la visión global del proyecto lee `../README.md`.
> Para **Shorts verticales 9:16** (1080×1920 con hueco arriba para la cara, recorte, paneo de
> contenido ancho y ritmo lento) usa `METODOLOGIA-SHORTS.md` (en esta misma carpeta) y el
> script `scripts/construir_short.py`. El principio rector de abajo aplica a AMBOS formatos.
>
> **Multiplataforma:** esta fase (editar) funciona igual en macOS, Windows y Linux — mismas
> herramientas (ffmpeg, whisper.cpp, python, yt-dlp). Los comandos y rutas de abajo son los de la
> máquina macOS; para Windows/Linux (instalación, nombre del binario de whisper, rutas, GPU, cómo
> correr los `.sh` con Git Bash/WSL) usa `../PORTABILIDAD.md`. Las rutas `~/Desktop/editor/...` que
> aparecen son ejemplos: hoy el proyecto vive en `cutly/editor/` y puede estar en cualquier sitio.

## Principio rector: precisión por encima de coste (tokens/tiempo)

**Decisión explícita del usuario, aplica desde ahora a toda transcripción y edición**: prioriza
al máximo que los fragmentos extraídos tengan el menor número de errores posible, aunque eso
suponga más tiempo de proceso y más consumo de tokens verificando. No recortes pasos de
verificación para ir más rápido. En la práctica:

- **Transcripción inicial: descarga siempre el MEJOR modelo Whisper que la máquina pueda mover
  de forma razonable, no uno fijo por defecto.** No asumas que "large-v3" seguirá siendo el
  mejor disponible — antes de transcribir un directo nuevo, comprueba qué modelos existen en
  https://huggingface.co/ggerganov/whisper.cpp/tree/main (puede haber versiones más nuevas o
  mejores, p. ej. large-v3-turbo u otras futuras) y ten en cuenta la potencia del host (RAM,
  disco libre, si hay GPU/Metal disponible — ya se confirmó que esta máquina tiene Apple
  Silicon con soporte Metal) para elegir el más grande/preciso que siga siendo viable en
  tiempo razonable. Si ya existe un modelo mejor que el guardado en `~/.whisper-models/`,
  descárgalo y adóptalo como nuevo por defecto para esa sesión y las siguientes.
  `ggml-medium.bin` queda como modelo de respaldo rápido para transcripciones intermedias de
  verificación (secciones 6.9, 7) si el modelo grande resultase demasiado lento para iterar,
  pero si la precisión está en duda en una comprobación concreta, repite esa comprobación con
  el modelo más preciso disponible en vez de conformarte con el rápido.
- **Verificación de cortes**: nunca te conformes con una sola comprobación si algo resulta
  ambiguo — repite con ventana más ancha, cruza con el método de probabilidad por token
  (sección 6.9), y si sigue sin estar claro, no cortes. Es preferible gastar más tool calls
  verificando que dejar pasar un corte mal hecho.
- **Antes de dar un clip por terminado**: pasa por todas las secciones del flujo (6, 6.9, 7, 8)
  sin saltarte ninguna "para ahorrar tiempo" — la auditoría retrospectiva de 2026-11-04
  encontró errores reales (un final cortado a mitad de frase, una redundancia sin detectar)
  precisamente en pasos que se habían hecho con menos rigor del que ya se sabía aplicar.
- **Regla general**: ante cualquier disyuntiva entre ir más rápido/barato o quedar más
  preciso/limpio durante la edición, elige lo segundo. Esto aplica a la transcripción, a la
  elección de modelo, al número de comprobaciones por corte, y a cualquier otro paso del
  flujo — la calidad del resultado final importa más que el coste de llegar a él.

Metodología para convertir directos de Twitch en bruto (hacking/ciberseguridad, en español)
en clips cortos y pulidos para subir a YouTube. Desarrollada y validada en sesiones reales
editando varios directos de Mario (elrincondelhacker). Sigue esto al pie de la letra salvo
que el usuario pida explícitamente otra cosa.

## Disparador: qué hacer cuando el usuario te pasa un directo en bruto

Cuando el usuario te indica que hay un directo completo en bruto nuevo (algo tipo "ahí tienes
el directo entero", "ahora veras directoN-completo", un enlace de YouTube/Twitch para
descargar, etc.), sin que pida explícitamente nada más, el flujo por defecto es SIEMPRE, en
este orden, sin pedir permiso para los dos primeros pasos:

1. **Transcribir el directo completo con timestamps** (sección 1 de abajo) — esto deja todo
   listo para poder aplicar cortes después sin tener que volver a procesar el vídeo entero.
2. **Analizar la transcripción y mostrar la tabla de fragmentos interesantes** (sección 2) —
   candidatos a clip, cronológicos, con ⭐ en los mejores.
3. **Esperar** a que el usuario diga qué quiere extraer. No cortes nada todavía en este punto
   — la tabla es solo propuesta.

Es decir: transcripción + tabla van siempre juntas y automáticas al recibir un directo nuevo;
cortar fragmentos concretos es un paso aparte que el usuario pide después, viendo la tabla.

## Contexto del usuario

- Los directos son streams de hacking ético/CTF en español, grabados en vídeo (1920x1080,
  h264, aac), normalmente nombrados tipo `directoN-completo.mp4`.
- El objetivo final siempre es el mismo: sacar fragmentos temáticos autocontenibles, limpios
  de muletillas/tangentes/interrupciones, para subir como clips independientes a YouTube.

### Estructura de carpetas (toda la metodología vive en `~/Desktop/editor/`)

- **`~/Desktop/editor/crudo/`** — vídeos fuente en bruto (`directoN-completo.mp4`). Cuando el
  usuario pasa un directo nuevo (archivo ya puesto ahí, o un enlace de YouTube/Twitch que hay
  que descargar primero en máxima calidad con `yt-dlp`), el .mp4 final vive en esta carpeta.
  La transcripción (`.srt`/`.txt`) se guarda **junto al vídeo, en esta misma carpeta** — debe
  persistir entre sesiones, no es un archivo temporal de scratchpad.
- **`~/Desktop/editor/videos-editados/`** — carpeta de salida de los clips ya montados
  (créala si no existe). Aquí va también `_cortes.log` (registro de cortes, ver sección de
  errores de proceso). El usuario vacía esta carpeta cuando ya ha subido los clips a
  YouTube — que esté vacía NO significa que no se haya hecho nada antes, solo que ya se
  subieron.
- El flujo nunca descarga ni escribe directamente en `~/Desktop/` a secas — todo el trabajo
  (crudo y editado) vive dentro de `~/Desktop/editor/`.
- **Nomenclatura de los clips**: `<directoN>_<Titulo-Tipo-YouTube>_editado.mp4`. La parte
  `<Titulo-Tipo-YouTube>` debe poder servir directamente como propuesta de título real para
  subir el vídeo a YouTube — no un resumen telegráfico tipo `cve_propio`, sino algo con gancho
  y que se entienda fuera de contexto, en Capitalized-Kebab-Case (palabras con mayúscula
  inicial separadas por guiones, sin acentos ni símbolos, para que el archivo siga siendo
  válido en cualquier sistema). Piensa en cómo titularías el vídeo en YouTube y conviértelo
  en ese formato. Ejemplos:
  - ✅ `directo2_Como-Consegui-Mi-Propio-CVE-Real_editado.mp4`
  - ✅ `directo2_Bypass-De-Content-Type-Para-Conseguir-RCE-Con-Webshell-En-Node_editado.mp4`
  - ✅ `directo_Bug-Bounty-Es-Una-Estafa-Mi-Experiencia-Real_editado.mp4`
  - ❌ `directo2_cve_propio_editado.mp4` (demasiado telegráfico, no sirve como título)
  - ❌ `directo_bugbounty_editado.mp4` (igual, muy genérico)

  Si un clip junta dos temas de la tabla de candidatos, el título debe reflejar la idea
  unificada de ambos, no simplemente concatenar los dos temas por separado.

## Herramientas instaladas (persistentes, no reinstalar)

- **whisper.cpp** vía Homebrew (`whisper-cli`, `whisper-server`, etc. en `/opt/homebrew/bin`).
- **Modelos Whisper** guardados en `~/.whisper-models/`, fuera de cualquier scratchpad de
  sesión para que persistan entre sesiones. Comprueba que existen antes de descargar nada:
  ```bash
  ls -la ~/.whisper-models/
  ```
  - `ggml-large-v3.bin` (~3GB) — **modelo por defecto, úsalo para todo** (transcripción base
    del directo entero y toda verificación/afinado de cortes). Más preciso que `medium`,
    sobre todo en nombres técnicos, acrónimos y voz rápida/con ruido de fondo — justo donde
    `medium` alucinaba o perdía palabras repetidas (ver principio rector al inicio del doc).
  - `ggml-medium.bin` (~1.5GB) — solo como respaldo si `large-v3` no estuviera disponible.
  Si falta alguno:
  ```bash
  mkdir -p ~/.whisper-models
  curl -L -o ~/.whisper-models/ggml-large-v3.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin
  curl -L -o ~/.whisper-models/ggml-medium.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin
  ```
- **ffmpeg / ffprobe** vía Homebrew — para todo el corte, recodificación y análisis de audio.

## Errores de proceso detectados en auditoría retrospectiva (no repetir)

- **Comprobar SIEMPRE los parámetros del vídeo fuente de CADA directo nuevo** (resolución,
  fps, bitrate) con `ffprobe` antes de construir el primer clip, y adaptar `-b:v` a ese
  bitrate (no reutilizar ciegamente el `-b:v 5M` de un directo anterior). Pasó en la práctica:
  el primer directo auditado era 1080p a ~4.9Mbps (ahí 5M tenía sentido), pero un directo
  posterior era 720p a ~839kbps y se siguió usando `5M` sin comprobar — los clips resultantes
  pesaban mucho más de lo necesario sin ninguna ganancia de calidad real (no se puede añadir
  detalle que no estaba ya en la fuente). Regla práctica: usa algo en el rango de 1.5x-2x el
  bitrate nativo de la fuente, no un valor fijo.
- **Guardar un registro de los cortes aplicados** (`videos-editados/_cortes.log`, junto a los
  clips) con los tramos exactos en segundos de cada clip y qué se cortó en cada
  corte interno. Antes no se guardaba nada de esto — si en una sesión futura hay que auditar o
  corregir un clip ya construido, no hay forma de saber qué timestamps se usaron sin
  reconstruir todo desde cero leyendo la transcripción otra vez. Añade una entrada a este log
  cada vez que termines un clip (sección 5/9).
- **La pasada de silencios/muletillas (secciones 6-7) debe ser parte del flujo estándar para
  TODO clip que se construya, no un paso opcional que solo se hace si el usuario lo pide
  explícitamente a posteriori.** Los primeros clips de una sesión pueden quedar con una
  fiabilidad de corte inferior a los últimos simplemente porque el método fue mejorando sobre
  la marcha — aplica siempre el método más fiable conocido (sección 6.9) desde el primer clip,
  no solo cuando algo ya ha fallado.
- **Una vez un clip está subido a YouTube y la carpeta de fragmentos se ha vaciado, ya no se
  puede corregir.** Si en una auditoría retrospectiva aparece algo que debería haberse cortado
  en un clip ya publicado, no se puede arreglar el archivo — lo único que cabe es avisar al
  usuario de qué se encontró y dejar que decida si quiere volver a subirlo. Por eso merece la
  pena invertir el esfuerzo de verificación ANTES de dar un clip por terminado, no después.
- **Sin `_cortes.log` no hay forma de auditar retrospectivamente un lote de clips ya
  construido.** Al auditar esta metodología se comprobó que los 2 primeros directos de la
  sesión (10 clips en total) ya estaban subidos a YouTube y sus carpetas vaciadas, y además
  **los vídeos fuente (`directoN-completo.mp4`) también habían sido borrados** — sin el
  archivo fuente y sin un registro de qué timestamps se usaron, es imposible re-verificar o
  corregir nada de ese trabajo, solo cabe documentar la lección para el futuro. Por eso el
  `_cortes.log` (punto anterior) no es opcional: es lo único que permite auditar o corregir
  un lote después de que el usuario borre la carpeta de fragmentos.
- **Comprobación visual rápida en cortes grandes**: extraer un frame justo antes y justo
  después de un corte interno grande (no de un micro-corte de muletilla, para eso no hace
  falta) y mirarlos (tienes capacidad de leer imágenes) para confirmar que no hay un salto
  visual raro (p. ej. que el corte caiga justo cuando hay un elemento en pantalla a medio
  cargar, o un gesto que quede cortado de forma antinatural). No es necesario en cada corte,
  pero es útil como comprobación rápida adicional en los cortes de topic completo (sección 3).
- **Nueva categoría de tangente a vigilar siempre: meta-comentario sobre la propia edición del
  vídeo ("voy a apuntar este momento para sacar un fragmento/clip luego").** Es distinta de las
  demás categorías de tangente (chat, perro, fallo OBS, saludo) porque no es una digresión de
  contenido — es el streamer hablando DIRECTAMENTE sobre el proceso de edición en el que tú
  mismo (el editor) estás trabajando, así que nunca pertenece al clip final por definición.
  Caso real detectado (clip "Máquina Race" walkthrough de 3 Race Conditions, candidato #5): tras
  completar un bypass, el streamer dice "Oye, esto es todo guapo para apuntarlo y luego sacar un
  buen fragmento. Minuto 00:45, voy a poner RACE CONDITION. Y esto lo voy a guardar aquí, notas
  directas. Ahí estamos, perfectísimo." — abre un bloc de notas y dicta en voz alta el timestamp
  que quiere recordar para editar. Este fragmento (~19s) se había colado sin cortar en la
  primera versión del clip; el usuario lo detectó viendo el resultado y pidió corregirlo.
  **Al revisar CUALQUIER fragmento, comprueba explícitamente si el streamer menciona apuntar,
  anotar, guardar en notas, o referirse al minuto/timestamp actual para "sacar un fragmento" —
  es casi siempre cortable al 100%, sin excepción, porque por definición no tiene relación con
  el contenido técnico que ve el espectador.** Usa el patrón grep de la sección 1.5 para
  detectarlo de forma sistemática en la fase de análisis, no solo si el usuario se queja después.
  Al cortarlo, localiza el límite exacto con `-ojf` (como cualquier otro corte, sección 6.9):
  normalmente empieza justo después de que termine la frase del contenido técnico anterior (p.
  ej. "...laboratorio completado") y termina justo antes de que retome ese contenido con un
  conector tipo "Pues nada, ..." — ese "pues nada" de vuelta SÍ se mantiene, es la transición
  natural hacia el siguiente tema, no parte del aparte.
- **Al usar el timestamp de un segmento del SRT como límite END de un tramo a mantener, usa
  siempre el FIN de ese segmento (el valor tras `-->`), nunca su INICIO.** Error real detectado
  en el clip de "Máquina Race" (3 Race Conditions): se identificó que la frase final deseada
  ("Y ya estamos dentro de la máquina") era el segmento SRT `00:52:16.100 --> 00:52:18.100`, pero
  se usó 3136.10 (el inicio, 00:52:16.100) como END del último tramo en vez de 3138.10 (el fin,
  00:52:18.100) — esto cortaba la frase completa fuera del clip, y además el `-ojf` / la
  verificación con ventana estrecha al final del clip no mostró la frase esperada, lo cual fue
  la señal de alarma correcta. Se detectó al verificar el final con `whisper-cli` sobre los
  últimos segundos del clip YA CONSTRUIDO y notar que faltaba la frase prevista; se corrigió
  reconstruyendo con END=3138.10 (duración +2s, frase íntegra). Lección: SIEMPRE verificar el
  final de un clip ya construido transcribiendo sus últimos segundos, no solo confiar en que
  los números de tramo "deberían" ser correctos — es la única forma de detectar este tipo de
  error de raíz (confundir inicio con fin de un segmento de referencia).
- **Alucinación que "envenena" TODA la transcripción de un directo, no solo la intro — usa
  siempre `-mc 0` (`--max-context 0`) al transcribir un directo completo.** Caso real: en
  "Máquina InfluencerHate" la transcripción completa (111 min) salió 100% "¡Suscríbete al
  canal!" repetido en los 3091 segmentos, de principio a fin — NO era el patrón ya conocido de
  alucinación solo-en-la-intro (visto en "Máquina Race", donde solo afectaba a los primeros
  ~7:30 min sobre una pantalla de espera y luego se recuperaba solo). Diagnóstico: los primeros
  ~3 minutos del directo son el streamer interactuando con su perro (Balú) antes de empezar a
  hablar de forma clara al micro/cámara — un tramo que whisper no reconoce bien — y esa
  alucinación inicial queda como contexto ("texto previo") que `whisper-cli` por defecto usa
  para condicionar la predicción de TODOS los segmentos siguientes (`-mc`/`--max-context`), de
  forma que el modelo se queda atascado repitiendo la misma frase alucinada durante el resto del
  archivo aunque el audio real sea perfectamente transcribible — se confirmó transcribiendo
  ventanas aisladas de 20-60s en minutos sueltos (10, 5, 7...) con el MISMO modelo: todas salían
  perfectas en aislado, solo fallaba la pasada completa y secuencial. Solución: añadir siempre
  `-mc 0` al comando de transcripción inicial del directo completo (fuerza a cada ventana a
  decodificarse sin arrastrar el texto previo como contexto, evitando que un tramo raro al
  principio contamine las 2 horas siguientes). Si aun así una transcripción completa sale con
  líneas idénticas repetidas de forma sospechosa en una proporción grande del archivo (comprueba
  con `grep -c` sobre la frase sospechosa contra el total de líneas de texto), NO analices esa
  transcripción — diagnostica primero con `ffmpeg -af volumedetect` (para descartar audio
  realmente silencioso) y con una ventana aislada de 20-60s en varios minutos sueltos del medio
  del archivo antes de concluir que el audio fuente está mal.

- **Si un sub-agente (fork) encargado de construir un clip encuentra `_cortes.log` ausente o con
  menos contenido del que debería tener, NUNCA debe asumir "el usuario vació la carpeta" y
  recrearlo desde cero.** Caso real: durante la construcción en paralelo de los clips de
  "InfluencerHate", un fork encontró `_cortes.log` temporalmente ausente (por la app externa que
  mueve archivos grandes a la Papelera, ya documentada arriba) y, sin verificarlo, reescribió el
  archivo entero con solo sus propias 2 entradas, borrando 11 entradas previas de otros directos
  y otros clips ya terminados por otros forks en la misma sesión. Se detectó y reconstruyó en la
  revisión final a partir del historial de la conversación, pero fue puro azar no perder
  información real. Instrucción obligatoria para cualquier sub-agente (y para el hilo principal)
  que vaya a tocar este archivo compartido: si aparece ausente o truncado, tratarlo como un
  problema transitorio (comprobar primero `~/.Trash/`), nunca como una señal para recrearlo desde
  cero — y si hay cualquier duda, reportarlo como hallazgo en la respuesta final en vez de
  sobrescribir sin confirmar. Al editar este archivo compartido desde varios agentes en paralelo,
  usar siempre APPEND (añadir al final), nunca Write/recreate.
- **Un candidato de "noticia de actualidad + demo práctica de un CVE" puede pasar casi
  desapercibido en la tabla inicial por una descripción demasiado genérica, aunque el rango ya
  esté bien identificado.** Caso real (directo4, 2026-11-08): el candidato "walkthrough
  autocontenible: explota en directo el CVE de auth bypass en OpenSSH..." ya cubría el arco
  completo (00:07:59→~00:23:40: lectura de la noticia del CVE, demo práctica en DockerLabs,
  reverse shell exitosa, cierre), pero el usuario tuvo que pedir explícitamente que se
  confirmara porque la etiqueta de la tabla ("walkthrough...") no dejaba claro que fuese TANTO
  la explicación de la noticia COMO la demo completa en un único tramo continuo — tuvo que
  pedir re-verificación completa de la transcripción para confirmar que no faltaba nada.
  Lección: al presentar en la tabla un candidato de este tipo, dilo de forma explícita
  ("explicación de la noticia/CVE + demo práctica completa, un solo tramo continuo") en vez de
  una etiqueta genérica — y en la fase de análisis (sección 2), busca explícitamente el patrón
  de "comentario de actualidad/vulnerabilidad" con el grep dedicado de la sección 1.5 en vez de
  depender solo del criterio genérico de "explicación técnica autocontenible", que no distingue
  este tipo de contenido (con gancho de actualidad) de un walkthrough cualquiera.

## Flujo de trabajo completo

### 0. Descargar el directo (solo si el usuario da un enlace en vez de un archivo ya puesto)

Si el usuario pasa una URL (YouTube, Twitch VOD, etc.) en vez de un `.mp4` ya colocado en
`crudo/`, descárgalo ahí mismo en la máxima calidad real disponible, no una por defecto:

```bash
# Lista formatos disponibles y elige el de mayor resolución/bitrate que sea mp4+m4a
# (evita tener que reencodear audio opus -> aac luego). Para YouTube, el par
# bestvideo[ext=mp4]+bestaudio[ext=m4a] suele ser la mejor combinación sin pérdidas de remux.
yt-dlp -F "<url>"
yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" \
  --merge-output-format mp4 \
  -o "~/Desktop/editor/crudo/directoN-completo.mp4" "<url>"
```

Lánzalo siempre en background (son descargas de varios minutos/GB) y **nunca lo trates como
terminado solo porque llega la notificación de la tarea** — comprueba con `ps aux | grep
yt-dlp` y el tamaño/existencia real del archivo final antes de pasar a transcribir, porque si
el proceso se interrumpe (p. ej. lo matas tú mismo para reiniciarlo con otra ruta) puede
quedar un `.part`/`.ytdl` a medias en vez del `.mp4` completo.

### 1. Transcribir el directo completo con timestamps

Usa siempre el directorio de scratchpad de la sesión para el audio intermedio (es grande y
desechable), pero guarda la transcripción resultante **junto al vídeo en `~/Desktop/editor/crudo/`**
(debe persistir entre sesiones, no es un archivo temporal).

```bash
# Asegura que tienes el mejor modelo disponible (lo descarga si falta)
# OJO: captura solo stdout en $MODEL. Si el script imprime algo de diagnóstico por error
# (sin redirigir a >&2), $MODEL queda corrupto y whisper-cli falla silenciosamente
# imprimiendo su --help en vez de transcribir (bug real que ocurrió una vez, ya corregido
# en el script, pero vuelve a comprobarlo con `echo "[$MODEL]"` si añades algo nuevo al script).
MODEL=$(~/Desktop/editor/scripts/asegurar_mejor_modelo.sh)

# Extraer audio (en el scratchpad de la sesión, es temporal)
ffmpeg -y -i ~/Desktop/editor/crudo/<directo>.mp4 -ar 16000 -ac 1 -c:a pcm_s16le audio.wav

# Transcribir con timestamps (salida persistente junto al vídeo, en crudo/)
# -mc 0 es OBLIGATORIO en la transcripcion inicial de un directo completo: evita que una
# alucinacion puntual (p.ej. sobre una intro sin voz clara) "envenene" el resto del archivo
# por arrastre de contexto (ver "Errores de proceso" mas abajo).
whisper-cli -m "$MODEL" -f audio.wav -l es -mc 0 \
  -osrt -of ~/Desktop/editor/crudo/<directo>_transcripcion --output-txt
```

Esto genera `<directo>_transcripcion.srt` (con timestamps `HH:MM:SS,mmm`) y `.txt` (texto
plano). **Las líneas del `.txt` y los números de segmento del `.srt` coinciden 1 a 1** — es
decir, la línea N del `.txt` es el texto del segmento N del `.srt`. Esto es clave para
localizar timestamps a partir de una frase: busca la frase en el `.txt`, coge su número de
línea, y haz `grep -n -A1 "^<numero>$" archivo.srt`.

Para un directo de ~1h30min-2h con `large-v3`, tarda más que con `medium` (usa GPU vía Metal,
pero el modelo es ~2x más grande) — es el coste aceptado por la directriz de priorizar
precisión. Lánzalo siempre en background (`run_in_background: true`) y sigue trabajando o
espera la notificación — nunca hagas polling activo del proceso.

Borra el `audio.wav` del scratchpad en cuanto termine la transcripción (es grande, ~200-250MB
por hora de directo, y ya no hace falta una vez tienes el `.srt`/`.txt`).

### 1.5. Atajo: catálogo de marcadores verbales recurrentes

Antes (o en paralelo a) leer todo el `.txt` a mano, lanza estos `grep -ci` sobre el `.srt`
para localizar rápido las zonas con más probabilidad de necesitar un corte (tangentes,
interrupciones, fallos técnicos). Están validados sobre varios directos reales — aparecen de
forma consistente (5-30+ veces por directo de ~2h) y marcan patrones concretos y fiables:

| Patrón grep | Qué señala |
|---|---|
| `os leo\|comenta por aquí\|comento por aquí` | Va a leer el chat — casi siempre arranca una digresión |
| `bueno.*chicos.*vamos a\|vamos a ir con la\|vamos a ir a con` | Vuelta al contenido técnico tras una digresión (punto de retorno) |
| `balu\|balut` | Interrupción del perro |
| `un segundo\|un segundito\|se me ha\|falla\|OBS\|pantalla` | Fallo técnico/aside (cámara, overlay, compartir pantalla) |
| `qué tal\|bienvenido\|qué bueno verte` | Saludo a un espectador — puede ser solo 1 frase o el inicio de una charla más larga |
| `apuntar\|apunto\|apuntarlo\|bloc de notas\|notas directa\|sacar un buen fragmento\|sacar un fragmento\|guardar aquí.*notas\|voy a poner.*minuto\|minuto.*voy a poner` | **Meta-comentario de producción**: el streamer rompe la narrativa para anotar el propio minuto/timestamp que luego usará para editar el vídeo. SIEMPRE cortar — ver sección "Errores de proceso" |
| `cve-\|\bcve\b\|fallo de seguridad\|fallo.*ssh\|visteis lo de\|salió un fallo\|día cero\|0-day\|exploit\|parche crítico\|octubre negro\|vulnerabilidad` | **Comentario de actualidad/vulnerabilidad**: el streamer lee o comenta una noticia de ciberseguridad reciente (un CVE, un fallo publicado). Revisa SIEMPRE si a continuación hace una demo práctica reproduciendo el fallo (DockerLabs, máquina propia) — si es así, es candidato fuerte y el rango debe cubrir el arco completo, ver sección 2 |
| `aplicación que\|herramienta que hice\|la hice yo\|creé una app\|creé una aplicación\|cree una herramienta\|hice esta herramienta\|mi propia herramienta\|mi propia app` | **Demo de herramienta/app propia**: el streamer enseña algo que ha construido él mismo (una web, un script, una automatización). Busca TODAS las apariciones de su nombre propio en el resto de la transcripción — suele reaparecer más de una vez (p.ej. un segundo ejemplo de uso mucho más tarde) y conviene unirlas, ver sección 2.5 |

Esto no sustituye la lectura completa del `.txt` (sección 2) ni el análisis con fork para
transcripciones largas — es un atajo para priorizar qué zonas mirar primero con más cuidado.

### 2. Analizar y proponer fragmentos interesantes

Si la transcripción es larga (>~500 líneas), **delega la lectura completa a un sub-agente
tipo fork** en vez de leerla entera en el contexto principal — así evitas saturarlo. Dale
contexto claro sobre quién es el streamer, qué ya se sabe, y qué tipo de contenido buscar.

Criterios de "fragmento interesante para YouTube":
- Explicaciones técnicas autocontenibles (concepto o técnica de principio a fin)
- Opiniones fuertes/controvertidas bien argumentadas
- Momentos de humor o autenticidad (sin ser vulgares/problemáticos)
- Preguntas de la audiencia con respuestas sustanciosas y genéricas (útiles fuera de contexto)
- Walkthroughs completos de máquina/CTF
- **Comentario de actualidad/vulnerabilidad (CVE, fallo de seguridad reciente) + demo práctica**:
  busca explícitamente este patrón con el grep de la sección 1.5, no lo trates solo como una
  "explicación técnica" genérica más. Cuando el streamer lee/comenta una noticia de
  ciberseguridad reciente y a continuación la reproduce y explota en un entorno controlado
  (DockerLabs, máquina propia), es un tipo de contenido distinto de un walkthrough normal —
  tiene gancho de actualidad ("esto es noticia ahora mismo") además de la demo técnica, lo que
  lo hace especialmente bueno para título de YouTube. Si lo encuentras, **asegúrate de que el
  candidato cubra el arco narrativo completo**: desde que empieza a comentar la noticia hasta
  que termina la demo con éxito y el cierre/resumen, aunque haya alguna tangente breve en medio
  (p.ej. mostrar una app propia de noticias) que convenga recortar aparte — no lo trocees ni lo
  acortes a mitad del arco. Descríbelo en la tabla de forma explícita ("explicación de la
  noticia/CVE + demo práctica completa"), no con una etiqueta genérica tipo "walkthrough de un
  CVE" que no deje claro que incluye ambas partes.
- Evita: saludos genéricos, silencios, música de fondo, charla intrascendente

Presenta el resultado en una tabla markdown: `# | Timestamp | Duración | Tema`, con ⭐ en los
mejores, ordenada cronológicamente. No extraigas nada todavía — esto es solo propuesta.

### 2.5. Técnica: rastreo global de un tema disperso + montaje no lineal

A veces un mismo tema (una herramienta/app propia, una opinión, una anécdota) aparece
mencionado más de una vez en puntos distintos y no contiguos del directo — el streamer la
enseña en un momento y mucho más tarde la retoma con un segundo ejemplo, sin que esos dos
tramos estén cerca en el tiempo. Cuando detectes esto (por el grep de la sección 1.5, o
leyendo el `.txt`), no lo trates como candidatos sueltos sin más — evalúa combinarlos en un
único clip no lineal:

1. Busca TODAS las apariciones del tema en el `.txt` completo (grep por el nombre propio de
   la herramienta/app, o por palabras clave del tema) antes de fijar el alcance de un
   candidato — no te quedes con la primera aparición que encuentres.
2. Para cada aparición, decide si aporta contenido nuevo (un ejemplo distinto, un dato nuevo)
   o si es redundante con otra aparición ya cubierta — descarta lo redundante, no lo incluyas
   solo porque esté ahí.
3. Si decides unir dos o más tramos no contiguos, verifica con el método `-ojf` (sección 6.9)
   que cada tramo por separado tiene un cierre/apertura que conecta bien con el siguiente sin
   sonar forzado (ambos deben ser variaciones de la misma idea, no ideas inconexas forzadas a
   encajar).
4. Documenta en `_cortes.log` que es un montaje no lineal y por qué — precedente real: el
   clip "CSRF Nivel 2" de Crossfi (ver `_cortes_historico_pre-reorganizacion.log`) y el clip
   "Pingunius" de directo4 (2026-11-08): se unió la demo inicial de la app (~00:09:27) con un
   segundo ejemplo de uso ~13 minutos después (~00:24:26), sin incluir el tramo intermedio
   (que pertenecía a otro clip, el del CVE de OpenSSH).

Esto aplica a cualquier contenido que se repita disperso por el directo, no solo a demos de
herramientas propias: opiniones que el streamer retoma más tarde, una anécdota contada en dos
partes, etc. El criterio es siempre el mismo: ¿aporta más al espectador verlo unido y fluido,
o es forzar una conexión que en realidad no existe?

### 3. Localizar los timestamps exactos de cada tramo a extraer

Con `grep -n -B1 -A1 "<frase característica>" <directo>_transcripcion.srt` localizas el
timestamp aproximado (a nivel de segmento, ±2s) de cualquier frase. Revisa el `.txt`
alrededor de esa zona para decidir el inicio/fin exactos y detectar tangentes/interrupciones
internas que convenga recortar (saludos al chat, el perro interrumpiendo, chistes
desconectados del tema, etc.) — **lee el contexto, no asumas que el rango del paso 2 es
limpio por dentro**.

### 4. Afinar cada punto de corte (inicio/fin de cada tramo que se mantiene)

Los timestamps del `.srt` son aproximados (a veces redondeados a múltiplos de 2s cuando hay
habla continua). Nunca cortes directamente en el timestamp del segmento — siempre afina así:

```bash
# 1. Detección de silencio alrededor del punto aproximado (ventana de ~6-8s)
ffmpeg -ss <aprox-3> -t 8 -i ~/Desktop/editor/crudo/<directo>.mp4 \
  -af silencedetect=noise=-22dB:d=0.1 -f null - 2>&1 | grep silence
```

Busca un hueco de silencio (idealmente >0.3s) cerca del punto objetivo y corta ahí, dejando
margen de seguridad dentro del hueco (nunca justo en el borde). Si `-22dB` no encuentra nada
útil, prueba con `-28dB` (menos sensible) o `-18dB` (más sensible) según el ruido de fondo.

Si el punto es ambiguo (varias palabras seguidas sin pausa clara, tartamudeo real del
streamer), transcribe esa ventana concreta con precisión palabra por palabra:

```bash
ffmpeg -y -ss <inicio> -t <dur> -i ~/Desktop/editor/crudo/<directo>.mp4 \
  -ar 16000 -ac 1 -c:a pcm_s16le tmp.wav
whisper-cli -m ~/.whisper-models/ggml-large-v3.bin -f tmp.wav -l es -ml 1 \
  2>&1 | grep -E "^\[00"
```

`-ml 1` fuerza segmentos de ~1 palabra con timestamp — da precisión de centésimas de segundo.
**Ojo**: en clips muy cortos y aislados, Whisper pierde contexto y a veces alucina palabras
que no se dijeron (ej. inventó "¿Otra imagen? ¿Cómo?" donde en realidad decía "como, joder").
Si una transcripción corta suena rara o sin sentido, **vuelve a transcribir con una ventana
más larga (10-15s) dando más contexto** antes de fiarte del resultado — no tomes la primera
lectura como verdad si es sospechosa.

### 5. Construir el clip final

**Usa `scripts/construir_clip.sh <origen> <salida> <start1> <end1> [<start2> <end2> ...]`** —
construye automáticamente el `filter_complex` con el micro-fade de 20ms en cada segmento
(sección 6.9) y evita errores manuales de conversión de timestamp (acepta `HH:MM:SS.ms` o
segundos sueltos, mezclados). Es el método preferido salvo que necesites algo que el script no
cubre (en ese caso, usa el patrón manual de abajo, pero añade los `afade` igualmente).

Patrón manual equivalente (para referencia, o si necesitas modificar algo puntual). Usa siempre
`filter_complex` con `trim`+`atrim`+`concat` (nunca `-c copy` con cortes internos arbitrarios —
solo sirve para recortar la cola final sin cortes intermedios). Patrón para N segmentos a
mantener:

```bash
SRC=~/Desktop/editor/crudo/<directo>.mp4
OUT=~/Desktop/editor/videos-editados/directo_<tema>_editado.mp4
ffmpeg -y -i "$SRC" -filter_complex \
"[0:v]trim=start=T0i:end=T0f,setpts=PTS-STARTPTS[v0];[0:a]atrim=start=T0i:end=T0f,asetpts=PTS-STARTPTS[a0]; \
 [0:v]trim=start=T1i:end=T1f,setpts=PTS-STARTPTS[v1];[0:a]atrim=start=T1i:end=T1f,asetpts=PTS-STARTPTS[a1]; \
 ... \
 [v0][a0][v1][a1]...concat=n=N:v=1:a=1[outv][outa]" \
-map "[outv]" -map "[outa]" -c:v libx264 -preset medium -b:v 5M -maxrate 5.5M -bufsize 10M \
-c:a aac -b:a 192k "$OUT"
```

Mantén el bitrate de vídeo (`-b:v 5M`) y audio (`-b:a 192k`) similar al original — comprueba
antes con `ffprobe -show_entries stream=width,height,r_frame_rate,bit_rate` sobre el fuente.

Lánzalo siempre en background (son renders de varios minutos). **Nunca lances un segundo
render del mismo `OUT` sin confirmar que el anterior terminó o pararlo explícitamente con
`TaskStop`** — dos procesos ffmpeg escribiendo al mismo path en paralelo compiten por CPU y
dejan el primero en un archivo incompleto (`moov atom not found`) al renombrarlo a mitad de
escritura. Si tienes dudas, comprueba `ps aux | grep ffmpeg` antes de lanzar otro.

### 6. Pasada de micro-silencios y muletillas DENTRO de cada tramo mantenido

Además de cortar tangentes/interrupciones completas (sección 3), revisa también los huecos
de duda DENTRO del contenido que vas a mantener: momentos donde el streamer se queda callado
pensando, repite "ehhh"/"eee" mientras busca una idea, o se traba y vuelve a empezar la
frase. Esto pasa sobre todo en explicaciones técnicas en directo (se atasca con un comando,
piensa en voz alta antes de encontrar la solución).

Sobre el clip YA CORTADO (puedes usarlo como su propio "source" para esta pasada, con
timestamps relativos a él, en vez de volver al directo original):

```bash
ffmpeg -i <clip>.mp4 -af silencedetect=noise=-30dB:d=0.8 -f null - 2>&1 | grep silence
```

De los huecos que salgan, **solo son candidatos a recortar los que ronden los ~1.5-2s o más**.
Pausas de 0.8-1.3s son ritmo de habla normal (coger aire, pausa antes de una idea nueva) y
cortarlas sistemáticamente hace que suene artificial/robótico — no los toques. Antes de cortar
cualquier candidato, transcribe el contexto para confirmar que es un hueco "de verdad" y no
una pausa legítima:

```bash
ffmpeg -y -ss <t-3> -t 10 -i <clip>.mp4 -ar 16000 -ac 1 -c:a pcm_s16le tmp.wav
whisper-cli -m ~/.whisper-models/ggml-large-v3.bin -f tmp.wav -l es 2>&1 | grep -E "^\[00"
```

Son pausas legítimas que **no** hay que tocar, aunque sean largas:
- Esperar una respuesta real del servidor/comando tras enviar algo (p. ej. tras un envío en
  Burp Suite) — es parte genuina de la demo, aporta suspense.
- Transición narrativa antes de empezar una idea o anécdota nueva.
- Leer un mensaje del chat antes de responder.

Son huecos a recortar:
- Dead air mientras piensa en silencio una solución, normalmente con un "ehhh"/"eee" de
  relleno al reanudar (patrón típico: "Hostia, estoy pensando... [silencio largo] ...eeeh,
  claro, estoy pensando cómo...").
- Frases que se repiten literalmente porque se trabó y volvió a arrancar.

Al recortar, no elimines el hueco entero a cero — dale el mismo tratamiento que cualquier
corte (sección 4-5): localiza dónde termina limpiamente la frase previa y dónde empieza
limpiamente la frase que retoma el hilo (saltándote el relleno/"ehhh"), y usa esos dos puntos
como `trim`/`atrim` con `concat`, igual que un corte de tangente normal, en vez de solo
recortar el silencio a un tamaño fijo.

### 6.9. Mejora clave de precisión: probabilidad por token (`-ojf`) + micro-fade en cada corte

Esto sustituye y mejora el método descrito en la sección 7 (que usaba `-ml 1` y repetir
transcripciones a ciegas esperando que coincidieran). Es significativamente más fiable y
rápido — **úsalo como método principal** para precisar cualquier corte al milímetro, no solo
para muletillas/tartamudeos sino para cualquier punto de corte fino.

**A) Obtener probabilidad real por token, no adivinar por repetición:**

```bash
ffmpeg -y -ss <inicio> -t <dur> -i <video> -ar 16000 -ac 1 -c:a pcm_s16le tmp.wav
whisper-cli -m ~/.whisper-models/ggml-large-v3.bin -f tmp.wav -l es -ojf -of tmp_out
python3 -c "
import json
d = json.load(open('tmp_out.json'))
for seg in d['transcription']:
    for tok in seg['tokens']:
        if tok['text'] != '[_BEG_]' and not tok['text'].startswith('[_TT'):
            print(f\"{tok['timestamps']['from']} -> {tok['timestamps']['to']}  p={tok['p']:.3f}  '{tok['text']}'\")
"
```

Cada token (no cada palabra completa — a veces un token es media palabra) trae su `timestamps`
exacto Y su `p` (probabilidad/confianza del decoder, 0-1). Esto es **la señal de fiabilidad que
antes había que adivinar repitiendo transcripciones**:

- `p` alto (>0.6-0.7) en varios tokens consecutivos que forman una repetición real (p. ej. dos
  "más o menos" seguidos, cada uno con sus tres tokens en ese rango) → la repetición es
  **real**, confía en los timestamps y corta ahí.
- `p` muy bajo generalizado en una zona, o un patrón de repetición absurda (la misma palabra
  5+ veces seguidas) → casi seguro alucinación del modelo en esa zona concreta de audio
  (ocurre en tramos con voz rápida/floja/ruido de fondo) — no confíes en el contenido ahí,
  prueba una ventana más amplia o acepta no poder verificarlo con confianza.
- Esto resuelve además el problema de "-ml 1 no coincide con el modo normal": usa `-ojf` en
  modo normal (sin forzar `-ml 1`) y lee `p` por token — es más preciso que ambos métodos
  anteriores combinados.

Nota: la opción `-dtw <modelo>` (timestamps por token vía Dynamic Time Warping, alineación real
del modelo) existe pero en las pruebas no dio `t_dtw` útil (apareció `-1`) — no es necesaria,
los timestamps normales + `p` ya son suficientes.

**Importante — `-ojf` con `p` no es inmune a alucinaciones si la ventana es demasiado corta.**
Confirmado en auditoría: una ventana de ~15s con `-ojf` puede seguir alucinando una frase
completa repetida 3 veces con probabilidades razonablemente altas (no bajas como cabría
esperar de una alucinación) — es decir, **el valor de `p` no detecta este tipo de alucinación
por repetición de frase**, solo ayuda a detectar palabras sueltas mal reconocidas. La única
forma fiable de descartar esto es repetir la comprobación con una **ventana más ancha (18-20s)
en modo normal** y comprobar que el contenido fluye hacia información NUEVA en vez de quedarse
dando vueltas sobre la misma frase. Si una frase se repite 2+ veces de forma casi idéntica en
una ventana corta, sube la ventana a 18-20s antes de decidir si es real.

**B) Aplicar un micro-fade de ~20ms en CADA corte, no solo cuando "falta silencio":**

Un corte seco (sin fade) en un punto sin silencio real casi siempre produce un **clic** de
discontinuidad de amplitud. Ese clic, en las pruebas, **confundía a Whisper al verificar el
resultado** — llegó a "oír" una palabra extra que no estaba ahí, dando la falsa impresión de
que el corte había dejado basura cuando en realidad el corte era correcto y el problema era el
clic en sí. Aplicar un fade de entrada/salida de ~20ms en cada segmento ANTES de concatenar
elimina el clic sin que se note como un "fundido" (muy por debajo del umbral perceptible) y
hace que la verificación posterior sea fiable:

```
[0:a]atrim=start=T0:end=T1,asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st=<T1-T0-0.02>:d=0.02[a0];
```

`afade=t=out:st=X:d=0.02` necesita `st` en segundos **relativos al inicio del propio
segmento** (duración del segmento menos 0.02), no en el timeline absoluto. Aplícalo a **todos**
los segmentos de audio de la cadena `concat`, no solo a los que parecían arriesgados — es
barato y nunca perjudica.

**Flujo recomendado actualizado** (sustituye el flujo de las secciones 4-5-7 para cortes finos):
1. Localiza el candidato en el transcript original.
2. `-ojf` en modo normal sobre una ventana de contexto amplio (10-15s) → lee `p` por token.
3. Si la confianza es razonable y el patrón de repetición/lapsus es claro en los timestamps,
   fija los dos puntos de corte ahí mismo.
4. Construye el clip con `afade` de ~20ms en cada segmento.
5. Verifica transcribiendo el resultado — ahora sí puedes confiar en que una transcripción
   "rara" en la verificación significa un problema real, no un artefacto de clic.

### 7. Pasada de muletillas, tartamudeos, lapsus y redundancias claras

Además de la pasada de silencios/dead-air (sección 6), el usuario puede pedir una limpieza
más fina y agresiva de **muletillas** ("eh", "o sea", "bueno", "vale" cuando son tics puros),
**tartamudeos** (repetir la misma palabra/sílaba por trabarse), **lapsus** (decir algo mal y
autocorregirse) y **redundancias claras** (repetir la misma frase/idea dos veces sin aportar
nada nuevo). El objetivo es que quede "lo más fluido posible", pero sin pasarse — cortar cada
"eh"/"bueno" suelto que usa como conector natural lo haría sonar artificial. Criterio: solo
toca lo que sea **claramente** prescindible.

**Proceso por candidato** (del transcript original completo, no solo del tramo ya cortado):

1. Localiza el candidato en el `.txt`/`.srt` original (frases tipo "X X" repetida, muletillas
   apiladas, "no, bueno, en verdad, en X" como posible lapsus).
2. **Verifica con una transcripción de contexto amplio (10-15s, modo normal, SIN `-ml 1`)
   antes de tocar nada.** Esto es crítico — ver más abajo por qué.
3. Si se confirma, busca el límite exacto con `silencedetect` a umbral sensible
   (`-noise -20dB -d 0.05`) para encontrar la micro-pausa entre repeticiones/palabras.
4. Aplica el corte (trim/atrim/concat, igual que cualquier otro) y **verifica el resultado
   transcribiendo el clip ya construido**, no solo prediciendo desde el audio fuente.
5. Si la verificación en el paso 2 o en el paso 4 da resultados **inconsistentes entre
   intentos** (ver más abajo), no apliques el corte — es más seguro dejarlo tal cual que
   arriesgarse a un corte mal hecho que no puedes confirmar.

**Lección aprendida — por qué el paso 2 y el modo `-ml 1` no son de fiar a ciegas:**

Whisper **alucina y pierde palabras repetidas con mucha frecuencia** en frases cortas, rápidas
o con repeticiones reales. Se ha comprobado en la práctica que:
- La transcripción completa inicial (la que arma la tabla de temas) a veces **inventa**
  muletillas que no existen en el audio real (ej. detectó "pues, bueno," que, comprobado con
  más contexto, nunca se dijo).
- El modo `-ml 1` (fuerza segmentos de ~1 palabra) a veces **omite** una repetición real que sí
  aparece en el modo normal (ej. no captó un "lo lo lo" que el modo normal confirmó dos veces
  de forma consistente), y otras veces **inserta palabras partidas** como si fueran repetidas
  (p. ej. partió "enero" en "en"+"ero" y lo leyó como "en en ero", pareciendo un tartamudeo que
  no era tal).
- Transcribir la MISMA ventana de audio corta dos veces puede dar **dos resultados distintos**
  (a veces hasta con alucinaciones evidentes tipo repetir una palabra 7 veces seguidas, p. ej.
  "match" x7 — señal inequívoca de alucinación, ignóralo).

Por eso: **nunca cortes solo porque una pasada de `-ml 1` lo sugiere.** Confírmalo con al menos
una transcripción de contexto amplio en modo normal, y si los intentos no son consistentes
entre sí, trátalo como no confirmado y no lo toques — la prioridad es no romper el audio, no
cazar cada tic.

**Qué SÍ suele ser seguro cortar** (bajo riesgo, alto valor):
- Una frase completa que repite literalmente la idea de la frase anterior sin novedad
  (termina y empieza en un límite de frase/puntuación, aunque no haya silencio real ahí).
- Una muletilla aislada (p. ej. un "bueno," suelto) entre dos palabras con coma/pausa a ambos
  lados, confirmada en una transcripción de contexto amplio.
- Un lapsus claro de corrección ("en Navidad, no, en enero") — corta el dato erróneo y el "no,"
  que lo corrige, deja solo el dato correcto.

**Qué es más arriesgado y conviene revertir si no se puede verificar con confianza**:
- Repeticiones exactas de 2-3 palabras en alta velocidad sin pausa real entre ellas (el límite
  exacto palabra-por-palabra es muy difícil de clavar y una transcripción corta del resultado
  rara vez confirma limpiamente que quedó bien).
- Cualquier "muletilla de estilo" que el streamer repite de forma consistente a lo largo de
  todo el contenido (p. ej. repetir un adjetivo dos veces para dar énfasis, "está muy bien,
  está muy bien") — es su forma de hablar, no un error, no lo toques.

### 8. Verificar TODOS los puntos de unión (inicio, cada corte interno, final)

Nunca des un clip por bueno sin verificar. Para cada punto de unión (inicio del clip, cada
corte interno, final del clip):

```bash
ffmpeg -y -ss <t-3> -t 8 -i <clip-final>.mp4 -ar 16000 -ac 1 -c:a pcm_s16le j.wav
whisper-cli -m ~/.whisper-models/ggml-large-v3.bin -f j.wav -l es 2>&1 | grep -E "^\[00"
```

Lee el resultado: la frase debe fluir sin cortarse a medias ni repetir contenido. Si algo
suena raro, vuelve al paso 4 con un rango más amplio y una transcripción con más contexto
(un clip de 6-8s aislado puede sonar mal transcrito sin ser un problema real de corte —
confírmalo con una ventana más grande antes de tocar nada).

Comprueba también la duración total del archivo final contra la suma esperada de los tramos
mantenidos (`ffprobe -show_entries format=duration`) — si no cuadra, algo falló en el filtro.

Opcionalmente, revisa silencios anómalos en todo el clip terminado:
```bash
ffmpeg -i <clip-final>.mp4 -af silencedetect=noise=-30dB:d=1.0 -f null - 2>&1 | grep silence
```
Pausas naturales de 1-2.5s son normales (piensa, espera un comando, lee el chat, tartamudea).
Sospecha solo de silencios mucho más largos o patrones raros.

### 9. Limpieza

Borra los `.wav` temporales de verificación del scratchpad al terminar cada clip. **Nunca
borres** la transcripción `.srt`/`.txt` de `~/Desktop/editor/crudo/` (sirve para futuros
fragmentos del mismo directo) ni el modelo de `~/.whisper-models/`.

## Ver fotogramas del vídeo (no estás completamente a ciegas)

Puedes extraer un fotograma suelto en cualquier timestamp y leerlo como imagen (tienes visión
sobre imágenes, aunque no veas vídeo en movimiento):

```bash
ffmpeg -y -ss <timestamp> -i <video>.mp4 -frames:v 1 frame.png
```

Luego usa la herramienta de lectura de archivos sobre `frame.png`. Útil para comprobar
composición (dónde está la cámara, el chat, el código en pantalla) antes de aplicar cualquier
efecto visual (zooms, recortes, etc.) sobre un tramo concreto.

## Errores ya cometidos (para no repetirlos)

- Confundir `01:HH:MM` con `00:HH:MM` al buscar timestamps en el `.srt` (verifica siempre el
  prefijo de hora antes de hacer `grep`).
- Asumir que el rango aproximado de un "tema interesante" está limpio por dentro — siempre
  puede haber una interrupción del perro, un saludo al chat, o una tangente que conviene
  cortar también.
- Lanzar un segundo render de ffmpeg sobre el mismo archivo de salida sin comprobar que el
  anterior ha terminado (ver sección 5).
- Fiarte de una transcripción de un clip aislado muy corto sin contexto si el resultado suena
  extraño — repítela con una ventana más larga.
