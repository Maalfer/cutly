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

---

## ⚠️ ESTADO ACTUAL DE LA MÁQUINA (leer primero)

Fecha: miércoles 18 de noviembre de 2026, ~20:00

### Apps OCULTAS (ocultadas por el agente — RESTAURAR con `set visible to true`):
- `stable` (ventana del TUI de OpenCode — "Demostración ClickFix en Mac")
- `Warp` (terminal que aloja OpenCode)
- `Brave Browser`
- `WhatsApp`
- `OBS` (la grabadora del usuario — si estaba grabando, SIGUE grabando)

### Proceso activo:
- `python3 c2_server.py` corriendo en una ventana de Terminal (id ~2489, posición {10,80→630,750})
  escuchando en `http://127.0.0.1:4444/upload`

### Escenario visible en pantalla:
- Safari con la página falsa "Mac Cleaner Pro" (~/Desktop/clickfix-demo/fake-page.html) en {290,40→990,790}
- Terminal víctima (id ~2487) en {650,80→1270,750} — ya ejecutó el payload
- Terminal C2 (id ~2489) en {10,80→630,750} — muestra el botín exfiltrado
- Botín en `~/Desktop/clickfix-demo/c2_loot/` (zip con datos decoy)

### PENDIENTE (cuando el usuario lo pida):
1. Restaurar apps ocultas
2. Matar C2: `pkill -f c2_server.py`
3. Cerrar ventanas de Terminal y Safari
4. Borrar botín: `rm -rf ~/Desktop/clickfix-demo/c2_loot`
5. Verificar limpieza: `launchctl list | grep systemcheck` (debe salir vacío — v1 ya limpiada)

---

## 📚 Índice de documentación

| Doc | Contenido |
|-----|-----------|
| `METODOLOGIA/01-control-total-mac.md` | Cómo la IA controla el MacBook al 100%: permiso de Accesibilidad + teoría |
| `METODOLOGIA/02-kit-herramientas.md` | Las herramientas: OCR, cursor, cliclick, find_button — con código y uso |
| `METODOLOGIA/03-gestion-ventanas.md` | Lecciones de z-order, apps fullscreen, direccionar ventanas por ID |
| `METODOLOGIA/04-flujo-toma-video.md` | Protocolo de toma: fases, pacing, verificación, "no tocar" |
| `DEMO-CLICKFIX/05-demo-completa.md` | La demo ClickFix v2 (exfiltración): contexto, archivos, arquitectura |
| `DEMO-CLICKFIX/06-reproducir-paso-a-paso.md` | Reproducción exacta comando a comando |
| `DEMO-CLICKFIX/07-limpieza-restore.md` | Limpieza completa del sistema y restauración |
| `herramientas/` | Código fuente de las herramientas (copias) |

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
