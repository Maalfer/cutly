# 🎬 cutly — Metodología completa para crear contenido de ciberseguridad en vídeo

> Repositorio de **metodología** (no de vídeos). Aquí vive todo el conocimiento para que
> cualquier persona —o cualquier **agente de IA**— pueda retomar el trabajo y producir
> vídeos de hacking ético / ciberseguridad en español para YouTube (canal
> **elrincondelhacker** / "El Pingüino de Mario"), de principio a fin.

El objetivo final siempre es el mismo: **sacar clips cortos y pulidos** (formato largo para
YouTube y formato **Short** vertical) a partir de demostraciones técnicas, con gancho y
limpios de relleno.

---

## 🧭 Las dos mitades del proceso

El flujo tiene dos fases independientes, cada una con su carpeta y su metodología propia:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FASE 1 — GENERAR / GRABAR          │  FASE 2 — EDITAR                         │
│  (carpeta  crear-shorts/)           │  (carpeta  editor/)                      │
│                                     │                                          │
│  La IA controla el Mac al 100%      │  La IA transcribe, analiza y recorta     │
│  (cursor, teclado, ventanas, apps)  │  la grabación en bruto hasta dejar       │
│  y ejecuta una demo cinematográfica │  clips limpios: formato largo (16:9)     │
│  mientras el usuario graba con OBS. │  o SHORT vertical (9:16) con hueco        │
│                                     │  arriba para la cara del usuario.        │
│  →  produce el .mkv/.mp4 en bruto   │  →  produce el clip final para subir     │
└─────────────────────────────────────────────────────────────────────────────┘
         crear-shorts/  ───────────── el .mkv crudo ──────────▶  editor/crudo/
```

El puente entre ambas fases es un archivo de vídeo en bruto: lo que la Fase 1 graba con OBS
se deja en `editor/crudo/` para que la Fase 2 lo convierta en clip.

> **Nota:** las dos fases se pueden usar por separado. Un directo de Twitch grabado "a mano"
> (sin que la IA controle nada) entra directamente en la Fase 2. Y la Fase 1 sirve para
> generar cualquier demo controlada, se edite luego como se edite.

---

## 📂 Estructura del repositorio

```
cutly/
├── README.md                         ← ESTE archivo (empieza aquí)
│
├── crear-shorts/                     ← FASE 1: la IA controla el Mac y graba la demo
│   ├── README.md                     ←   índice + estado de la máquina + permiso maestro
│   ├── METODOLOGIA/
│   │   ├── 01-control-total-mac.md   ←   permiso de Accesibilidad + teoría del control
│   │   ├── 02-kit-herramientas.md    ←   OCR, cursor, cliclick, find_button (con código)
│   │   ├── 03-gestion-ventanas.md    ←   z-order, apps fullscreen, direccionar por ID
│   │   └── 04-flujo-toma-video.md    ←   protocolo de toma: fases, pacing, verificación
│   ├── DEMO-CLICKFIX/                ←   ejemplo real completo (demo ClickFix de exfiltración)
│   │   ├── 05-demo-completa.md
│   │   ├── 06-reproducir-paso-a-paso.md
│   │   └── 07-limpieza-restore.md
│   └── herramientas/                 ←   código fuente de las herramientas
│       ├── ocr.swift                 ←   OCR con Vision de macOS (texto + coordenadas)
│       ├── mousepos.swift            ←   posición real del cursor
│       └── find_button.py            ←   localizar botones por color
│
└── editor/                           ← FASE 2: editar la grabación en clips
    ├── CLAUDE.md                     ←   METODOLOGÍA PRINCIPAL de edición (directo → clips 16:9)
    ├── METODOLOGIA-SHORTS.md         ←   metodología de SHORTS verticales 9:16 (cara arriba)
    ├── scripts/
    │   ├── asegurar_mejor_modelo.sh  ←   descarga/elige el mejor modelo Whisper disponible
    │   ├── construir_clip.sh         ←   construye un clip 16:9 (trim+concat+micro-fade)
    │   ├── construir_short.py        ←   construye un SHORT 9:16 (recorte+paneo+banda cara)
    │   ├── detectar_silencio.sh      ←   detección de silencios para afinar cortes
    │   └── verificar_corte.sh        ←   transcribe un tramo para verificar una unión
    ├── crudo/                        ←   vídeos fuente en bruto + sus transcripciones
    │                                     (los .mkv/.mp4 NO están en git, ver abajo)
    └── videos-editados/              ←   salida de clips + _cortes.log (registro de cortes)
```

### ⚠️ Qué NO está en el repositorio

Este repo guarda **metodología**, no material pesado. El `.gitignore` excluye:

- **Vídeos** (`*.mp4`, `*.mkv`, `*.mov`, `*.webm`) — fuentes en bruto y clips finales.
- Audio intermedio (`*.wav`) y `.DS_Store`.

Sí se versiona todo lo demás: documentación, scripts, transcripciones de ejemplo
(`*_transcripcion.*`) y el registro de cortes (`_cortes.log`), porque son el valor real.

---

## 🚀 Si eres un agente de IA que retoma este trabajo — lee en este orden

1. **Este README** (visión global).
2. ¿Vas a **grabar/generar** una demo nueva controlando el Mac?
   → `crear-shorts/README.md` y luego `crear-shorts/METODOLOGIA/01…04`.
3. ¿Vas a **editar** una grabación en clips?
   → `editor/CLAUDE.md` (clips 16:9 desde un directo) **y**
   `editor/METODOLOGIA-SHORTS.md` (shorts verticales 9:16 con hueco para la cara).
4. Mira siempre `editor/videos-editados/_cortes.log` antes de tocar un clip ya hecho:
   contiene los tramos exactos (en segundos) de cada clip construido.

### Reglas de oro heredadas (válidas en todo el repo)

- **Precisión por encima de coste.** Mejor gastar más comprobaciones (o ir más lento en el
  pacing del montaje) que dejar un corte mal hecho. Detalle en `editor/CLAUDE.md`.
- **Verifica, no asumas.** Tras cada acción (un clic en la Fase 1, un corte en la Fase 2),
  compruébala: con OCR/screenshot en la grabación, extrayendo fotogramas en la edición.
- **Nunca toques `_cortes.log` a ciegas.** Si aparece ausente o truncado, es un problema
  transitorio (mira la Papelera) — nunca lo recrees desde cero; añade al final (APPEND).

---

## 🛠️ Herramientas base (ya instaladas en la máquina de trabajo)

- **ffmpeg / ffprobe** (Homebrew) — todo el corte, recodificación y análisis.
- **whisper.cpp** (Homebrew) + modelos en `~/.whisper-models/` — transcripción con timestamps.
- **cliclick** (Homebrew), **OCR propio** y `mousepos` (Swift + Vision) — control del Mac.
- **yt-dlp** — descargar directos si se parte de una URL.

Máquina de referencia: **Apple Silicon (Metal)**, macOS, pantalla 1280×832 lógico (Retina 2×),
menús en español.
