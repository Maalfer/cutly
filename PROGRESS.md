# PROGRESS

## Decisiones
- Desarrollo en el VPS actual (2 CPU, 1,8 GB, sin GPU, compartido con correo): solo código y pruebas con vídeos de segundos. Producción en un VPS más potente (migración prevista) → `Transcriber` detrás de interfaz.
- API keys: sha256 del token (alta entropía). Contraseñas: argon2.
- Subida por trozos: protocolo propio (`POST /uploads`, `PUT /uploads/{id}/chunks/{n}`, `POST …/complete`), trozos de 32 MB (compatible con límite 100 MB de Cloudflare).
- Cloudflare en modo solo DNS (nube gris) para `editor.cogny.es`. Certbot DNS-01 en Fase 3.
- Sin Docker ni Redis en esta máquina: tests de cola con fakeredis.

## Fase 1
- [x] 1. Esqueleto, config, BD (SQLite WAL), auth (sesión + API keys), Compose, tests
- [x] 2. Subida por trozos reanudable (+ simple), ffprobe, proxy 540p, peaks, worker RQ con progreso/cancelación/timeout, endpoints de media y jobs, 16 tests
- [x] 3. Transcripción: interfaz `Transcriber`, faster-whisper por ventanas cortadas en silencios, API (lanzar, leer JSON/texto, editar segmento), 23 tests
- [x] 4. Candidatos a clip elegidos por el agente (ajuste a frases, deduplicado, API); claves API en la web + guía para agentes + script de subida. 31 tests
- [x] 5. Alembic + esquema de proyecto (6 tipos de layer), operaciones atómicas por lotes, historial deshacer/rehacer con control de concurrencia, API `/projects`. 58 tests
- [x] 6. Render extremo a extremo (reencuadre, subtítulos ASS, texto/forma/icono, audio medido, borrador y final), 68 tests
- [ ] 7. Registro de efectos, assets, presets
- [ ] 8. Verificación
- [ ] 9. Servidor MCP

## Pendiente técnico
- Alembic: hoy `create_all`; añadir migraciones antes de producción.
- Tabla de sesiones/rate limit en memoria (suficiente con un solo proceso API).

## Notas del paso 2
- Subida: `POST /uploads` → `PUT /uploads/{id}/chunks/{n}` (cuerpo crudo, `X-Chunk-SHA256` opcional, idempotente) → `GET /uploads/{id}` para reanudar → `POST /uploads/{id}/complete`. El archivo se escribe en su sitio (sin duplicar disco).
- Subida simple: `POST /media/simple?filename=x.mp4` con cuerpo crudo (máx. 100 MB por defecto). Sin multipart a propósito: Starlette lo volcaría a `/tmp` (tmpfs en RAM en esta máquina).
- Peaks: 20 pares min/max por segundo en `.npy` int8 (≈0,9 MB para 6 h); `GET /media/{id}/peaks?start&end&bins` devuelve el tramo reducido.
- Proxy: H.264 540p, keyframe cada 1 s, `+faststart`, `nice -n 10`. Medido en este VPS (2 CPU): ~4,2× tiempo real con 1080p30 sintético → un directo de 5 h tardará aprox. 1,2–2,5 h.
- Los jobs se cancelan vía BD (el runner consulta el estado cada 0,5 s y mata el subproceso).
- `CUTLY_QUEUE_MODE=inline` ejecuta los jobs al momento (tests y desarrollo sin Redis).
- Pendiente: el worker real con Redis solo se probará en Docker/VPS (aquí no hay Redis).

## Notas del paso 3
- El audio se extrae a PCM 16 kHz y se transcribe en ventanas de 10 min cortadas en el punto más silencioso (±15 s): nunca más de ~40 MB de audio en RAM, sin solapes.
- Filtro de alucinaciones (Amara.org, etc.) y VAD. Idioma fijado con la primera ventana si se autodetecta.
- Editar un segmento: mismo nº de palabras conserva tiempos; si cambia, reparte proporcionalmente.
- `CUTLY_TRANSCRIBER_BACKEND=remote` está reservado (contrato en `services/transcribe/remote.py`).
- Validado el arranque real del motor (modelo `base`, 10 s, pico 530 MB). **Sin validar** con voz española real: falta un fragmento de directo.

