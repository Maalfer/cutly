# Prompt de traspaso — Cutly

> Pégalo tal cual como primer mensaje a la otra IA (con acceso al servidor por SSH/terminal). No contiene credenciales:
> pídeselas al usuario (ver «Accesos»). Última actualización: 2026-10-26.

---

Eres el ingeniero principal que continúa **Cutly**, un editor de vídeo «API-first» que convierte directos largos en
clips verticales profesionales. Trabajas en español con el usuario (comentarios y documentación en español, código en
inglés). Antes de tocar nada lee, en este orden: `/home/mario/cutly/PROGRESS.md`, `docs/AGENT_GUIDE.md` y este
documento. Todo lo que afirmes debe estar verificado: si no lo has ejecutado y visto, di que no lo has verificado.

## 1. Objetivo

El usuario sube un directo (3–6 h) o un vídeo corto y lo edita a mano **o con Claude Code usando una clave API**; ambos
usan exactamente los mismos endpoints REST. El proyecto de edición es un JSON, única fuente de verdad. Caso de uso
principal: 10–20 clips de 30–90 s (algunos de varios minutos) en 9:16, con subtítulos estilo reel (karaoke por palabra),
audio normalizado, color básico, efectos, iconos y rótulos, en español. **No hay descargas de Twitch/URLs: sin yt-dlp;
los vídeos entran solo por subida.** La integración principal es **REST + clave API** (estilo SysReptor: el usuario crea
la clave en la web, «Claves API»); el servidor MCP es un extra opcional.

## 2. Accesos y secretos (NO están aquí)

- Producción: **https://editor.cogny.es**. Usuario web `mario`; la contraseña, pídesela al usuario.
- Repositorio: `/home/mario/cutly` (git, rama `main`). Identidad git local ya configurada.
- Secretos solo en `/home/mario/cutly/.env` (chmod 600; nunca en el repo, nunca en logs ni en el chat).
- La app **no usa ninguna API de IA externa**: la inteligencia (elegir clips, montar, verificar) la pone el agente que se conecta con una API key de Cutly.
- Para probar la API crea una clave desde la web (Claves API) o con
  `uv run cutly create-key nombre --write` (con `.env` cargado). Revoca las claves de prueba al terminar.

## 3. Stack (decidido; no lo cambies sin avisar y justificar)

Python 3.12/3.13, uv, ruff, pytest · FastAPI + SQLModel/SQLAlchemy 2 + SQLite WAL + **Alembic** · Pydantic v2 · cola RQ +
Redis (local) · faster-whisper (modelo `small` en CPU, tras la interfaz `Transcriber`) · FFmpeg/ffprobe (libass para ASS), resvg
para SVG, Pillow para secuencias de iconos y contact sheets · frontend Preact + htm **vendorizados** (sin CDN, sin npm,
sin build) servido por la propia API · Nginx existente del VPS + certbot (HTTP-01) · systemd.

## 4. Restricciones del servidor (CRÍTICAS)

El VPS de producción es **compartido con otros servicios** (correo, bases de datos, otros sitios Nginx): **2 CPU,
1,8 GB de RAM, sin GPU, swap de 4 GB casi llena**. El usuario migrará más
adelante a un VPS potente. Por tanto:

- Nunca ejecutes ffmpeg/whisper pesados fuera de un límite de memoria. Para pruebas manuales:
  `sudo systemd-run --pipe --wait --quiet --uid=mario --gid=mario -p MemoryMax=900M -p MemorySwapMax=0 -p Nice=12
  -p WorkingDirectory=/home/mario/cutly --setenv=PATH=$PATH <comando>` (ojo: `systemd-run` arranca en `/`).
- Servicios: `cutly-api` (uvicorn 127.0.0.1:8321, MemoryMax 450 MB) y `cutly-worker` (RQ, Nice 12, CPUQuota 150 %,
  MemoryMax 900 MB; Whisper `small` llega a ~730 MB, el render final a ~730 MB). Unidades en `deploy/`. Redis local
  (64 MB, solo localhost). Nginx: `deploy/nginx-editor.cogny.es.conf`.
- Un render grande sin límite provocó un OOM global (solo cayó mi ffmpeg). Sigue activa la regla: **un render a la vez**.
- `/tmp` es un tmpfs en RAM (921 MB) y se llena; `/tmp/opencode` es un enlace a `~/.cache/tmp-moved/`. **No borres
  nada de `/tmp` ni de otros proyectos sin permiso del usuario.** Usa `~/.cache/<algo>` para temporales y bórralos.
