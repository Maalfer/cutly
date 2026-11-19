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
> (`editor/directos/CLAUDE.md`, `editor/shorts/METODOLOGIA-SHORTS.md`). Y la Fase 1 sirve para generar cualquier demo
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
├── nucleo/                           ← LIBRERÍA COMÚN (Python, sin CLI): la usan las dos fases
│   ├── rutas.py · ffmpeg.py · medios.py  ←   dónde está cada cosa, ffmpeg en cualquier SO, leer vídeo/audio
│   ├── audio.py · series.py          ←   energía a 10 ms, máscara de voz, LUFS; tramos de una máscara
│   ├── formato.py                    ←   el lienzo del Short (1080x1920@60, banda de la cara 648)
│   ├── toma.py                       ←   CONTRATO Fase 1 → Fase 2 (.steps.jsonl / .mapa.md)
│   ├── transcripcion.py · subtitulos.py  ← Whisper medido; texto y tiempos de los subtítulos
│   └── cortes.py                     ←   _cortes.log (solo APPEND)
├── pruebas/                          ← python -m unittest discover -s pruebas -t pruebas
├── estudio/                          ← INTERFAZ DE ESCRITORIO (PySide6): Claude Code dentro + pestañas VM/Shorts/Subtítulos
│                                         (python -m estudio; ver estudio/ESTUDIO.md)
├── .claude/skills/                   ← los flujos de trabajo como skills (/preparar-vm, /fusionar-cara-pantalla…)
│                                         = los botones de la interfaz
│
├── crear-shorts/                     ← FASE 1: la IA controla la VM y graba la demo
│   ├── README.md · ARQUITECTURA.md   ←   índice de esta fase · QUÉ es el sistema + propuesta multiagente
│   ├── historial/HISTORIAL-SESIONES.md ← archivo largo, sesión a sesión (rutas de entonces; no hace falta leerlo)
│   ├── METODOLOGIA/
│   │   ├── 00-empezar-aqui-vm.md     ←   PUNTO DE ENTRADA: montaje, toma, verificación, referencia
│   │   ├── 04-flujo-toma-video.md · 05-controlar-aplicaciones.md · 06-navegador-y-herramientas-gui.md
│   │   ├── 07-auditoria-de-pruebas.md · 08-maquina-virtual.md
│   │   ├── 09-conducir-apps-kali.md  ←   fallos medidos + fichas por app (Firefox, Burp, terminal, nmap, Docker)
│   │   └── 10-plantilla-demo-terminal.md ← CHECKLIST para una demo de terminal "perfecta a la primera"
│   ├── DEMO-IDOR/ · DEMO-SSHOLE/     ←   demos de referencia (GUI con Burp · terminal con nmap + reverse shell)
│   └── herramientas/
│       ├── vm_control.py             ←   CLI + API (`import vm_control as v`): fachada del paquete vm/
│       ├── vm/                       ←   un módulo por responsabilidad: config, anfitrion, registro, conexion,
│       │                                 pantalla (ver), entrada (actuar), ventanas, maquina, toma, escenario
│       │                                 canales/: ssh · guestcontrol, intercambiables (VM_CANAL)
│       ├── tipear.py · mover.py      ←   planes de tecleo y ratón humanos (lógica pura)
│       └── ocr_buscar.py · ocr.swift ←   localizar texto por OCR (ocr.swift: Vision, opcional en macOS)
│
└── editor/                           ← FASE 2: editar (índice: editor/CLAUDE.md)
    ├── comun/                        ←   lo de todas las líneas: transcribir.py, energia.py, verificar_corte.sh,
    │                                     detectar_silencio.sh, BENCHMARK-WHISPER.md, glosario.json, fuentes/
    ├── shorts/                       ←   Short vertical: SHORT-IDEAL.md (CÓMO DEBE QUEDAR), fusión cara+pantalla,
    │                                     short_desde_toma.py, subtitular.py, verificar_short.py...
    ├── directos/                     ←   clips 16:9 de un directo: CLAUDE.md + construir_clip.sh
    ├── crudo/                        ←   fuentes de trabajo (LOCAL, no se versiona)
    └── videos-editados/              ←   resultados + _cortes.log (LOCAL, no se versiona)