## Despliegue actual (este VPS) — https://editor.cogny.es
- Sin Docker: `cutly-api` (uvicorn 127.0.0.1:8321) y `cutly-worker` (RQ) como servicios systemd (`deploy/`), Redis local (64 MB, solo localhost), Nginx existente (`deploy/nginx-editor.cogny.es.conf`), certificado Let's Encrypt (webroot, renovación automática).
- DNS en Cloudflare: registro A solo-DNS (sin proxy). El token no se guardó en ningún sitio.
- Límites del worker: Nice 12, CPUQuota 150 %, MemoryMax 900 MB, IO idle. Modelo Whisper `base` por la RAM disponible.
- Web: Preact + htm vendorizados (sin build), CSP estricta, responsive. Login `mario`. Comprobada por HTTPS (login, subida, worker RQ, rangos, peaks) y que los 45 imports resuelven; **no revisada visualmente en un navegador**.
- Actualizar: `git pull` (o editar) → `uv sync --extra whisper` → `sudo systemctl restart cutly-api cutly-worker`.
- Disco: 71 GB libres; un directo de 5 h son 10–25 GB + proxy. Activar limpieza de originales cuando haga falta.

## Notas del paso 4
- Integración principal = **API key + REST** (estilo SysReptor): el usuario crea la clave en la web (Claves API), se la pasa a Claude Code y este usa los mismos endpoints. `GET /api/v1/agent-guide` (Markdown con la URL real) y `web/tools/upload.py` (subida reanudable, solo stdlib). El servidor MCP del paso 9 queda como extra opcional.
- **Decisión (2026-10-26): Cutly no usa ninguna API de IA externa.** Se eliminó el selector de clips con Anthropic (`ANTHROPIC_API_KEY`, `CUTLY_CANDIDATES_*`, extra `anthropic`, job `candidates.propose`). El agente lee la transcripción por bloques (`GET /media/{id}/transcript?format=text&start&end`) y registra los clips con `POST /media/{id}/candidates`; el servidor ajusta a frases, descarta solapes y valida duraciones. La transcripción sigue siendo local (faster-whisper).

## Notas del paso 5
- **Alembic activo**: `init_db()` migra al arrancar (una BD previa sin `alembic_version` se marca como 0001). Migraciones en `src/cutly/db/migrations/versions/`; el test `test_fresh_db_matches_models` falla si cambias un modelo sin migración. Al generar migraciones fija SIEMPRE `CUTLY_DATABASE_URL` a una BD temporal (ver `alembic.ini`). Backup previo en `~/.cache/backups/`.
- Columnas NOT NULL nuevas necesitan `server_default` (lo cazó el test de BD antigua).
- Proyecto = `ProjectDoc` (Pydantic estricto, `extra=forbid`): colores hex, ids de asset, texto sin control, `params` de efecto acotados → base del saneado contra inyección en FFmpeg/ASS. Tiempos: timeline en s del original; layers en s del clip resultante; geometría 0-1.
- Historial = diferencias por clave de primer nivel (`forward`/`inverse`), máx. 200 pasos; un cambio nuevo tras deshacer descarta lo rehacible; las operaciones sin efecto no crean paso.
- Concurrencia optimista: `Project.version` + `base_version` opcional → 409.
- Los subtítulos que cubren todo el clip siguen la duración al recortar.
- Bug encontrado en producción y corregido: borrar un proyecto con historial daba 500 (FK). Regla: sin `relationship()`, borrar hijos → `flush()` → borrar padre.
- Esquema de proyecto versionado (`schema/versioning.py`); aún sin migraciones reales (solo v1).
- Pendiente de pasos siguientes: validación de `asset` y `effect` contra el registro (paso 7), render (paso 6).

