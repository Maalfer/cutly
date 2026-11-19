# 🎬 cutly — Metodología completa para crear contenido de ciberseguridad en vídeo

> Repositorio de **metodología** (no de vídeos). Aquí vive todo el conocimiento para que
> cualquier persona —o cualquier **agente de IA**— pueda retomar el trabajo y producir
> vídeos de hacking ético / ciberseguridad en español para YouTube (canal
> **elrincondelhacker** / "El Pingüino de Mario"), de principio a fin.

El objetivo final siempre es el mismo: **sacar clips cortos y pulidos** (formato largo para
YouTube y formato **Short** vertical) a partir de demostraciones técnicas, con gancho y
limpios de relleno.

> **Todo en una VM, desde cualquier anfitrión:** las demos se ejecutan **dentro de una VM de VirtualBox**
> (nunca en el ordenador real). El anfitrión puede ser **Windows, macOS o Linux**: solo cambia cómo se instalan
> las herramientas (VirtualBox, ssh, Tesseract, ffmpeg) — ver **[`PORTABILIDAD.md`](PORTABILIDAD.md)**, que incluye
> la sección de **anfitrión Windows** (rutas, `VBoxManage`, Tesseract). Reglas para agentes: [`CLAUDE.md`](CLAUDE.md).

---

## 🧭 Las dos mitades del proceso

El flujo tiene dos fases independientes, cada una con su carpeta y su metodología propia. Arquitectura
completa (contratos de datos, propuesta de pipeline con agentes especializados): [`crear-shorts/ARQUITECTURA.md`](crear-shorts/ARQUITECTURA.md).

```
┌──────────────────────────────────────┬──────────────────────────────────────┐
│  FASE 1 — GENERAR / GRABAR            │  FASE 2 — EDITAR                      │
│  (carpeta  crear-shorts/)             │  (carpeta  editor/)                   │
│                                        │                                        │
│  La IA controla la VM al 100%         │  Construye el clip final: formato     │
│  (cursor, teclado, ventanas, apps) y  │  largo 16:9 (de un directo) o SHORT    │
│  ejecuta una demo cinematográfica.    │  vertical 9:16 con hueco para la cara │
│  VirtualBox graba en el anfitrión     │  (automático si la toma viene de      │
│  (sin OBS, sin que el usuario toque   │  Fase 1: short_desde_toma.py).        │
│  nada). → .mp4 + registro de pasos    │  → produce el clip final para subir   │
└──────────────────────────────────────┴──────────────────────────────────────┘
      crear-shorts/  ── .mp4 + .steps.jsonl + .mapa.md ──▶  editor/crudo/
```

El puente entre ambas fases es el `.mp4` de la toma **más su registro** (`.steps.jsonl`, `.mapa.md`):
la Fase 1 los deja en `editor/crudo/` y la Fase 2 los usa para construir el clip sin tener que mirar
el vídeo entero a ciegas.

> **Nota:** las dos fases se pueden usar por separado. Un directo de Twitch grabado "a mano" (sin que
> la IA controle nada, sin registro de pasos) entra directamente en la Fase 2 por el camino MANUAL
> (`editor/CLAUDE.md`, `editor/METODOLOGIA-SHORTS.md`). Y la Fase 1 sirve para generar cualquier demo
> controlada, se edite luego como se edite.

---

## 📂 Estructura del repositorio

