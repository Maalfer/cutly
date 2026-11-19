# 🎬 CREAR-SHORTS — Demos controladas por IA dentro de una VM

> **Propósito:** que un agente de IA ejecute demos de ciberseguridad **dentro de una VM de VirtualBox**,
> que VirtualBox graba en el anfitrión (`rec start`, sin OBS, sin que el usuario toque nada). **Nunca en
> el ordenador anfitrión.** Funciona con anfitrión **Windows, macOS o Linux** (ver `../PORTABILIDAD.md`).
> Arquitectura completa: [`ARQUITECTURA.md`](ARQUITECTURA.md).

**Empieza por [`METODOLOGIA/00-empezar-aqui-vm.md`](METODOLOGIA/00-empezar-aqui-vm.md)** (montaje único, protocolo
de toma, verificación, referencia). Qué es el sistema y cómo encajan sus piezas: [`ARQUITECTURA.md`](ARQUITECTURA.md)
(incluye la propuesta de pipeline con agentes especializados + verificación independiente). Estado real y
pendientes (corto): [`../PENDIENTE.md`](../PENDIENTE.md) — historial detallado sesión a sesión:
[`historial/HISTORIAL-SESIONES.md`](historial/HISTORIAL-SESIONES.md).

## 🤖 Qué puede hacer la IA
Todo con **entrada humana** (ritmo de tecleo variable con errores corregidos, ratón con trayecto curvo):

- **Ratón y teclado** del invitado (xdotool por SSH), con la **guarda de foco** (`--in "Título"`).
- **Ver:** captura de la VM (~0,08 s), OCR (Tesseract/Vision), búsqueda por plantilla, espera a que la pantalla se asiente.
- **Apps:** lanzar, enfocar, colocar, esperar (Firefox, Burp Suite, terminal…).
- **Verificar sin OCR:** el lab registra cada petición (`labcheck`).
- **Grabar y registrar:** `rec` (VirtualBox en el anfitrión, cursor incluido, sin OBS ni nada dentro de la VM) + registro JSONL de cada paso + **mapa de
  edición automático** con los segundos de cada momento → entrada directa de la Fase 2: `editor/shorts/short_desde_toma.py` genera el **Short 1080×1920 con la banda negra fija** para tu cara.
- **Estado de partida rápido:** `suspend`/`resume` (savestate, no snapshot) para no repetir los diálogos de Burp.

## 📚 Índice
| Doc | Contenido |
|---|---|
| `METODOLOGIA/00-empezar-aqui-vm.md` | **Punto de entrada**: montaje, toma, verificación, referencia |
| `METODOLOGIA/04-flujo-toma-video.md` | Protocolo de toma: fases, pacing cinematográfico, "no tocar" |
| `METODOLOGIA/05-controlar-aplicaciones.md` | Patrón para conducir cualquier app: abrir/esperar/enfocar/verificar |
| `METODOLOGIA/06-navegador-y-herramientas-gui.md` | Navegador y herramientas GUI (Burp Suite) |
| `METODOLOGIA/07-auditoria-de-pruebas.md` | Fallos reales hallados (lecciones del enfoque anfitrión) y protocolo de pruebas |
| `METODOLOGIA/09-conducir-apps-kali.md` | **Guía general** para conducir cualquier app de Kali + fichas por app (Firefox, Burp, terminal) |
| `METODOLOGIA/10-plantilla-demo-terminal.md` | **Plantilla para una demo de terminal "perfecta a la primera"**: despliegue, ventanas, encuadre del Short, ritmo — empieza aquí para una demo nueva de nmap/ssh/exploits |
| `METODOLOGIA/08-maquina-virtual.md` | Qué canal sirve para qué en VirtualBox, mediciones, fallos de montaje (37-42) |
| `DEMO-IDOR/` | Demo de ejemplo: navegador + Burp contra un lab local (`lab_idor.py`) |
| `DEMO-SSHOLE/` | Demo de ejemplo (la más completa): nmap + bypass SSH + reverse shell contra un laboratorio Docker de BunkerLabs; plantilla de código a copiar |
| `herramientas/` | `vm_control.py` (CLI + API) sobre el paquete `vm/` (un módulo por responsabilidad: ver `vm/__init__.py`), `tipear.py`/`mover.py` (planes humanos), `ocr_buscar.py`, `ocr.swift` (OCR Vision, opcional en macOS) |

> Los docs 05-07 nacieron controlando el anfitrión macOS: los **comandos** de esos ejemplos ya no se usan (su
> equivalente es `vm_control.py`), pero los **principios y fallos** siguen vigentes.

## 🎞️ Catálogo de demos

Añade una fila aquí cada vez que una demo nueva quede cerrada (la plantilla de código a copiar es siempre
la última de tipo "terminal" o "GUI" más reciente, por ser la más depurada).

| Demo | Tipo | Tema | Short generado | Estado |
|---|---|---|---|---|
| `DEMO-IDOR/` | GUI (navegador + Burp) | IDOR (Insecure Direct Object Reference) | sí | referencia |
| `DEMO-SSHOLE/` | Terminal | CVE ficticio "sshole": bypass SSH por contraseña larga en musl `crypt()` + reverse shell | sí | referencia, dada por buena por el usuario |

Antes de empezar una demo de un tema que te suene parecido a una ya hecha, mira esta tabla — puede que
solo haga falta adaptar una existente en vez de partir de cero.
