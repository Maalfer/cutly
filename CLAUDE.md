# cutly — instrucciones para agentes

## Regla de oro: TODO en la VM
Las demos de vídeo se ejecutan **dentro de una VM de VirtualBox** (Kali/Debian + X11), nunca en el anfitrión.
Tú actúas y te mueves; el usuario solo graba. Entrada humana siempre (tecleo y ratón realistas).

- Empieza por `crear-shorts/METODOLOGIA/00-empezar-aqui-vm.md`, `crear-shorts/ARQUITECTURA.md` (qué es el
  sistema) y `PENDIENTE.md` (estado real). Demo de terminal nueva: `METODOLOGIA/10-plantilla-demo-terminal.md`.
- La herramienta es `crear-shorts/herramientas/vm_control.py` (multiplataforma: Windows, macOS, Linux).
- Edición posterior: `editor/CLAUDE.md` y `editor/METODOLOGIA-SHORTS.md`. Si el usuario pasa el Short de pantalla + un
  vídeo con su cara y voz para juntarlos: `editor/METODOLOGIA-FUSION-CARA.md`. El Short sale solo con
  `editor/scripts/short_desde_toma.py` (banda negra superior FIJA de 648 px para la cara del usuario). La toma se graba con
  VirtualBox en el anfitrión (`rec start`), no con OBS ni dentro de la VM. La toma deja
  `editor/crudo/<toma>.mp4`, `.steps.jsonl` y `.mapa.md` para decidir los cortes.

## Límites (no negociables)
- No adivines contraseñas ni aceptes EULA/acuerdos por el usuario.
- No hagas snapshots ni clones de la VM `kali` (el usuario no los quiere). `suspend`/`resume` (savestate) sí está permitido.
- Solo contra laboratorios propios (`127.0.0.1`) o objetivos autorizados.
- Verifica cada acción con algo que pueda fallar (log del lab, OCR, plantilla); no informes éxitos sin comprobar.
- Nunca recrees `editor/videos-editados/_cortes.log` desde cero: solo APPEND.

## Anfitrión Windows
`VBoxManage` no está en el PATH: `vm_control.py` lo localiza solo. Instalación y rutas: `PORTABILIDAD.md`.
- **Sin MCP en ningún sitio.** Todo se controla por pantalla, ratón y teclado de la VM.
