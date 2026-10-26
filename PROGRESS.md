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
- [x] 4. Candidatos (Anthropic): bloques de 25 min con solape, salida estructurada, ajuste a frases, deduplicado, API; claves API en la web + guía para agentes + script de subida. 31 tests
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
- Modelo por defecto `claude-opus-5-5` (effort `high`, pensamiento adaptativo, sin `temperature`/`tool_choice`/prefill). Si el clasificador de seguridad rechaza un bloque se reintenta con `CUTLY_CANDIDATES_FALLBACK_MODEL` (`claude-opus-4-8`); si también rechaza, el bloque se omite y se cuenta en `refusals`.
- El modelo devuelve ids de segmento (no segundos); el servidor calcula tiempos y ajusta a frases con los tiempos por palabra.
- Coste orientativo: un directo de 5 h son ~100k tokens de entrada en total → del orden de 1 USD con Opus 5.5.
- **Sin validar contra la API real**: falta `ANTHROPIC_API_KEY` en `/home/mario/cutly/.env` (el endpoint responde 503 con el motivo). Probado con cliente simulado (forma de la petición, rechazo, fallback).
- Los tests ya no leen `.env` (antes recogían el de producción).
- **Pendiente importante**: Alembic. `create_all` no añade columnas a tablas existentes; antes de cambiar el modelo en producción hay que introducir migraciones.

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
