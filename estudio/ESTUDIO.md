# cutly estudio — la interfaz de escritorio

Una ventana (PySide6, igual en Windows, macOS y Linux) con **Claude Code u OpenCode instalados dentro, con su
interfaz completa** (Sesión → Motor elige cuál, y se puede ir alternando), y alrededor una **sección por cosa que
quieres hacer** con tus vídeos. El material no se coloca en carpetas: **se suelta en la sección de lo que quieres
hacer**.

```
┌ Sesión · Ver · Flujos · Ayuda ─────────────────────────────────────────────────────────────────────┐
│ Directo → clips    │ ┌ Cara ─────────────┐ ┌ Pantalla ──────────┐  │ Claude Code / OpenCode        │
│ Cara + pantalla  ◀ │ │ suelta aquí       │ │ suelta aquí        │  │ (el que elijas en Sesión →    │
│ Grabación → Short  │ └───────────────────┘ └────────────────────┘  │  Motor: misma sesión, permisos,│
│ Resultados  ●       │ Título: [...] [x] Subtitular  [Fusionar con Claude] │ comandos /…; soltar un  │
│ Material · VM      │                                               │  archivo aquí pega su ruta)  │
│                     │                                               │  F12 lo oculta / muestra     │
└ sesión · material · VM ─────────────────────────── [Ir a Resultados] ──────────────────────────────┘
```

## Arrancar

```bash
pip install -r requirements.txt              # todo: estudio + los flujos de vídeo/VM (un solo paso)
python -m estudio                            # sesión nueva, con el motor elegido (Sesión → Motor; Claude Code por defecto)
python -m estudio --continuar                # retoma la última conversación de ese motor (--continue)
```

Requisitos: Claude Code y/o OpenCode instalados y con sesión iniciada (`claude` y/o `opencode` en el PATH; si el
elegido no está, el panel lo explica y deja cambiar de motor desde ahí mismo) y conexión a internet (lo necesitan
igual; xterm.js se carga de jsDelivr con versión fijada). Para iniciar sesión en la VM desde la sección VM:
`VM_GUEST_PASSFILE` en el entorno.

### Dos motores, un solo panel (Sesión → Motor)

El panel acoplable no es específico de Claude Code: `estudio/terminal/widget.py` lanza CUALQUIER programa en un
pseudo-terminal real y lo muestra con xterm.js — el programa en sí (`estudio/motores.py`) es lo único que cambia.
Sesión → Motor dice cuál cargar (Claude Code u OpenCode), lo recuerda entre arranques (QSettings) y, si ya hay una
sesión abierta, pregunta antes de cambiarla (como cerrar la app mientras trabaja).

**Cómo sabe la app en qué está trabajando cada uno** (arrancando/trabajando/espera tu respuesta/listo, barra de
estado): mismo contrato de fichero en los dos casos (`CUTLY_ESTADO_FICHERO`, JSON `{estado, mensaje}`), pero cada
motor lo rellena con SU propio mecanismo de extensión — no hay una API común entre ellos:
- **Claude Code**: sus hooks nativos (`.claude/settings.json` → `estudio/hooks/estado_claude.py`).
- **OpenCode**: un plugin (`.opencode/plugins/cutly-estado.js`) que escucha `ctx.event.subscribe()`
  (`session.execution.started/succeeded` → trabajando/libre) y `ctx.permission.hook("evaluate")` (`effect=="ask"`
  → necesita tu respuesta).

Las **skills del proyecto** (`.claude/skills/*/SKILL.md`, los botones de cada sección y el menú Flujos) funcionan
con los dos motores sin ningún cambio: OpenCode las lee de ahí mismo de forma nativa (comprobado: `opencode run
"lista tus comandos"` las devuelve junto a las suyas propias).

## Las secciones: dónde se suelta cada cosa

| Sección | Qué sueltas | Qué hace Claude (skill) |
|---|---|---|
| **Directo → clips** | el directo (o pegas un enlace) | propone fragmentos (`/directo-a-clips`); aparecen en una tabla con el directo al lado: ver cada uno, elegir y "Cortar los elegidos" (`<directo>.candidatos.json`, `nucleo/candidatos.py`) |
| **Cara + pantalla** | tu cara y el Short de pantalla (en sus ranuras, o los dos juntos: cada uno va al suyo) | `/fusionar-cara-pantalla <cara> <pantalla> [Título]`; con la casilla «Subtitular también» (marcada por defecto), Claude sigue solo con `/subtitular-short` al terminar |
| **Grabación → Short** | grabaciones sueltas (sin registro de la VM) e intro/imágenes, en orden | `/short-desde-grabacion <fuentes…> [Título]` (plan JSON + `construir_short.py`) |
| **Resultados** | cualquier vídeo, para verificarlo | lo que Claude termina aparece solo: ver, verificar contra el Short ideal (solo verticales), pedir sus subtítulos («Subtitular con Claude»). Si tiene unos a medio revisar, la tabla de revisión aparece aquí mismo bajo el vídeo: corrige el texto y pulsa «Revisado» |
| **Material** | lo que sea | la biblioteca: papel de cada archivo, miniatura, datos; menú "Pedir a Claude" según el papel |
| **VM** | — | estado sin credenciales, pantalla en directo, diagnóstico, arrancar, iniciar sesión, guardar estado, apagar |