## Notas del paso 6
- Un comando FFmpeg por render: una entrada por clip con `-ss` previo (no decodifica el directo entero), `-filter_complex_script`, capas en orden de z (las de ASS consecutivas se agrupan en un fichero; iconos/imágenes son overlays). Todo valor del grafo es numérico formateado, color validado o ruta generada por el servidor (alfabeto comprobado).
- **Memoria (crítica en este VPS)**: `loudnorm` en el grafo costaba +340 MB (reescala a 192 kHz). Sustituido por normalización en dos pasadas: análisis solo-audio con `ebur128` + `volume` fijo + `alimiter` (más preciso y ligero). Pico medido ≈ 410 MB con reencuadre stack + subtítulos + icono en 1080×1920. `-threads 2 -filter_threads 1` y x264 con `rc-lookahead=8`. Prueba siempre con `systemd-run -p MemoryMax=900M -p MemorySwapMax=0` (como el servicio real).
- Ojo: el host usaba 3,5 de 4 GB de swap antes de renderizar; un render grande sin límite provocó OOM global (solo cayó mi ffmpeg).
- SVG: saneador por lista blanca (rechaza script/eventos/image/use/entidades/url externa), resvg para rasterizar; iconos propios CC0 en `assets/icons/`.
- ASS: todo texto pasa por `ass_escape` (el streamer puede decir `{\\pos}`); karaoke = un evento por palabra con la activa resaltada.
- No soportado todavía (avisa en `warnings`): `keyframes`, capas `effect`, `pop`/`zoom_in` en iconos (se aproxima con fundido), animación de salida distinta de fundido.
- Fuente por defecto DejaVu Sans; fuentes propias vendrán con la biblioteca de assets (paso 7).

## Hito de edición profesional (animaciones, efectos, fuentes, verificación parcial)
- Motor de animación único (`services/render/animation.py`): enter/exit simétricos, loops (pulse/wiggle/float/blink/shake) y keyframes con easing; texto/formas por tramos en ASS, iconos/imágenes por secuencia de PNG (Pillow). Giro positivo = horario.
- Registro de efectos (`registry/effects.py`): 12 incluidos (`effects/<n>/`), `region` para limitar el efecto a una zona, efectos declarativos creables por API (lista blanca de filtros + prueba real con FFmpeg). `GET/POST/DELETE /effects`.
- Fuentes OFL en `assets/fonts`; validación de efectos/assets/fuentes al crear capas (errores con sugerencias).
- Transcripción: `vocabulary` y `beam_size`; corrección de palabras conservando tiempos (`PATCH …/segments/{id}/words`).
- Subida del navegador rehecha (trozos de 4 MB, XHR con progreso real, vigilancia de bloqueo, reintentos, reanudación), probada con Node.
- Bug grave corregido: envolvente `decay` con `exp()` desbordado → `NaN` oscurecía el vídeo con destellos lejanos.
- Edición real de «apps linux.mp4» vía API: ver `scripts/apps_linux/` y `docs/HANDOFF.md` §10.
- Pendiente principal: endpoints de verificación (fotograma/tira/checks), API de assets, presets, transiciones, MCP. Ver `docs/HANDOFF.md` §7.

## Hito: verificación, assets, presets y transiciones (2026-10-26)
- **Verificación para agentes** (`api/routers/verify.py`, `services/verify/`): `GET /projects/{id}/frame` (fotograma con capas; job en el worker, `wait` bloquea), `filmstrip` (hoja de contacto con tiempos), `POST …/frames`, `GET /frames/{job}/{name}`, `GET /media/{id}/frame?grid=true` (original con rejilla 0–1), `audio-stats` (LUFS/pico/silencios), `GET /projects/{id}/transcript` (hablado en el reloj del clip), render parcial `start`/`end`, y **checks** (caras tapadas con OpenCV Haar sobre el proxy llevadas al reencuadre, fuera de pantalla, zonas de UI de la app, solapes, tamaño, cortes a mitad de palabra/frase con sugerencia, audio, densidad de efectos).
- Técnica del fotograma/tramo: se recorta solo la línea de tiempo y se desplaza el reloj (`setpts=PTS+t0/TB`): las capas conservan sus tiempos absolutos y no se tocan.
- **Assets** (`api/routers/assets.py`, `services/assets/library.py`): manifiesto + 45 iconos propios (CC0, `scripts/gen_icons.py`) + 5 fuentes OFL; subida con saneado/validación (SVG lista blanca, imágenes ≤4096 px, fuentes con fc-scan), borrado, vistas previas y hoja de contacto.
- **Presets** (`api/routers/presets.py`, `services/presets/`, `presets/`): 50 incluidos (7 subtítulos, 9 texto, 8 animación, 6 color, 9 transición, 11 capas), propios por API, validados contra el esquema real; `POST /projects/{id}/presets/apply` = operación normal con historial. Migración 0003 (`preset.description`).
- **Transiciones** (`TimelineClip.transition_in`, op `set_transition`): `xfade` + `acrossfade`, mezcla con cortes; `duration`, mapa de tiempos de subtítulos, `slice` y checks usan `timeline_starts`.
- Efectos: `docs/ADDING_EFFECTS.md` + `effects/_template/`; tests de imagen de referencia en `tests/golden/` (`UPDATE_GOLDEN=1` regenera; revisa SIEMPRE las imágenes antes de fijarlas).
- Proxy: ahora el lado corto a 540 px (en vertical 540×960). Los proxies anteriores siguen siendo 304×540: regenerar con `POST /media/{id}/proxy`.
- **BUG GRAVE corregido**: el handler de render había perdido la pasada de medición de volumen (mi parche no encajó con el código ya formateado y `ruff --fix` borró los imports), de modo que **ningún render normalizaba el audio**. Test de regresión que mide el LUFS del MP4. Lección: tras un reemplazo de texto, comprobar que se aplicó; y no confiar en `ruff --fix` para imports "sin uso".
- OpenCV: fijado `opencv-python-headless>=4.10,<5` (la 5.0 ya no trae `CascadeClassifier`).
- Pendiente: MCP (opcional), editor visual de línea de tiempo, renderer Chromium, UI de proyectos en la web, limpieza automática de renders/fotogramas (los fotogramas se podan a las 24 h).

