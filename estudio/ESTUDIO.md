# cutly estudio — la interfaz de escritorio

Una ventana (PySide6, igual en Windows, macOS y Linux) con **el Claude Code instalado dentro, con su interfaz
completa**, y alrededor una **sección por cosa que quieres hacer** con tus vídeos. El material no se coloca en
carpetas: **se suelta en la sección de lo que quieres hacer**.

```
┌ Sesión · Ver · Flujos · Ayuda ─────────────────────────────────────────────────────────────────────┐
│ Directo → clips    │ ┌ Cara ─────────────┐ ┌ Pantalla ──────────┐  │ Claude Code                  │
│ Cara + pantalla  ◀ │ │ suelta aquí       │ │ suelta aquí        │  │ (el de `claude`, de verdad:  │
│ Grabación → Short  │ └───────────────────┘ └────────────────────┘  │  misma sesión, permisos,     │
│ Subtítulos  ●      │ Título: [...........]   [Fusionar con Claude] │  comandos /…; soltar un      │
│ Resultados         │                                               │  archivo aquí pega su ruta)  │
│ Material · VM      │                                               │  F12 lo oculta / muestra     │
└ sesión · material · VM ─────────────────────────── [Ir a Subtítulos] ──────────────────────────────┘
```

## Arrancar

```bash
pip install -r estudio/requisitos.txt        # PySide6 + pseudo-terminal (pywinpty en Windows, ptyprocess en el resto)
python -m estudio                            # sesión nueva de Claude Code en el repo
python -m estudio --continuar                # retoma la última conversación (claude --continue)
```

Requisitos: Claude Code instalado y con sesión iniciada (`claude` en el PATH; si no está, el panel lo explica) y
conexión a internet (Claude Code la necesita igual; xterm.js se carga de jsDelivr con versión fijada). Para iniciar
sesión en la VM desde la sección VM: `VM_GUEST_PASSFILE` en el entorno.

## Las secciones: dónde se suelta cada cosa

| Sección | Qué sueltas | Qué hace Claude (skill) |
|---|---|---|
| **Directo → clips** | el directo (o pegas un enlace) | propone fragmentos (`/directo-a-clips`); aparecen en una tabla con el directo al lado: ver cada uno, elegir y "Cortar los elegidos" (`<directo>.candidatos.json`, `nucleo/candidatos.py`) |
| **Cara + pantalla** | tu cara y el Short de pantalla (en sus ranuras, o los dos juntos: cada uno va al suyo) | `/fusionar-cara-pantalla <cara> <pantalla> [Título]` |
| **Grabación → Short** | grabaciones sueltas (sin registro de la VM) e intro/imágenes, en orden | `/short-desde-grabacion <fuentes…> [Título]` (plan JSON + `construir_short.py`) |
| **Subtítulos** | el Short montado | `/subtitular-short <short>`; los subtítulos aparecen solos para revisarlos con el vídeo al lado; "Revisado" se lo dice a Claude |
| **Resultados** | cualquier vídeo, para verificarlo | lo que Claude termina aparece solo: ver, verificar contra el Short ideal (solo verticales), subtitular, revisar sus subtítulos |
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

Las pruebas de la app (`pruebas/test_estudio.py`, `pruebas/test_material.py`) no abren ninguna sesión de Claude Code.
