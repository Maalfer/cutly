# 🎬 CREAR-SHORTS — Base de conocimiento para crear videos con IA controlando el ordenador

> **Propósito:** Que cualquier modelo/agente de IA pueda retomar el trabajo y seguir
> creando videos de demos de seguridad donde la IA controla el ordenador al 100%
> mientras el usuario graba la pantalla.

> **⚠️ Multiplataforma:** esta carpeta describe la implementación en **macOS** (es donde se
> desarrolló: `cliclick`, AppleScript, OCR con Vision…). La *metodología* (verificar cada acción,
> pacing cinematográfico, gestión de z-order, toma única sin tocar) es **la misma en Windows y
> Linux**; solo cambian los comandos del kit de control. La tabla de equivalencias
> macOS ⇄ Windows ⇄ Linux y cómo instalar el kit en cada sistema están en **`../PORTABILIDAD.md`**
> (sección 2). Lee ESTA carpeta para entender el *cómo* y el *porqué*, y `PORTABILIDAD.md` para
> traducir cada comando a tu sistema.

## 🤖 Qué puede hacer la IA (control completo del ordenador)

Con este kit, un modelo (Claude u otro) **controla el ordenador por completo** para montar la
demo que haga falta, mientras el usuario graba con OBS:

- **Cursor:** mover (con trayecto cinematográfico), clicar, doble-clic, arrastrar, rueda.
- **Teclado:** escribir texto, combinaciones y atajos, navegar menús y campos.
- **Aplicaciones:** abrirlas, esperar a que carguen, enfocarlas, escribir en ellas y cerrarlas
  (navegador, Burp Suite, terminal, editores… cualquiera).
- **Ventanas:** posicionarlas, ocultarlas/minimizarlas, listar la pila, montar un layout estable.
- **"Ver" la pantalla:** OCR con coordenadas + análisis de píxeles + enumeración de ventanas,
  para **verificar cada acción** antes de la siguiente.

Así puede hacer demos completas de principio a fin: p. ej. **explicar un IDOR** (abrir el
navegador, ir a una ruta, loguear, abrir Burp, interceptar, modificar y reenviar) — ver
`DEMO-IDOR/ejemplo-idor-con-burp.md`. El *cómo* general está en `METODOLOGIA/05` y `06`.

---

## ⚠️ Estado de la máquina: verifícalo en CADA sesión (no es fijo)

Antes de empezar y al terminar una toma, **comprueba el estado real de la máquina** — no asumas
nada de una sesión anterior. Rutina al **abrir** sesión:

1. **Verifica el control** (permiso + herramientas): mueve el cursor y léelo
   (`cliclick m:300,600 && ~/Desktop/ctrl-kit/mousepos`); si no se mueve, ver doc 01 / `PORTABILIDAD.md`.
2. **Enumera ventanas y pasa el gate anti-solape** (doc 03): que ninguna tape a otra.
3. **Mira una captura** (visión, doc 01 §4): confirma a ojo qué hay abierto y el layout.

Al **cerrar** una toma, deja la máquina como estaba: restaura apps ocultas
(`set visible to true`), cierra ventanas que creaste, mata procesos de la demo y borra datos de
prueba (cada ejemplo trae su limpieza, p. ej. `DEMO-CLICKFIX/limpieza-restore.md`).

> Si en una sesión dejas algo a medias (apps ocultas, un servidor corriendo), **anótalo en una nota
> de scratch de esa sesión**, no aquí: este README es metodología permanente, no el estado de un día.

---

## 📚 Índice de documentación

**METODOLOGÍA** (el *cómo*, sirve para cualquier demo):

| Doc | Contenido |
|-----|-----------|
| `METODOLOGIA/01-control-total-mac.md` | Cómo la IA controla el ordenador al 100%: permiso + teoría |
| `METODOLOGIA/02-kit-herramientas.md` | Las herramientas: OCR, cursor, cliclick, find_button — con código y uso |
| `METODOLOGIA/03-gestion-ventanas.md` | Lecciones de z-order, apps fullscreen, direccionar ventanas por ID |
| `METODOLOGIA/04-flujo-toma-video.md` | Protocolo de toma: fases, pacing, verificación, "no tocar" |
| `METODOLOGIA/05-controlar-aplicaciones.md` | **Patrón general para conducir CUALQUIER app**: abrir/esperar/enfocar/cerrar, multi-app, sincronización, robustez |
| `METODOLOGIA/06-navegador-y-herramientas-gui.md` | **Navegador** (URL, clics, formularios, pestañas, leer) y **herramientas GUI** (Burp Suite como caso) |
| `METODOLOGIA/08-maquina-virtual.md` | **Controlar una VM (VirtualBox/Kali)** en vez del anfitrión: qué canal sirve para qué, resultados medidos (10/10), 6 fallos de montaje y comparación VM vs anfitrión |
| `METODOLOGIA/07-auditoria-de-pruebas.md` | **Fallos reales** encontrados probando la navegación + **protocolo de pruebas** para validar el control en cualquier SO |

**EJEMPLOS** (demos completas de referencia):

| Demo | Contenido |
|------|-----------|
| `DEMO-CLICKFIX/demo-completa.md` · `reproducir-paso-a-paso.md` · `limpieza-restore.md` | Demo ClickFix v2 (exfiltración por copiar-y-pegar): contexto, arquitectura, reproducción y limpieza |
| `DEMO-IDOR/ejemplo-idor-con-burp.md` | **Demo de IDOR** conduciendo navegador + Burp Suite, de principio a fin |
| `herramientas/` | Código de las herramientas: `ocr.swift`, `mousepos.swift`, `find_button.py` **`winlist.swift`** + **`visibilidad.py`** (qué ve realmente una persona: enterrada/cortada/overlay), `ocr_buscar.py` **`mac-control.sh`** (funciones que hacen y verifican) y la **entrada humana**: `tipear.py`, `mover.py`, `teclear.swift` |

## 📂 Carpetas del proyecto fuera de esta doc

- `~/Desktop/ctrl-kit/` — herramientas compiladas en vivo (ocr, mousepos)
- `~/Desktop/clickfix-demo/` — la demo ClickFix completa (página, payload, C2, decoys)

## 🔑 El permiso maestro (macOS)

El binario `/Users/mario/.opencode/bin/opencode` está añadido en:
**System Settings → Privacidad y seguridad → Accesibilidad**

Sin esto, NADA del control funciona en macOS. Si un modelo nuevo no puede clicar/teclear,
verificar este permiso primero (es la causa #1 de fallos).

**En otros sistemas el "permiso maestro" es distinto** (ver `../PORTABILIDAD.md` §2):
- **Windows:** normalmente no hace falta permiso; solo si la ventana objetivo corre **elevada**
  (como admin), el automatizador también debe ir elevado.
- **Linux X11:** permitido de serie.
- **Linux Wayland:** el input sintético necesita `ydotool` con su daemon y acceso a `/dev/uinput`;
  si se complica, graba la demo en una sesión **X11**.