## Hito: animaciones explicativas (capa `scene`) — 2026-10-26
- Nuevo tipo de capa `scene` (`schema/scene.py`, `services/scene/`): motor de escenas 2D propio (OpenCV + Pillow + numpy, **sin Chromium**: no cabe en este VPS) que genera una secuencia PNG con alfa superpuesta por FFmpeg (mismo mecanismo que los iconos animados). Objetos: node (23 glifos vectoriales), text, card, link, dot (viajero con estela), ring, burst, meter; cámara con seguimiento, fondo espacial/rejilla/transparente, objetos `fixed` en pantalla.
- Sin estado entre fotogramas (todo es función del tiempo): `frame`, `filmstrip` y los renders por tramos (`start`/`end`) generan solo los fotogramas necesarios.
- 7 plantillas (`packet_network`, `flow_steps`, `dns_lookup`, `tls_handshake`, `url_anatomy`, `recap_cards`, `title_card`) que se ajustan a la duración de la capa y a la orientación (`wide` 1600×900 / `tall` 900×1600). Inspiradas en las animaciones de `yt/`.
- API (`api/routers/scenes.py`): `GET /scenes/templates[/{n}]`, `POST /scenes/build` (expande una plantilla a JSON editable), `GET /scenes/schema`, `POST /scenes/preview` (PNG con N fotogramas, sin crear proyecto; un preview a la vez). Hook de validación (plantilla, parámetros, fuentes). Docs: `docs/SCENES.md` y §2b de `AGENT_GUIDE.md`.
- Editor web: pestaña «Animaciones» en la biblioteca, marcador punteado en el escenario y «▶ Vista previa» en el inspector (imagen generada por el servidor). **El editor no anima la escena en vivo**; solo se ve al renderizar o con la vista previa.
- Coste medido (VPS, 1080×1920 final): ~0,1–0,3 s por fotograma; FFmpeg con dos escenas superpuestas llegó a ~770 MB RSS (dentro del límite de 900 MB del worker, pero ajustado): no renderizar escenas a pantalla completa de más de ~40 s en final.
- Tests: `tests/test_scenes.py` (esquema, determinismo, cámara, plantillas wide/tall a varias duraciones, API, render real con FFmpeg, ventana de fotogramas).
- Pendiente: plantillas nuevas bajo demanda (es una función `(params, B)` en `services/scene/templates.py`), más glifos, vista previa viva en el navegador (portar el motor a JS), animación de la escena sincronizada con palabras de la transcripción.

## Hito: escenas con código (`code`, motor de navegador) — 2026-10-26
- **Decisión que corrige la del hito anterior**: Chromium headless **sí cabe** en este VPS si se usa con cuidado
  (medido: pico ~860 MB generando 20 s a 1080×1920, dentro del límite de 900 MB del worker, pero ajustado). Pedido
  explícito del usuario: que un agente pueda escribir HTML/Canvas con total libertad (igual que los `.html` de
  `yt/`: cámara propia, partículas, callout inferior con texto largo, letterbox…), no solo las 8 plantillas
  declarativas. El motor declarativo (hito anterior) se queda tal cual para lo que ya cubre bien y es mucho más barato.
- `SceneLayer` ahora acepta una tercera fuente, exclusiva con `template`/`scene`: `code` (el HTML completo) + `fps`
  opcional. Nuevo paquete `services/scene_js/` (extra opcional `scene-js`, añade `playwright`; usa el `/usr/bin/chromium`
  del sistema, no el navegador propio de Playwright).