- Si el tool de shell devuelve «disk full» sin salida: redirige la salida a un fichero en `/home` y léelo con Read.
- No instales paquetes del sistema sin avisar (ya hay `ffmpeg`, `redis-server`; `uv` está en `~/.local/bin`).
- Despliegue: `git commit` → `sudo systemctl restart cutly-api cutly-worker` (no reinicies el worker con un job en
  curso: lo mata). Las migraciones se aplican solas al arrancar (`init_db`). Backup de la BD antes de migrar:
  `cp data/cutly.db ~/.cache/backups/…`.

## 5. Estructura del repositorio

```
src/cutly/
  config.py                 ajustes por entorno (prefijo CUTLY_)
  auth.py, cli.py           argon2, claves API (sha256), create-user/create-key/set-password
  db/                       modelos SQLModel, sesión (WAL), migrations/ (Alembic: 0001 baseline, 0002 version/candidate_id)
  schema/project.py         ProjectDoc (Pydantic estricto): timeline, layers (text/icon/image/shape/subtitle/effect), reframe, audio, color
  schema/ops.py             operaciones atómicas por lote + merge-patch; schema/versioning.py (migraciones del JSON)
  services/ingest/          ffprobe, alta/baja de medios
  services/transcribe/      interfaz Transcriber, faster-whisper por ventanas en silencios, cleanup (edición de palabras)
  services/candidates/      candidatos a clip (ajuste a frases y deduplicado; los elige el agente)
  services/projects/        store (historial/undo/redo/versión), check (avisos), hooks (valida efectos/assets/fuentes)
  services/render/          graph.py (filtergraph), ass.py (subtítulos/texto/formas), animation.py (curvas), sprite.py
                            (secuencias PNG de iconos animados), effects_api.py, fonts.py, rasterize.py (SVG→PNG)
  services/sanitize/        paths y svg (lista blanca)
  registry/effects.py       registro de efectos (código + declarativos por API)
  worker/                   jobs, runner de subprocesos (timeout/progreso/cancelación), handlers (proxy, peaks, transcribe,
                            candidates, render)
  api/routers/              auth, uploads, media, transcripts, candidates, projects, render, effects, jobs, guide
effects/<nombre>/           effect.json + build.py + preview.js (12 efectos incluidos; `_template` pendiente)
assets/icons, assets/fonts  5 iconos propios CC0 (+ LICENSES.md de las 5 fuentes OFL)
web/                        index.html, api.js, upload.js, store.js, components/, canvas/, tools/upload.py, vendor/
docs/AGENT_GUIDE.md         guía para agentes (se sirve en /api/v1/agent-guide con la URL real)
tests/ (+ tests/js)         ~120 tests, incluye Node para la lógica de subida del navegador
scripts/apps_linux/         ejemplo completo de edición profesional vía API (build.py, render.py)
```

## 6. Estado (qué está hecho)

Todo desplegado en producción y probado contra https://editor.cogny.es (≈165 tests: `uv run pytest`):

- Auth (sesión web + claves API con permisos), subida por trozos reanudable (web con XHR/progreso real y script `web/tools/upload.py`),
  proxy (lado corto 540 px) y forma de onda.
- Transcripción (`vocabulary`, `beam_size`, corrección palabra a palabra conservando tiempos), candidatos a clip elegidos por el agente.
- Proyecto de edición: ops atómicas por lote, undo/redo, versión optimista, transiciones entre clips (xfade/acrossfade).
- Render: reencuadre center/facecam/game/stack/custom, varios clips, velocidad, subtítulos ASS con palabra activa, texto, formas,
  iconos/imágenes animados, **motor de animación único** (enter/exit simétricos, loops, keyframes con easing), color, audio
  normalizado **en dos pasadas (verificado midiendo el MP4)**, borrador/final y render por tramos (`start`/`end`).
- **Efectos**: registro con autodescubrimiento (12 incluidos, `region`, efectos declarativos por API con lista blanca y prueba real
  con FFmpeg). Doc y plantilla: `docs/ADDING_EFFECTS.md`, `effects/_template/`.
- **Assets**: 45 iconos propios CC0 (`scripts/gen_icons.py`), 5 fuentes OFL, API de listar/buscar/subir/borrar con saneado, vistas
  previas y hoja de contacto (`GET /assets-sheet.png`). **Presets**: 50 incluidos + propios, aplicables como operación.
- **Verificación para agentes**: `frame`, `filmstrip`, `frames`, original con rejilla, `audio-stats`, `transcript` en reloj del clip y
  `checks` (caras tapadas con OpenCV, fuera de pantalla, zonas de la app, solapes, tamaño, cortes a mitad de palabra/frase, audio,
  efectos). Medición de texto con la **fuente real** y el criterio de libass (Fontsize = ascendente+descendente).