```
**¿Qué línea de la Fase 2?** La tabla de `editor/CLAUDE.md` lo decide en una línea: toma de `crear-shorts/` →
`short_desde_toma.py`; Short de pantalla + vídeo con la cara → fusión; directo real → `editor/directos/`.

### Cómo crece el proyecto sin desordenarse
- Lo que sirva a **más de una línea** va a `nucleo/` (un módulo por responsabilidad, sin CLI, sin depender de nada
  de `editor/` ni de `crear-shorts/`). Lo propio de una línea, en su carpeta. **Un script nunca importa a otro.**
- Una capacidad nueva de la VM va al módulo de `crear-shorts/herramientas/vm/` que le toca, y se expone en
  `vm/__init__.py` (y en la CLI de `vm_control.py` si hace falta).
- Una demo nueva: copia `DEMO-SSHOLE/` o `DEMO-IDOR/`; solo `demo_<tema>.py` es nuevo.
- El contrato entre fases (`nucleo/toma.py`) es el único punto de contacto: si cambia un campo, cambian los dos lados.
- `pruebas/` vigila todo esto (dependencias, CLIs, y que ninguna ruta citada en un .md esté muerta). Pásalas antes
  de cada commit.

### ⚠️ Qué NO está en el repositorio

Este repo guarda **metodología impersonal**: documentación, scripts, plantillas, glosario y la fuente de los
subtítulos. **Nada de un vídeo concreto se versiona.** El `.gitignore` excluye:

- **Las carpetas de trabajo enteras** `editor/crudo/` y `editor/videos-editados/` (solo se versiona su `.gitkeep`):
  fuentes, clips, transcripciones, planes de fusión, subtítulos `.subtitulos.json`, registros de toma
  (`.steps.jsonl`, `.mapa.md`) y el registro de cortes `_cortes.log`. Viven solo en tu disco.
- Esos mismos tipos de archivo estén donde estén, más vídeo, audio y modelos Whisper (`*.bin`).

Si un caso real enseña algo, se documenta **la lección** (medidas, reglas, errores) en la metodología, no los
archivos del vídeo. Las plantillas genéricas van en `editor/shorts/plantillas/`.

---

## 🚀 Si eres un agente de IA que retoma este trabajo — lee en este orden

1. **Este README** (visión global) y **`PENDIENTE.md`** (qué está pendiente de verdad, ahora mismo).
   El objetivo de todo es **`editor/shorts/SHORT-IDEAL.md`**: cómo debe quedar el Short final.
2. **`CLAUDE.md`** y **`PORTABILIDAD.md`** (reglas no negociables + instalación en tu anfitrión).
3. **`crear-shorts/ARQUITECTURA.md`** — qué es el sistema, cómo encajan sus piezas.
4. ¿Vas a **grabar/generar** una demo nueva?
   → `crear-shorts/METODOLOGIA/00-empezar-aqui-vm.md`, y si es de terminal (nmap/ssh/exploits)
   **`METODOLOGIA/10-plantilla-demo-terminal.md`** (checklist para que salga bien a la primera).
   Copia `DEMO-SSHOLE/demo_sshole.py` o `DEMO-IDOR/demo_idor.py` como esqueleto de código.
   La toma deja `editor/crudo/<toma>.mp4` + `.steps.jsonl` + `.mapa.md` para la Fase 2.
5. ¿Vas a **convertir esa toma en Short**? → `editor/shorts/short_desde_toma.py <toma> --titulo ...`
   (automático). ¿Es un directo real sin registro de pasos? → `editor/directos/CLAUDE.md` (16:9) y
   `editor/shorts/METODOLOGIA-SHORTS.md` (9:16), a mano.
   ¿Te pasan el Short de pantalla + un vídeo con la cara y la voz del usuario para juntarlos? →
   `editor/shorts/METODOLOGIA-FUSION-CARA.md`.
6. Mira siempre `editor/videos-editados/_cortes.log` antes de tocar un clip ya hecho:
   contiene los tramos exactos (en segundos) de cada clip construido.

### Reglas de oro heredadas (válidas en todo el repo)

- **Precisión por encima de coste.** Mejor gastar más comprobaciones que dejar un corte mal hecho.
  Detalle en `editor/directos/CLAUDE.md`. (Precisión no es lentitud: el Short final va lo más al grano posible,
  `editor/shorts/SHORT-IDEAL.md`.)
- **Verifica, no asumas.** Tras cada acción (un clic en la Fase 1, un corte en la Fase 2),
  compruébala: con OCR/screenshot en la grabación, extrayendo fotogramas en la edición.
- **Nunca toques `_cortes.log` a ciegas.** Si aparece ausente o truncado, es un problema
  transitorio (mira la Papelera) — nunca lo recrees desde cero; añade al final (APPEND).

---

## 🛠️ Herramientas base

Comunes a los tres sistemas (instalación por SO en [`PORTABILIDAD.md`](PORTABILIDAD.md)):

- **ffmpeg / ffprobe** — todo el corte, recodificación y análisis (Fase 2).
- **Whisper** (whisper.cpp o faster-whisper), modelo **`large-v3-turbo`** — transcripción con timestamps (Fase 2).
  Elegido midiendo, no por tamaño: `editor/comun/BENCHMARK-WHISPER.md`.
- **yt-dlp** — descargar directos si se parte de una URL (Fase 2).
- **VirtualBox + ssh + `vm_control.py`** (Fase 1) — control de la VM, igual en los tres SO; OCR con Tesseract
  (en macOS puede usarse Vision).

Desarrollo: la metodología se midió primero en un Mac con Apple Silicon (invitado ARM64) y se portó a un anfitrión
Windows 11 (invitado x86-64). Los resultados medidos de cada plataforma están en `crear-shorts/METODOLOGIA/08-maquina-virtual.md` y `PENDIENTE.md`.