- **El problema real y cómo se resolvió**: el tiempo virtual nativo de Chromium (`Emulation.setVirtualTimePolicy` vía
  CDP) no sirve para esto — avanzar el presupuesto no garantiza que el `<canvas>` se repinte en cada
  `requestAnimationFrame` pendiente (probado con `--headless=new` y también con los flags de sincronización de
  compositor que recomienda Chrome para este caso; el estado de la animación se quedaba parado). La solución fue
  un harness JS (`_HARNESS` en `renderer.py`) inyectado con `add_init_script` ANTES que el documento del agente:
  sustituye `performance.now`/`requestAnimationFrame`/`cancelAnimationFrame` por versiones controladas por un reloj
  virtual que Python avanza paso a paso (`1000/fps` ms), con un `page.screenshot()` tras cada paso. Determinista de
  verdad (test: dos sesiones generan bytes idénticos) y no depende de la velocidad real de la máquina.
- La página navega por una URL `data:` (nunca `file://`: no expone el sistema de archivos) y **toda petición de red se
  aborta** (`page.route("**/*", ...abort)`) — probado con `fetch`/`<img>` reales, ambos bloqueados. El documento debe
  ser enteramente autocontenido.
- Límites más estrictos que las escenas declarativas, dado el coste real medido: 30 s por capa (no 120), caja ≤
  1920² (no 4096²), ~12× más lento que tiempo real para generar la secuencia completa. El estado es acumulativo
  (como un vídeo grabado): un fotograma suelto o un render por tramos obliga a simular TODO desde el principio.
  Un error de JS a mitad de animación (p. ej. `null.boom()`) se reporta como aviso y conserva los fotogramas previos
  en vez de tirar todo el render.
- **Incidente en el despliegue (corregido en el momento)**: `uv sync --extra scene-js` en producción desinstaló
  `faster-whisper` y `mcp` (transcripción real rota unos minutos). `uv sync --extra X` instala la base + SOLO los
  extras nombrados en esa llamada, no los une a los que ya estuvieran instalados: hay que listar siempre TODOS los
  extras que deben quedar presentes (`uv sync --extra whisper --extra scene-js --extra mcp`), nunca solo el nuevo.
- `POST /scenes/preview` acepta `code` (con `width`/`height`/`fps` propios); `POST /scenes/build` lo rechaza (no hay
  JSON al que «expandirlo»). El hook de validación de capas no hace un dry-run con Chromium (sería lento en el
  camino caliente de guardar); los errores de JS se ven en el preview o al renderizar.
- Tests: `tests/test_scenes_js.py` (esquema, determinismo byte a byte, cambio real en el tiempo, bloqueo de red,
  error de sintaxis al cargar, error a mitad de animación, caja sin `h`, ventana de fotogramas, API, render real
  end-to-end). Se saltan solos si no hay Chromium/Playwright instalado.
- Aplicado de inmediato al vídeo real `race.mp4` del usuario: ver nota en §10 (o la sección correspondiente) con la
  escena de «condición de carrera» escrita en este estilo.
- Pendiente: aislar el proceso de Chromium en su propio cgroup/subproceso con límite de memoria independiente del
  resto del worker (hoy comparte el límite de 900 MB de `cutly-worker.service`; si una escena se pasa de memoria,
  el OOM del cgroup puede matar cualquier otro trabajo en curso del mismo worker, no solo el renderizado de la
  escena). Por ahora, mitigado con los límites de tamaño/duración y la regla de "una escena de código por vídeo".

## Arreglo: escenas `code` en negro en el editor — 2026-10-26
- Causa: `scene-live.js` enviaba el código por un `<input>` de una línea, que elimina los saltos de línea; un `//` en la primera línea del script del agente comentaba todo lo demás y la escena nunca arrancaba (canvas 300×150 vacío sobre fondo negro). Ahora usa `<textarea>`. Verificado con Chromium real contra el editor: la escena anima al reproducir y al saltar en la línea de tiempo.

## Mejoras para que la IA cree escenas `code` — 2026-10-26
- `POST /scenes/lint` (`services/scene_js/lint.py`): ejecuta la escena en Chromium con ganchos de observación (canvas `fillText`,
  `Date.now`, timers, CSS animations) y devuelve `issues` accionables + muestras (% de píxeles no negros). ~10 s para 9 s de escena.