- Interfaz web responsive (login, biblioteca, subida, ficha con reproductor/forma de onda/transcripción, Claves API). **Sin pantalla
  de proyectos todavía**: los renders se bajan por `GET /renders/{job}/download` estando logueado.
- Tests de imagen de referencia (`tests/golden/`, SSIM ≥ 0,93; `UPDATE_GOLDEN=1` regenera: mira las imágenes antes de fijarlas).

## 7. Pendiente (en este orden de prioridad)

1. **Frontend de proyectos** (fases 2–3 del plan original): lista de proyectos y candidatos, revisión con preview, editor de capas y
   subtítulos, línea de tiempo con Canvas y forma de onda, miniaturas, uso de `/effects/{n}/preview.js`, botón de render, visor de
   fotogramas/checks. La API ya lo permite todo.
2. **Servidor MCP** (opcional; envoltorio fino de la REST): list_effects, describe_effect, add_layer, update_layer, remove_layer,
   list_assets, search_assets, upload_asset, create_preset, apply_preset.
3. (hecho) Los candidatos ya no usan IA externa: los registra el agente con `POST /media/{id}/candidates`.
4. Limpieza automática de originales/proxies/renders antiguos (los fotogramas ya se podan a las 24 h); validar `docker-compose.yml` y
   el Nginx del Compose (nunca probados: aquí no hay Docker).
5. Efectos que FFmpeg no pueda hacer: renderer Chromium/Playwright (`render_backend: "browser"`, reservado; no viable en este VPS).
6. Mejoras de calidad candidatas: keyframes en la UI, más presets de subtítulos con fuentes subidas, `slice` exacto dentro de
   transiciones, detección de caras más robusta (YuNet) para planos de perfil, previews de efectos verificados contra el render.

## 8. Lecciones aprendidas (no repitas estos errores)

- `loudnorm` dentro del grafo costaba +340 MB: se normaliza en **dos pasadas** (análisis `ebur128` solo audio + `volume` +
  `alimiter`). Pico de render 1080×1920 ≈ 410–730 MB. Usa `-threads 2 -filter_threads 1` y x264 con `rc-lookahead=8`.
- **`exp()` desbordaba fuera de la ventana de un efecto y `0*inf = NaN` oscurecía TODO el vídeo** (solo con destellos lejanos
  del inicio). Toda envolvente debe acotar sus argumentos y valer 0 fuera de su ventana (hay tests con ventana a los 88 s).
  Prueba siempre con **vídeo real y efectos a mitad/final del clip**, no solo con sintéticos al inicio.
- No todos los filtros de FFmpeg admiten expresiones con `t` (p. ej. `colorbalance` no). Los efectos declarativos se prueban
  con FFmpeg al crearlos. Sí funcionan: `scale ... eval=frame` + `crop` (zoom), `eq ... eval=frame`, `drawbox` con `w/h` por
  expresión, `crop` con `x/y` por expresión, `rgbashift`/`vignette`/`noise`/`gblur`/`negate` con `enable`.
- `-ss` previo por cada clip de la línea de tiempo (no decodifica el directo entero). `concat` con varias entradas acumula
  fotogramas en memoria: vigila clips largos.
- libass: tags `\1a/\3a/\4a` por componente (no `\alpha`, que pisa la transparencia del fondo); texto no confiable pasa
  por `ass_escape`; los rótulos con fondo usan `BorderStyle 3`. Giros positivos = **sentido horario** en toda la tubería.
  La fuente Anton no tiene « ». Familias de fuente reales: `Poppins`, `Poppins ExtraBold` (con `bold:false`), `Anton`,
  `Bebas Neue`, `Bangers`; la validación lista las disponibles.
- Sin `relationship()` en SQLModel, borrar hijos → `flush()` → borrar padre (hubo un 500 por FK). Los tests no deben leer
  el `.env` de producción (ya aislado). Columnas NOT NULL nuevas necesitan `server_default` en la migración. Al generar
  migraciones fija **siempre** `CUTLY_DATABASE_URL` a una BD temporal.
- Subida: los trozos de 32 MB en conexiones inestables se cortaban; ahora 4 MB (web) / 8 MB (script), XHR con progreso real,
  vigilancia de bloqueo y reintentos. El límite de peticiones por IP excluye `/uploads/*/chunks/*`.
- Nginx: `proxy_request_buffering off`, `client_max_body_size 64M`. Cloudflare en modo **solo DNS** (nube gris). La CSP se
  construye con el hash del import map de `web/index.html`; si cambias ese script inline, reinicia la API.