Soltar en la **zona vacía** de una sección cuenta como soltarlo en su sitio; donde no hay sitio (VM), va a Material.
Cada sección tiene **una** acción principal resaltada, una explicación arriba y una línea de estado abajo.

**El material** (`nucleo/material.py`): soltar un archivo lo trae a `editor/crudo/` (enlace sin copiar si está en el
mismo disco; si no, copia en segundo plano; soltar dos veces lo mismo no lo duplica) y fija su papel en
`editor/crudo/material.json`. Claude lo consulta con `python editor/comun/material.py`. Quitarlo no borra el original.

**Cuando Claude termina algo**, la app se entera sola (un único vigía de carpetas, `servicios.py`): la sección que
toca se marca con ● en la barra lateral, la barra de estado ofrece "Ir a…" y la sección ya lo tiene abierto (los
subtítulos para revisar, la propuesta de fragmentos, el vídeo terminado; un vídeo se anuncia cuando deja de crecer).

## La app sabe en qué está Claude

Los hooks del proyecto (`.claude/settings.json` → `estudio/hooks/estado_claude.py`) escriben en un fichero temporal
en qué está **esta** sesión (la app le pasa la ruta en `CUTLY_ESTADO_FICHERO`; en tu terminal de siempre no hacen
nada, y nunca imprimen ni bloquean). La app lo enseña en la barra de estado y en el título del panel:

| Estado | De dónde sale | Qué hace la app |
|---|---|---|
| Claude arrancando… | sesión nueva | lo que pidas espera a que pueda recibirlo |
| Claude trabajando… | al enviarle algo (y `UserPromptSubmit`, `PostToolUse`) | lo que pidas desde una sección **espera en cola** ("N petición(es) en espera · enviar ya") y se envía sola al terminar |
| ⚠ Claude espera tu respuesta | `Notification` de permiso | muestra el panel de Claude y hace parpadear la ventana en la barra de tareas |
| Claude listo | `Stop`, o su terminal quieto 8 s (si lo interrumpes con Esc no hay aviso) | envía lo siguiente de la cola |

Cerrar la app o cambiar de sesión mientras trabaja pide confirmación, y detiene también lo que Claude haya lanzado
(una transcripción no se queda corriendo sola). Si abres la app desde otra sesión de Claude Code, la suya no hereda
sus variables (no se creería una sesión hija).

**Permisos**: el mismo `settings.json` permite sin preguntar solo las herramientas del repo que usan los flujos,
ffmpeg/ffprobe y editar dentro de `editor/crudo/` y `editor/videos-editados/` (`_cortes.log` siempre pregunta, para
que nunca se recree). Todo lo demás sigue preguntando como siempre. Solo se aplica en carpetas que Claude Code ya
considere de confianza.

## Accesibilidad