```
cutly/
├── README.md                         ← ESTE archivo (empieza aquí)
├── PORTABILIDAD.md                   ← cómo usar todo en macOS / Windows / Linux
├── CLAUDE.md                         ← reglas para agentes (todo en la VM, límites no negociables)
├── PENDIENTE.md                      ← estado y pendiente ACTUAL (corto a propósito)
│
├── crear-shorts/                     ← FASE 1: la IA controla la VM y graba la demo
│   ├── README.md                     ←   índice de esta fase
│   ├── ARQUITECTURA.md               ←   QUÉ es el sistema (contratos de datos) + propuesta multiagente
│   ├── historial/HISTORIAL-SESIONES.md ← archivo largo, sesión a sesión (no hace falta leerlo entero)
│   ├── METODOLOGIA/
│   │   ├── 00-empezar-aqui-vm.md     ←   PUNTO DE ENTRADA: montaje, toma, verificación, referencia
│   │   ├── 04-flujo-toma-video.md · 05-controlar-aplicaciones.md · 06-navegador-y-herramientas-gui.md
│   │   ├── 07-auditoria-de-pruebas.md · 08-maquina-virtual.md
│   │   ├── 09-conducir-apps-kali.md  ←   fallos medidos + fichas por app (Firefox, Burp, terminal, nmap, Docker)
│   │   └── 10-plantilla-demo-terminal.md ← CHECKLIST para una demo de terminal "perfecta a la primera"
│   ├── DEMO-IDOR/                    ←   demo de referencia (GUI): navegador + Burp contra lab_idor.py
│   ├── DEMO-SSHOLE/                  ←   demo de referencia (terminal): nmap + bypass SSH + reverse shell
│   └── herramientas/
│       ├── vm_control.py             ←   LA herramienta (Win/macOS/Linux): ver, actuar, verificar, grabar, registrar
│       ├── tipear.py · mover.py      ←   planes de tecleo y ratón humanos (lógica pura)
│       └── ocr_buscar.py · ocr.swift ←   localizar texto por OCR (ocr.swift: Vision, opcional en macOS)
│
└── editor/                           ← FASE 2: editar la grabación en clips
    ├── CLAUDE.md                     ←   edición de un DIRECTO SIN registro → clips 16:9 (camino manual)
    ├── METODOLOGIA-SHORTS.md         ←   Shorts 9:16 a mano (camino manual, sin registro de pasos)
    ├── SHORT-IDEAL.md                ←   CÓMO DEBE QUEDAR el Short final (referencia aprobada + especificación medible)
    ├── glosario.json                 ←   correcciones de términos técnicos para los subtítulos
    ├── fuentes/Inter.ttf             ←   letra de los subtítulos (licencia OFL)
    ├── METODOLOGIA-FUSION-CARA.md    ←   juntar el Short de pantalla con el vídeo de la cara+voz del usuario
    ├── BENCHMARK-WHISPER.md          ←   qué modelo de transcripción usar y por qué (medido)
    ├── scripts/
    │   ├── short_desde_toma.py       ←   Short AUTOMÁTICO desde una toma de Fase 1 (el camino normal)
    │   ├── transcribir.py            ←   transcripción (faster-whisper: large-v3-turbo + VAD, timestamps por palabra)
    │   ├── subtitular.py             ←   subtítulos karaoke quemados (estilo del ideal del usuario)
    │   ├── verificar_short.py        ←   comprueba un Short final contra la especificación del ideal
    │   ├── analizar_fusion.py        ←   mide cara/pantalla/voz y avisa de tomas repetidas antes de la fusión
    │   ├── fusionar_cara_pantalla.py ←   mete cara+voz en la banda del Short y sincroniza pantalla con la narración
    │   ├── asegurar_mejor_modelo.sh  ←   descarga el modelo Whisper recomendado (whisper.cpp)
    │   ├── construir_clip.sh         ←   construye un clip 16:9 a mano (trim+concat+micro-fade)
    │   ├── construir_short.py        ←   construye un SHORT 9:16 a mano (recorte+paneo+banda cara)
    │   ├── detectar_silencio.sh      ←   detección de silencios para afinar cortes
    │   └── verificar_corte.sh        ←   transcribe un tramo para verificar una unión
    ├── crudo/                        ←   vídeos fuente + transcripciones + `.steps.jsonl`/`.mapa.md` de Fase 1
    │                                     (los .mkv/.mp4 NO están en git, ver abajo)
    ├── plantillas/                   ←   plantillas genéricas (p. ej. fusion_plan.ejemplo.json)
    └── videos-editados/              ←   salida de clips + _cortes.log (LOCAL, no se versiona)
```
**¿Camino automático o manual en la Fase 2?** Si el vídeo viene de `crear-shorts/` (tiene
`.steps.jsonl`), usa `short_desde_toma.py` — no sigas `editor/CLAUDE.md`/`METODOLOGIA-SHORTS.md`,
que son para un directo real sin ese registro. Ver el árbol de decisión al principio de `editor/CLAUDE.md`.

### ⚠️ Qué NO está en el repositorio

Este repo guarda **metodología impersonal**: documentación, scripts, plantillas, glosario y la fuente de los
subtítulos. **Nada de un vídeo concreto se versiona.** El `.gitignore` excluye:

