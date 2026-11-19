# cutly estudio — la interfaz de escritorio

Una ventana de PySide6 con **el Claude Code instalado dentro, con su interfaz completa**, y al lado las pestañas
visuales de lo que el terminal hace mal: ver la VM, ver un vídeo, revisar subtítulos.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Nueva sesión · Continuar la última │ Preparar VM · Grabar demo · Fusionar · Subtitular · …     │ ← un botón por skill
├────────────────────────────────────────────┬─────────────────────────────────────────────────┤
│                                            │  VM │ Shorts │ Subtítulos                        │
│   Claude Code (el de `claude`, de verdad)  │  estado sin credenciales, pantalla en directo,  │
│   misma sesión, permisos, comandos /...    │  doctor / arrancar / login / apagar             │
│                                            │  vídeos + verificar_short                       │
│                                            │  revisar subtítulos con el vídeo sincronizado   │
└────────────────────────────────────────────┴─────────────────────────────────────────────────┘
```

## Arrancar

```bash
pip install -r estudio/requisitos.txt        # PySide6 + pywinpty (Windows) / ptyprocess (macOS, Linux)
python -m estudio                            # sesión nueva de Claude Code en el repo
python -m estudio --continuar                # retoma la última conversación (claude --continue)
```

Requisitos: Claude Code instalado y con sesión iniciada (`claude` en el PATH) y conexión a internet (Claude Code la
necesita igual; xterm.js se carga de jsDelivr con la versión fijada). Para iniciar sesión en la VM desde la pestaña VM:
`VM_GUEST_PASSFILE` en el entorno, como con `vm_control.py`.

## Cómo funciona (y por qué así)

- **Claude Code no se reimplementa: se ejecuta.** `terminal/pty.py` lanza `claude` en un pseudo-terminal REAL
  (ConPTY en Windows con pywinpty; pty en macOS/Linux) y `terminal/widget.py` lo muestra con **xterm.js** (el emulador
  del terminal de VS Code) dentro de un `QWebEngineView`, conectados por `QWebChannel`. Para Claude Code es un
  terminal normal: misma identificación, misma memoria, mismos `CLAUDE.md`, permisos, comandos y tareas.
- **Los botones son las skills** del proyecto (`.claude/skills/<nombre>/SKILL.md`): cada uno escribe `/<nombre>` en la
  sesión, como si lo tecleases. Una skill nueva aparece sola como botón (`estudio/flujos.py`).
- **Claude y la app se hablan por ficheros**, los mismos contratos que usan las CLIs: Claude escribe
  `<video>.subtitulos.json`, la pestaña Subtítulos lo muestra al instante (vigila el fichero), lo corriges, y
  "Revisado" lo guarda y escribe en la sesión que ya puede quemarlos.
- **La app no duplica lógica**: lee con `nucleo/` y `vm/` (`entorno.py`) y lo que modifica algo lo hacen las CLIs del
  repo (`vm_control.py`, `verificar_short.py`) o Claude Code.

## Teclado en el terminal

- **Ctrl+C** con texto seleccionado copia; sin selección va a Claude Code (interrumpir), como en Windows Terminal.
- **Ctrl+V** pega el portapapeles como texto pegado (Claude Code lo distingue de lo tecleado).

## Medido al construirla (2026-11-19, Windows 11)

| Hecho | Consecuencia |
|---|---|
| ConPTY pregunta al arrancar "¿qué terminal eres?" (`ESC[c`) y no muestra la salida hasta que se le contesta | xterm.js contesta solo; en las pruebas sin interfaz se contesta a mano (`pruebas/test_estudio.py`) |
| Una página local no puede cargar `qrc:///qtwebchannel/qwebchannel.js` ("QWebChannel is not defined") | `widget.py` lo lee de los recursos de Qt y lo inserta en la página |
| Caracteres no ASCII en la línea de órdenes del pseudo-terminal rompen el arranque del programa | `claude` no los lleva; la salida con tildes y € sí llega bien |
| Python liberaba el emisor de una tarea en segundo plano antes de que terminase ("Signal source has been deleted") | `entorno._VIVOS` los mantiene hasta que acaban |
| Resaltar la fila del subtítulo que suena marcaba la tabla como editada | el resaltado bloquea las señales de la tabla |

## Añadir cosas

- **Un flujo nuevo:** una skill en `.claude/skills/<nombre>/SKILL.md` (frontmatter `name` + `description`). Sale como
  botón; si quieres rótulo u orden, añádela a `ROTULOS` en `estudio/flujos.py`.
- **Una pestaña nueva:** un `QWidget` en `estudio/paneles/` que lea con `nucleo/` o `vm/` y actúe con
  `entorno.ejecutar_cli` (CLIs del repo) o mandando texto a la sesión (`Ventana.enviar`); se añade en `ventana.py`.
- Las pruebas de la app están en `pruebas/test_estudio.py` (sin abrir ninguna sesión de Claude Code).