- `GET /scenes/code-kit`: reglas de diseño + plantilla base (`services/scene_js/kit/base.html`, limpia en el lint).
- `window.CUTLY_PARAMS` (= `layer.params`) en render, `/scenes/preview` y `/scenes/live-doc` (editor en vivo).
- El iframe del editor se maqueta a tamaño real de salida y se reduce con `transform: scale` (preview fiel).
- Pendiente: palabras de la transcripción como `CUTLY_WORDS`, captura del editor con el vídeo detrás, aislar Chromium en su cgroup.

## Palabras de la transcripción en escenas + herramientas por capa — 2026-10-26
- `window.CUTLY_WORDS` (palabras dichas durante la capa, relativas a su inicio): render (`graph.py`), `/scenes/preview`, lint,
  `/scenes/live-doc` y editor en vivo (`stage._layerWords`). La plantilla base trae `saidAt()`/`currentWord()`.
- `GET /projects/{id}/words?q=`, `POST /projects/{id}/layers/{id}/lint`, `GET /projects/{id}/layers/{id}/scene-preview`.
- `POST /projects/{id}/checks` incluye avisos de escenas `code` (red/WebGL/solape/duración).
- Bug corregido: el render cargaba la escena como `data:` sin `charset=utf-8`; sin `<meta charset>` las tildes salían rotas.

## Vista compuesta barata de escenas `code` — 2026-10-26
- `GET /projects/{id}/layers/{layer_id}/composite?times=`: vídeo base SIN la capa (job `frames`, solo FFmpeg) + una única simulación
  de la escena a tamaño real para todos los instantes (`render_js_preview`), reducida y pegada en su caja. Aproximaciones: por
  encima de todas las capas, aplica `opacity`, no `animations.enter/exit`. `/frame` sigue siendo la verificación exacta.

## Más control para agentes: ripple_delete, auto-cut, dry_run, summary y MCP — 2026-10-26
- Op `ripple_delete` (`schema/ops.py`): quita un tramo del clip resultante, parte clips, adelanta `start_at` y recoloca/recorta/borra capas.
- `POST /projects/{id}/auto-cut` (dry_run por defecto): pausas largas + muletillas desde la transcripción, un único paso de historial.
- `POST /projects/{id}/ops?dry_run=true` y `GET /projects/{id}/summary` (todo en el reloj del clip resultante).
- Servidor MCP stdio de un solo archivo sin dependencias: `web/tools/cutly_mcp.py` (12 herramientas; devuelve imágenes). Tests en `tests/test_mcp_server.py`.

## MCP v2 — 2026-10-26
- `web/tools/cutly_mcp.py` v2.0: `instructions` (playbook en el contexto del modelo), 5 `prompts` (edit_short, clip_hunter, explain_with_animation,
  cleanup_dead_air, polish_and_verify), 3 `resources`, anotaciones readOnly, 24 herramientas. Compuestas: `cutly_review` (resumen+checks+audio+hoja de
  fotogramas elegidos por capa), `cutly_layer_check`, `cutly_media`, `cutly_overview`, `cutly_catalog`, `cutly_render`/`cutly_job`/`cutly_transcribe` (esperan y dan enlaces).
- Probado contra producción con claves temporales (borradas).

## Móvil / responsive — 2026-10-26
- Editor ≤1000 px rehecho: el estilo en línea de la rejilla de escritorio anulaba el CSS móvil (panel inferior sin altura); ahora solo se aplica en escritorio. Layout: vista previa arriba (botón ⤢ para ampliarla), panel inferior y barra de 5 pestañas (Edición, Capas, Biblioteca, Texto, Ajustes; punto en Ajustes si hay selección). Apaisado: escenario a la izquierda y panel a la derecha. Teclado en pantalla: `visualViewport` → `--vvh`/`data-kbd`.
- Barra superior compacta: «Exportar» agrupa Comprobar, nuevo clip, renombrar y fotograma exacto. Menús a todo el ancho y se cierran al tocar fuera (`useDismiss`).
- Línea de tiempo táctil: medidas mayores con puntero grueso, pellizco = zoom, arrastrar algo sin seleccionar = desplazar (no mueve clips por accidente), asas de recorte más anchas.
- Escenario: pellizco con dos dedos redimensiona la capa seleccionada, asas de esquina más grandes, tocar la capa seleccionada abre sus ajustes; `playsinline` en el vídeo.
- Campos a 16 px (sin zoom de iOS) y objetivos de ≥40 px con `pointer: coarse`; botones del escenario legibles en tema claro.
- Resto de la web: botón «Abrir en el editor» en la ficha del vídeo, fecha «Invalid Date» de las claves API corregida, sin desbordes horizontales (390/360/768 px).