- **Las carpetas de trabajo enteras** `editor/crudo/` y `editor/videos-editados/` (solo se versiona su `.gitkeep`):
  fuentes, clips, transcripciones, planes de fusión, subtítulos `.subtitulos.json`, registros de toma
  (`.steps.jsonl`, `.mapa.md`) y el registro de cortes `_cortes.log`. Viven solo en tu disco.
- Esos mismos tipos de archivo estén donde estén, más vídeo, audio y modelos Whisper (`*.bin`).

Si un caso real enseña algo, se documenta **la lección** (medidas, reglas, errores) en la metodología, no los
archivos del vídeo. Las plantillas genéricas van en `editor/plantillas/`.

---

## 🚀 Si eres un agente de IA que retoma este trabajo — lee en este orden

1. **Este README** (visión global) y **`PENDIENTE.md`** (qué está pendiente de verdad, ahora mismo).
   El objetivo de todo es **`editor/SHORT-IDEAL.md`**: cómo debe quedar el Short final.
2. **`CLAUDE.md`** y **`PORTABILIDAD.md`** (reglas no negociables + instalación en tu anfitrión).
3. **`crear-shorts/ARQUITECTURA.md`** — qué es el sistema, cómo encajan sus piezas.
4. ¿Vas a **grabar/generar** una demo nueva?
   → `crear-shorts/METODOLOGIA/00-empezar-aqui-vm.md`, y si es de terminal (nmap/ssh/exploits)
   **`METODOLOGIA/10-plantilla-demo-terminal.md`** (checklist para que salga bien a la primera).
   Copia `DEMO-SSHOLE/demo_sshole.py` o `DEMO-IDOR/demo_idor.py` como esqueleto de código.
   La toma deja `editor/crudo/<toma>.mp4` + `.steps.jsonl` + `.mapa.md` para la Fase 2.
5. ¿Vas a **convertir esa toma en Short**? → `editor/scripts/short_desde_toma.py <toma> --titulo ...`
   (automático). ¿Es un directo real sin registro de pasos? → `editor/CLAUDE.md` (16:9) y
   `editor/METODOLOGIA-SHORTS.md` (9:16), a mano.
   ¿Te pasan el Short de pantalla + un vídeo con la cara y la voz del usuario para juntarlos? →
   `editor/METODOLOGIA-FUSION-CARA.md`.
6. Mira siempre `editor/videos-editados/_cortes.log` antes de tocar un clip ya hecho:
   contiene los tramos exactos (en segundos) de cada clip construido.

### Reglas de oro heredadas (válidas en todo el repo)

- **Precisión por encima de coste.** Mejor gastar más comprobaciones que dejar un corte mal hecho.
  Detalle en `editor/CLAUDE.md`. (Precisión no es lentitud: el Short final va lo más al grano posible,
  `editor/SHORT-IDEAL.md`.)
- **Verifica, no asumas.** Tras cada acción (un clic en la Fase 1, un corte en la Fase 2),
  compruébala: con OCR/screenshot en la grabación, extrayendo fotogramas en la edición.
- **Nunca toques `_cortes.log` a ciegas.** Si aparece ausente o truncado, es un problema
  transitorio (mira la Papelera) — nunca lo recrees desde cero; añade al final (APPEND).

---

## 🛠️ Herramientas base

Comunes a los tres sistemas (instalación por SO en [`PORTABILIDAD.md`](PORTABILIDAD.md)):

- **ffmpeg / ffprobe** — todo el corte, recodificación y análisis (Fase 2).
- **Whisper** (whisper.cpp o faster-whisper), modelo **`large-v3-turbo`** — transcripción con timestamps (Fase 2).
  Elegido midiendo, no por tamaño: `editor/BENCHMARK-WHISPER.md`.
- **yt-dlp** — descargar directos si se parte de una URL (Fase 2).
- **VirtualBox + ssh + `vm_control.py`** (Fase 1) — control de la VM, igual en los tres SO; OCR con Tesseract
  (en macOS puede usarse Vision).

Desarrollo: la metodología se midió primero en un Mac con Apple Silicon (invitado ARM64) y se portó a un anfitrión
Windows 11 (invitado x86-64). Los resultados medidos de cada plataforma están en `crear-shorts/METODOLOGIA/08` y `PENDIENTE.md`.
