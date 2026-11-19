# Archivo: el enfoque de controlar el ordenador anfitrión

Estos documentos son de la primera etapa del proyecto, cuando la IA controlaba directamente el **ordenador anfitrión**
(el sistema donde se desarrolló entonces, con herramientas propias de ese sistema y OBS para grabar). Ese enfoque se
retiró: hoy todo ocurre **dentro de la VM**, igual en Windows, macOS o Linux, con
`crear-shorts/herramientas/vm_control.py`, y graba VirtualBox. Se guardan como registro de cómo se llegó hasta aquí.

Lo que sigue valiendo de ellos ya está en la metodología actual:
- bucle mirar → actuar → verificar, reconocimiento de una app nueva, reglas medidas y fichas por app:
  `crear-shorts/METODOLOGIA/09-conducir-apps-kali.md` (incluida su sección "Principios heredados");
- pacing y toma: `crear-shorts/METODOLOGIA/04-flujo-toma-video.md`; demo de terminal: `10-plantilla-demo-terminal.md`;
- la demo IDOR real: `crear-shorts/DEMO-IDOR/demo_idor.py`.

No sigas sus comandos: no existen en la VM. Las rutas y números de documento que citan son los de entonces.