## MCP v2.1 — autopilot (2026-10-26)
- `POST /projects/{id}/autopilot` (dry_run por defecto): cortes + estilo de subtítulos + zooms de empalme + audio, en un paso de historial. `_plan_cuts` extraído de auto-cut. Test en `tests/test_ripple_autocut.py`.
- MCP 2.1: `cutly_quick_edit` (de bruto a edición base con hoja de fotogramas), `cutly_autopilot`, prompt `edit_raw`. Probado en producción con clave temporal (borrada) y proyecto temporal (borrado).

## MCP v2.2 — ritmo y repeticiones (2026-10-26)
- auto-cut/autopilot: detección de repeticiones/falsos arranques; autopilot: zooms de ritmo (`max_static`). `GET /projects/{id}/pacing` + `cutly_pacing` (también dentro de `cutly_review`). Tests ampliados.

## MCP v2.3 — menos fricción al componer (2026-10-26)
- Nuevo `GET /projects/{id}/safe-zones`: detección de cara reutilizando `detect_faces`/`source_rect_to_output` de checks.py, expuesta de forma proactiva (antes solo se veía al revisar, vía `covers_face`). `POST /projects/{id}/words` para localizar varios términos en una llamada. MCP: `cutly_safe_zones`, `cutly_words` con `queries`. Motivado por la fricción real al editar race.mp4 con el MCP: 10 llamadas sueltas a cutly_words y 3 rondas de mover rótulos por culpa de la cara.

## MCP v2.4 — galería de efectos dibujados (2026-10-26)
- El usuario pidió explícitamente ir más allá de los zoom_punch: animaciones de verdad dibujadas con HTML/Canvas (iconos, elementos, efectos).
- Kit base ampliado con iconos vectoriales (trazo animado), typewriter, countUp, highlightSweep, progressRing, burst + escena de ejemplo. Verificado con lint (0/0) y preview visual.
- Instrucciones/playbook/prompt explain_with_animation reescritos para que la IA use la galería por defecto en vez de zoom_punch al explicar; cutly_pacing distingue tramos cortos (rótulo/zoom) de tramos ≥9s (animación dibujada).