- **Teclado en todo**: Ctrl+1…7 cambia de sección; F12 muestra/oculta Claude; Ctrl+` le da el foco; F1 lista todos los
  atajos. Las ranuras tienen foco (Intro elige archivo, Supr vacía, Ctrl+V pega una ruta copiada); la lista de fuentes
  se ordena con Alt+↑/↓; la propuesta de fragmentos se recorre con flechas (Intro: ver, Espacio: elegir); Material
  con Intro/Supr/tecla Menú; la barra del vídeo con flechas (1 s) y Re Pág/Av Pág (10 s). Las etiquetas tienen su
  atajo subrayado (Alt+letra).
- **Lectores de pantalla**: nombres y descripciones accesibles en ranuras, listas, tablas y controles; modo lector
  del terminal (Ver → Modo lector de pantalla en el terminal), que expone el texto de Claude Code.
- **Temas**: oscuro, claro y **alto contraste** (Ver → Tema). Contraste comprobado en las pruebas: ≥ 4,5:1 (WCAG AA)
  en todos y ≥ 7:1 en alto contraste. El foco del teclado siempre se ve (borde de color).
- **Tamaño de letra** de toda la app y del terminal: Ctrl+= / Ctrl+- / Ctrl+0 (del 85 % al 200 %).
- La ventana recuerda tamaño, distribución, sección, tema, letra y modo lector (`CUTLY_AJUSTES` usa otro perfil de
  preferencias, p. ej. para pruebas).

## Cómo funciona (y por qué así)

- **Claude Code no se reimplementa: se ejecuta.** `terminal/pty.py` lanza `claude` en un pseudo-terminal REAL
  (ConPTY en Windows; pty en macOS y Linux) y `terminal/widget.py` lo muestra con **xterm.js** (el emulador del terminal
  de VS Code) dentro de un `QWebEngineView`, conectados por `QWebChannel`. Misma identificación, memoria, `CLAUDE.md`,
  permisos, comandos y tareas que en cualquier terminal.
- **Los flujos son las skills** (`.claude/skills/<nombre>/SKILL.md`): cada sección escribe `/<nombre> <archivos>` en la
  sesión; el menú Flujos las lista todas (una skill nueva aparece sola: `flujos.py`).
- **Claude y la app se hablan por ficheros** (los contratos de `nucleo/`): Claude escribe, la sección lo muestra al
  instante; el usuario corrige o elige, y la sección se lo dice a Claude en la sesión.
- **La app no duplica lógica**: lee con `nucleo/` y `vm/`; lo que modifica algo lo hacen las CLIs del repo o Claude.
- **Eficiencia**: un único vigía de carpetas que agrupa ráfagas de cambios y sincroniza el material una sola vez;
  miniaturas en caché; todo lo lento (ffprobe, VBoxManage, copias) en segundo plano; la VM solo se consulta a menudo
  cuando su sección está a la vista.

## Estructura del código

```
estudio/
├── __main__.py        arranque (python -m estudio)
├── ventana.py         barra lateral + sección + panel de Claude, menús, avisos, preferencias
├── apariencia.py      temas (colores con contraste comprobado), hoja de estilo única, escala de letra
├── servicios.py       el vigía central (material, carpetas, novedades)
├── hooks/             estado_claude.py: lo que los hooks de Claude Code cuentan a la app
├── flujos.py          las skills como flujos
├── entorno.py         rutas del repo, tareas en segundo plano, CLIs con salida en directo
├── miniaturas.py      fotogramas de muestra en caché
├── terminal/          pseudo-terminal + xterm.js (Claude Code)
└── paneles/           una sección por archivo + comun.py (contrato y piezas), ranura.py, reproductor.py
```

**Añadir una sección** (una cosa nueva que hacer): un `QWidget` en `estudio/paneles/` que cumpla el contrato de
`paneles/comun.py` (`TITULO`, `pedir`, `traer_soltados` y, si le sirven, `al_material`, `al_carpetas`,
`al_novedad`), con su sitio para soltar (`Ranura` para un archivo, una lista como `ListaFuentes` para varios), una
acción principal (`primario(...)`) y su skill en `.claude/skills/`. Se añade a la lista de `ventana.py`. Un papel
nuevo de material va en `ROLES` de `nucleo/material.py`. Nada de colores sueltos: marcas en el widget y
`apariencia.py`.

## Medido al construirla

| Hecho | Consecuencia |
|---|---|
| ConPTY pregunta al arrancar "¿qué terminal eres?" (`ESC[c`) y no muestra nada hasta que se le contesta | xterm.js contesta solo; en las pruebas sin interfaz se contesta a mano |
| Una página local no puede cargar `qrc:///qtwebchannel/qwebchannel.js` | `widget.py` lo lee de los recursos de Qt y lo inserta |
| Soltar un vídeo sobre el terminal llevaría la página a ese fichero (el terminal desaparecería) | la página no navega tras cargar; soltar pega la ruta en la sesión |
| El Short de pantalla lleva una pista de audio muda: salía como "cara" | `material.describir` mide el pico: por debajo de −60 dB es mudo |
| Soltar dos veces el mismo vídeo lo duplicaba; usar tu cara como fuente de un Short manual le cambiaba el papel | `material.ya_esta`; la lista de fuentes no pisa un papel fijado |
| El botón principal del tema oscuro (blanco sobre azul claro) daba 3,7:1 | acento más oscuro: 5,2:1 (la prueba de contraste lo vigila) |
| Las columnas de las tablas se cortaban al subir la letra | columnas que se ajustan solas al contenido |
| Un vídeo aparece en disco en cuanto se empieza a escribir | el vigía lo anuncia cuando deja de crecer |
| Lo que se escribía mientras Claude arrancaba se perdía; entre enviar y el hook "trabajando" pasa un instante | estado "arrancando" y "trabajando" marcado al enviar: todo va a la cola |
| Al cerrar la app, la transcripción que Claude había lanzado siguió viva y escribió sus ficheros | cerrar termina el árbol de procesos (taskkill /T en Windows, el grupo del pty en el resto) |
| Abierta desde otra sesión de Claude Code, la de la app heredaba sus variables ("Transcript saving is off") | el terminal no las pasa |

Las pruebas de la app (`pruebas/test_estudio.py`, `pruebas/test_material.py`) no abren ninguna sesión de Claude Code.
