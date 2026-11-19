# cutly estudio — la interfaz de escritorio

Una ventana de PySide6 con **el Claude Code instalado dentro, con su interfaz completa**, y al lado las pestañas
visuales de lo que el terminal hace mal: aportar el material arrastrándolo, ver la VM, ver un vídeo, revisar
subtítulos. **El material no se coloca en carpetas: se arrastra a la pestaña que toca.**

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Nueva sesión · Continuar la última │ Preparar VM · Grabar demo · Fusionar · Subtitular · …     │ ← un botón por skill
├────────────────────────────────────────────┬─────────────────────────────────────────────────┤
│                                            │ Material│Fusión│Subtítulos│Directo│Shorts│VM      │
│   Claude Code (el de `claude`, de verdad)  │ ┌ Cara ─────────┐  ┌ Pantalla ─────┐           │
│   misma sesión, permisos, comandos /...    │ │ suelta aquí   │  │ suelta aquí   │ ← ranuras │
│   (soltar un archivo aquí pega su ruta)    │ └───────────────┘  └───────────────┘           │
│                                            │ [Fusionar con Claude]                          │
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

## Las pestañas: una por cosa que quieres hacer, cada una con su sitio para soltar

| Pestaña | Qué sueltas ahí | Qué hace Claude |
|---|---|---|
| **Directo → clips** | el directo (o pegas un enlace) | propone fragmentos (`/directo-a-clips`); salen en una tabla con el directo al lado: clic = saltar a ese momento, marcas los que quieres y "Cortar los elegidos" (`<directo>.candidatos.json`, `nucleo/candidatos.py`) |
| **Cara + pantalla** | tu cara y el Short de pantalla (en sus ranuras, o los dos juntos en cualquier parte: cada uno va a la suya) | `/fusionar-cara-pantalla <cara> <pantalla> [Título]` |
| **Grabación → Short** | grabaciones sueltas (sin registro de la VM) e intro/imágenes, **en orden** (se reordenan arrastrando) | `/short-desde-grabacion <fuentes…> [Título]`: decide los planos y monta el Short mudo con un plan JSON (`construir_short.py`) |
| **Subtítulos** | el Short montado | `/subtitular-short <short>`; luego revisas el texto con el vídeo sincronizado y "Revisado" |
| **Resultados** | cualquier vídeo, para verificarlo | lo que ha salido; menú: subtitular, revisar sus subtítulos, preguntar |
| **Material** | lo que sea | la biblioteca: papel, miniatura, datos; menú "Pedir a Claude" según el papel |
| **VM** | — | estado, pantalla en directo, diagnóstico, arrancar, iniciar sesión, apagar (`vm_control.py`) |

Soltar **en la zona vacía** de una pestaña cuenta como soltarlo en su sitio (`traer_soltados` de cada panel); en una
pestaña sin sitio para material (VM), va a Material.

**El material**: soltar un archivo en una ranura lo trae a `editor/crudo/` (como **enlace**, sin copiar ni ocupar
espacio, si está en el mismo disco; si no, se copia en segundo plano) y le fija ese papel en
`editor/crudo/material.json` (`nucleo/material.py`). Soltarlo en cualquier otra parte de la ventana lo lleva a
Material con el papel deducido (vertical mudo = pantalla, vertical con voz = cara o Short, horizontal largo con voz =
directo…). Claude lo consulta con `python editor/comun/material.py`. Quitar algo del material no borra el original.

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
| El Short de pantalla lleva una pista de audio (muda): por tener audio salía como "cara" | `material.describir` mide el pico (volumedetect): por debajo de −60 dB cuenta como mudo |
| Soltar un vídeo sobre el terminal haría que la página navegase a ese fichero (y el terminal desaparecería) | la página no navega tras cargar; el soltar se intercepta y pega la ruta en la sesión |
| Soltar en la ranura un vídeo de otra carpeta del mismo disco | entra como enlace duro: instantáneo y sin duplicar (medido: 2 nombres, 1 fichero) |
| Soltar dos veces el mismo vídeo lo duplicaba (`x-2.mp4`) | `material.ya_esta`: se reconoce el mismo fichero (enlace o copia idéntica) |
| Usar tu cara como fuente de "Grabación → Short" le cambiaba el papel y vaciaba la ranura Cara | la lista de fuentes no pisa un papel fijado |

## Añadir cosas

- **Un flujo nuevo:** una skill en `.claude/skills/<nombre>/SKILL.md` (frontmatter `name` + `description`). Sale como
  botón; si quieres rótulo u orden, añádela a `ROTULOS` en `estudio/flujos.py`.
- **Una pestaña nueva** (una cosa nueva que hacer): un `QWidget` en `estudio/paneles/` que lea con `nucleo/` o `vm/`,
  actúe con `entorno.ejecutar_cli` (CLIs del repo) y le pida cosas a Claude con una señal `pedir = Signal(str)` (la
  ventana la conecta sola). Su sitio para soltar: una `Ranura(papel, ...)` (un archivo, `paneles/ranura.py`) o una
  lista como `ListaFuentes` (varios, `paneles/grabacion.py`), más `traer_soltados(rutas)` para lo que se suelte en la
  zona vacía. Normalmente va con su skill en `.claude/skills/`. Un papel nuevo se añade a `ROLES` en
  `nucleo/material.py`. Se registra en `ventana.py`.
- Atajos: Ctrl+1…6 cambian de pestaña; Ctrl+` vuelve al terminal.
- Las pruebas de la app están en `pruebas/test_estudio.py` (sin abrir ninguna sesión de Claude Code).