## MCP v2.5 — cámara de mundo, maqueta de navegador y escena real rehecha (2026-10-26)
- El usuario compartió un zip con sus propias animaciones de referencia (yt/*.html): cada una reimplementaba desde cero una cámara de mundo (pan/zoom/follow) y paquetes viajando en arco. Se añadió al kit como utilidad reusable: WORLD/camTo/W/wText/updateCam/arcPt + browserChrome (maqueta de navegador con URL escribiéndose). Viñeta cinematográfica CSS estática añadida al kit. Corregido sobre la marcha: el icono ICONS.euro (vectorial) no era reconocible -> glifo de texto; el texto de browserChrome incumplía el tamaño mínimo -> subido a 25px.
- Vuelta a montar la escena de condición de carrera de race.mp4 (proyecto p_d5e2c165f6394e6a) usando la galería nueva (iconBadge, countUp, highlightSweep, typewriter, burst, browserChrome): 0 errores/avisos, verificada con fotogramas reales del render de borrador.

## MCP v2.6 — refuerzo del estilo + fix de iconBadge (2026-10-26)
- El usuario confirmó que el estilo (cámara + navegador + iconos) es justo el que quiere y pidió reforzarlo como el comportamiento por defecto, no una opción más.
- Añadida una 5.ª escena de ejemplo a base_html (cámara de mundo + browserChrome + arcPt) para que se copie literalmente. Instrucciones/playbook/prompt/tool-description reescritos en términos más directivos ("SIEMPRE", "parte de base_html, no escribas desde cero", "nunca un zoom como único recurso").
- Fix real encontrado al verificar: iconBadge dibujaba la placa de fondo a opacidad plena desde `draw=0`. Corregido y vuelto a montar en la escena de race.mp4 ya en producción.

## Subtítulos pro y títulos cinéticos — 2026-10-27
- Referencia: reel de autor (subtítulo de una palabra, Inter fina, frases clave en tipografía cinética). Análisis y hoja de ruta en la conversación.
- Subtítulos: fuentes Inter (Regular/Bold/SemiBold/ExtraBold) y Montserrat (Bold/ExtraBold/Black) en `assets/fonts`; `SubtitleStyle` con `letter_spacing`, `shadow`, `shadow_color`, `shadow_blur`, animación `fade_pop` y `emphasis` (`WordEmphasis`: escala/color/fuente/negrita/mayúsculas por palabra, se reduce sola si no cabe). Render ASS (`ass.py`), vista previa del editor (`stage.js`/`subtitles.js`), inspector y preset `reel_word_clean`. Tests: `tests/test_subtitle_style.py`.
- Escenas `code` transparentes: `SceneLayer.transparent` (PNG con alfa vía `omit_background`), previews sobre damero y `composite` con alfa. Chromium ve las fuentes de la biblioteca por nombre (fontconfig generado en `data/cache/scene-fonts.conf`).
- Títulos cinéticos: `kit/kinetic.html` + `services/scene_js/kinetic.py` + `POST /projects/{id}/title` + MCP `cutly_title` (estilos title/kicker/statement/impact/ghost; entradas blur_in/rise/pop/tracking/letters/words/mask; `say` sincroniza con la voz). Tests: `tests/test_kinetic_title.py` y `test_add_title_endpoint`.
- Pendiente: desplegar (reiniciar `cutly-api`/worker), y siguientes puntos de la hoja de ruta (transiciones y cámara, capa de vídeo/B-roll, audio SFX, texto detrás de la persona).

## Efectos de cámara, sonido y autopiloto pro — 2026-10-27
- Efectos nuevos (`effects/`): `zoom_blur`, `whip_pan` (estela con `tblend` encadenado: `tmix` con `enable` corrompe la imagen, comprobado), `warm_flash`, `blur_ramp`, `tilt_roll` (+ `rotate` y `tblend` en la lista blanca de filtros).
- Capa `audio` (`schema/project.py::AudioLayer`): efectos de sonido sintetizados con numpy (`services/audio/sfx.py`: whoosh, whoosh_fast, hit, pop, click, ding, riser, glitch), mezclados tras normalizar la voz (`graph.py`, `amix normalize=0` + limitador). Catálogo `GET /sfx`, MCP `cutly_catalog sfx`, soporte mínimo en el editor (etiqueta, color, inspector).
- Autopiloto: `pro: true` alterna zoom con estela / whip pan en empalmes con `whoosh_fast`, y zooms de ritmo con estela.
- Playbook MCP: reglas 7b (cámara/cambios de plano) y 7c (sonido). No se puede escuchar el resultado desde el agente: las reglas de volumen son relativas a la voz.
- Pendiente: capa de vídeo/B-roll y plantillas split-screen, música con ducking, texto detrás de la persona (necesita segmentación, esperar al VPS nuevo).

## Directos largos → clips de 5-10 min — 2026-10-27
- Subido `directo.mp4` (99,7 min, 1080p, 2 GB). Ingesta (proxy) y transcripción por ventanas lanzadas.
- Análisis (`services/analysis/stream.py`, `api/routers/analysis.py`): `GET /media/{id}/outline` (esquema por ventanas con interés, cambios de tema, palabras clave, energía, preguntas) y `POST /media/{id}/suggest-segments` (tramos de 5-10 min con interés sostenido, límites de tema/frase, sin aire muerto; `save` los registra como candidatos). Heurístico: sin diarización ni detección de risas.
- `layout: "horizontal"` al crear proyecto (1920×1080, reframe `custom` a cuadro completo).
- MCP: `cutly_outline`, `cutly_find_segments`, prompt `stream_to_clips`, regla 14 del playbook, `layout` en `cutly_start_project`/`cutly_quick_edit`.
- Render de clips largos: los efectos se compilan solo sobre su ventana (`graph.py::_fx_windowed`, trim+concat con pre-roll de 6 fotogramas y pts regenerados por número de fotograma). Medido con 45 s del directo y 15 zooms: 86,8 s de CPU sin efectos, 139,6 s encadenados, 103,9 s ventaneados. Hallazgo: `concat` tras `trim` repite el pts en cada unión y el codificador descarta un fotograma por unión; `tblend` pierde el primer fotograma de cada etapa. Tests: `tests/test_fx_windowing.py`.
- Pendiente: probar con la transcripción real del directo; música con ducking; capa de vídeo/B-roll.