- No llames a tu script `bisect.py` (ni a ningún módulo estándar).
- **Reemplazos de texto sobre código ya formateado por ruff**: si el `str.replace` no encaja, no falla (devuelve lo mismo). Usa la
  herramienta de edición exacta o `assert old in s` y **comprueba con grep que se aplicó**. Así se perdió la pasada de volumen del
  render y ningún render normalizó el audio durante un tiempo (ya corregido y con test que mide el LUFS del MP4).
- `ruff --fix` borra imports «sin uso» que aún no has usado en ese momento: añade el import junto con el uso, en el mismo cambio.
- OpenCV: `opencv-python-headless>=4.10,<5` (la 5.0 ya no trae `CascadeClassifier`).
- `sleep` largo está bloqueado en el shell de la herramienta: usa `until <condición>; do sleep 2; done`.
- Las estimaciones de composición deben usar la fuente real (Pillow) y el criterio de libass; con factores fijos hubo falsos positivos.
- Proxies antiguos 304×540 siguen en disco: regenerar con `POST /media/{id}/proxy` para frames/previews nítidos en vertical.

## 9. Cómo trabajar

1. Cambios pequeños, un commit por hito, mensaje claro y trailer
   `Co-Authored-By: <tu modelo> <noreply@anthropic.com>`. Mantén `PROGRESS.md` (hecho/pendiente/decisiones) y
   `docs/AGENT_GUIDE.md` al día: es lo que lee el agente que edita.
2. Antes de dar algo por hecho: `uv run ruff format src tests effects && uv run ruff check src effects tests && uv run pytest -q`
   (en segundo plano con `nice -n 15` y salida a fichero; la suite tarda ~2 min). Tests nuevos con cada cambio.
3. Para cualquier cambio visual: renderiza, **extrae fotogramas con ffmpeg y míralos** (Read sobre el PNG; contact sheets
   con `hstack/vstack`). Mide con `signalstats` si sospechas de brillo/color. Revisa `result.warnings` del render.
4. Despliega y comprueba **contra https://editor.cogny.es** con una clave real; limpia lo que crees (medios, proyectos,
   claves de prueba). Informa de lo no validado (p. ej. la interfaz web no se ha visto en un navegador real).
5. Pregunta al usuario solo lo que sea suyo decidir (credenciales, dinero, infraestructura). Recomienda, no enumeres.

## 10. Edición de «apps linux.mp4» (hecha; pendiente de validación del usuario)

- Medio `m_ad7487db158d4304` (94 s, ya 9:16 1080×1920, tutorial de apt/flatpak en Linux; cara hasta ≈40 % de la altura, terminal debajo con
  la línea de comandos en y≈0.55, y≈0.66 para `flatpak install`). Transcripción repetida con `vocabulary` técnico y `beam_size` 5 y
  corregida palabra a palabra por API (`flatpak`, `desinstalación`, el cierre «te mando la guía al privado»).
- Proyecto `p_5a8feaabc2d141b9` (versión 4): subtítulos Poppins con palabra activa amarilla bajo la cara (y=0.425), título Anton,
  rótulos de concepto arriba a la derecha, cuadros pulsantes sobre cada comando, 7 `zoom_punch` solo sobre la cara (región y 0–0.40),
  3 destellos, glitch en «ciberseguridad», barra de progreso, color +6 % saturación y CTA final (COMENTA LINUX en y=0.56, «GUÍA AL
  PRIVADO» en y=0.705, flecha hacia abajo en y=0.78: todo por encima de la franja que tapa la app). Reproducible con
  `scripts/apps_linux/build.py` y `render.py` (`CUTLY_URL`, `CUTLY_API_KEY`).
- Verificado con la propia API: `checks` sin errores ni avisos (solo `loudness` y `tight_cut` informativos), tira de miniaturas, y render
  final 1080×1920 **−14,4 LUFS, pico −1,9 dBFS** (medido sobre el MP4). Render descargable: `GET /renders/j_e97eb1b0b9ac4312/download`
  (logueado). Los renders antiguos del proyecto se borraron a mano (no hay limpieza automática todavía).

## 11. Primer paso recomendado

Lee `PROGRESS.md`, ejecuta la suite en segundo plano, comprueba `systemctl is-active cutly-api cutly-worker`
y `free -m`, y pregunta al usuario cuál de los puntos de la sección 7 quiere primero (mi recomendación: el 1, la
verificación, porque es lo que permite a Claude Code editar sin ir a ciegas). No empieces a construir sin esa confirmación.
