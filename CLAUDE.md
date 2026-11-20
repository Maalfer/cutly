# cutly — instrucciones para agentes

## Regla de oro: TODO en la VM
Las demos de vídeo se ejecutan **dentro de una VM de VirtualBox** (Kali/Debian + X11), nunca en el anfitrión.
Tú actúas y te mueves; el usuario solo graba. Entrada humana siempre (tecleo y ratón realistas).

- Empieza por `crear-shorts/METODOLOGIA/00-empezar-aqui-vm.md`, `crear-shorts/ARQUITECTURA.md` (qué es el
  sistema) y `PENDIENTE.md` (estado real). Demo de terminal nueva: `METODOLOGIA/10-plantilla-demo-terminal.md`.
- La herramienta es `crear-shorts/herramientas/vm_control.py` (multiplataforma: Windows, macOS, Linux).
- Edición posterior: índice en `editor/CLAUDE.md` (Shorts en `editor/shorts/`, directos 16:9 en `editor/directos/`). Si el usuario pasa el Short de pantalla + un
  vídeo con su cara y voz para juntarlos: `editor/shorts/METODOLOGIA-FUSION-CARA.md`. El Short sale solo con
  `editor/shorts/short_desde_toma.py` (banda negra superior FIJA de 760 px para la cara del usuario). La toma se graba con
  VirtualBox en el anfitrión (`rec start`), no con OBS ni dentro de la VM. La toma deja
  `editor/crudo/<toma>.mp4`, `.steps.jsonl` y `.mapa.md` para decidir los cortes.

## Interfaz y flujos
- Los flujos de trabajo son skills del proyecto (`.claude/skills/`: `/preparar-vm`, `/grabar-demo`,
  `/fusionar-cara-pantalla`, `/short-desde-grabacion`, `/subtitular-short`, `/directo-a-clips`). Cada una remite a su
  metodología.
- El usuario puede estar usándote dentro de **cutly estudio** (`estudio/ESTUDIO.md`): misma sesión, con una sección
  por cosa que hacer al lado. Cuando una skill pida su revisión (p. ej. los subtítulos), la hace en la sección que
  toca (se le abre sola cuando escribes el fichero) y te escribe en la sesión cuando termina.
- `.claude/settings.json` (proyecto): permite sin preguntar SOLO las herramientas del repo de los flujos (más
  ffmpeg/ffprobe y editar en `editor/crudo/` y `editor/videos-editados/`; `_cortes.log` siempre pregunta) y sus hooks
  le cuentan a cutly estudio si estás trabajando, esperando permiso o libre (`estudio/hooks/estado_claude.py`; fuera
  de la app no hacen nada). Si añades una herramienta a un flujo, añade su regla allí (lo comprueba una prueba).
- **El material ya no se coloca en carpetas:** el usuario ARRASTRA cada vídeo a su sitio en la interfaz (la ranura
  "Cara", "Pantalla", "Short a subtitular", "Directo"...). Vive en `editor/crudo/` y el papel de cada archivo está en
  `editor/crudo/material.json`. Para saber qué hay: `python editor/comun/material.py` (y `... ruta <papel>`). No
  supongas nombres fijos como `cara.mp4`.

## Objetivo final: el Short ideal
Cómo debe quedar TODO Short entregado (aprobado por el usuario, con especificación medible):
`editor/shorts/SHORT-IDEAL.md`. Antes de entregar uno: `python editor/shorts/verificar_short.py VIDEO.mp4` debe
cumplir la especificación. Estilo: lo más al grano posible, sin pausas, y con subtítulos karaoke revisados
(`editor/shorts/subtitular.py`, SHORT-IDEAL.md §6).

## Límites (no negociables)
- No adivines contraseñas ni aceptes EULA/acuerdos por el usuario.
- No hagas snapshots ni clones de la VM `kali` (el usuario no los quiere). `suspend`/`resume` (savestate) sí está permitido.
- Solo contra laboratorios propios (`127.0.0.1`) o objetivos autorizados.
- Verifica cada acción con algo que pueda fallar (log del lab, OCR, plantilla); no informes éxitos sin comprobar.
- Nunca recrees `editor/videos-editados/_cortes.log` desde cero: solo APPEND.

## Anfitrión Windows
`VBoxManage` no está en el PATH: `vm_control.py` lo localiza solo. Instalación y rutas: `PORTABILIDAD.md`.
- **Sin MCP en ningún sitio.** Todo se controla por pantalla, ratón y teclado de la VM.
