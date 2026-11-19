# Estado y pendiente (leer al retomar — corto a propósito)

> Para el PORQUÉ de cada decisión y el detalle sesión a sesión: `crear-shorts/historial/HISTORIAL-SESIONES.md`
> (archivo, no hace falta leerlo entero). Para la arquitectura del sistema: `crear-shorts/ARQUITECTURA.md`.
> Para empezar una demo nueva: `crear-shorts/METODOLOGIA/00-empezar-aqui-vm.md` →
> `METODOLOGIA/10-plantilla-demo-terminal.md` si es de terminal.

## Decisiones vigentes (no las repreguntes)
- Todas las demos se graban **dentro de la VM de VirtualBox** (Kali), nunca en el anfitrión. La IA actúa;
  el usuario solo graba su pantalla si quiere, pero no hace falta: `rec start` ya graba con VirtualBox.
- Sin copias ni snapshots de `kali`. `suspend`/`resume` (savestate) sí está permitido.
- Entrada humana siempre (tecleo y ratón realistas). Sin MCP en ningún sitio: solo pantalla/ratón/teclado.
- Ante dudas de credenciales, pagos o cuentas del usuario (Skool, DockerLabs...): preguntar, no adivinar.

## Pendiente (en este orden)
1. **Fiabilidad:** repetir una demo end-to-end 10-20 veces y medir (hoy: 1 ejecución limpia por demo).
2. **Instalar Tesseract en este anfitrión** (`winget install UB-Mannheim.TesseractOCR`): `vm_control.py doctor` lo
   marca como FALLA; sin él no hay `waitfor` ni `clicktext`. Lo demás de la integración con VirtualBox está medido
   en vivo (2026-11-19, doc 08 §1): canales ssh y guestcontrol, login, grabación a la resolución real, maximizar.
3. **cutly estudio** (`estudio/ESTUDIO.md`): siguiente sección, el plan de fusión como línea de tiempo (voz, cara,
   pantalla con miniaturas) editable; y xterm.js empaquetado en el repo para no depender de jsDelivr.
4. `suspend`/`resume`: medir tiempos y si las apps quedan bien al reanudar.
5. Fichas de más apps de Kali (Wireshark, Metasploit, sqlmap…) en `METODOLOGIA/09-conducir-apps-kali.md`
   tras su primera sesión de reconocimiento con cada una.
6. Arquitectura multiagente (`crear-shorts/ARQUITECTURA.md` §4): diseñada, sin implementar como Workflow
   todavía — pendiente de que el usuario confirme que quiere ejecutarla así.
7. Windows como invitado, Wayland.
8. **Transcripción con la GPU AMD (RX 590):** faster-whisper solo usa CUDA, así que hoy va por CPU (~1,7× tiempo real
   con turbo). Probar whisper.cpp compilado con Vulkan y medirlo como en `editor/comun/BENCHMARK-WHISPER.md`.

## Referencia rápida
- **Antes de una demo:** `python crear-shorts/herramientas/vm_control.py doctor` (dice qué falta y cómo arreglarlo);
  `vm_control.py start --login` arranca, inicia sesión con `VM_GUEST_PASSFILE` y espera al canal.
- Pruebas (pásalas antes de cada commit): `python -m unittest discover -s pruebas -t pruebas`.
- Estructura y dónde va cada cosa nueva: `README.md` ("Cómo crece el proyecto") y `editor/CLAUDE.md`.
- Herramienta de control: `crear-shorts/herramientas/vm_control.py`.
- Generar el Short: `editor/shorts/short_desde_toma.py TOMA --titulo Titulo-Con-Gancho`.
- Juntar el Short con la cara y la voz del usuario: `editor/shorts/METODOLOGIA-FUSION-CARA.md`.
- Subtítulos: `editor/shorts/subtitular.py preparar|quemar` (revisar el JSON entre medias).
- **Cómo debe quedar el Short final:** `editor/shorts/SHORT-IDEAL.md`; comprobarlo con `editor/shorts/verificar_short.py`.
- Transcribir: `editor/comun/transcribir.py` (large-v3-turbo + VAD; por qué: `editor/comun/BENCHMARK-WHISPER.md`).
- Demos de referencia (copiar su estructura para una nueva): `crear-shorts/DEMO-IDOR/`, `crear-shorts/DEMO-SSHOLE/`.
- Fallos ya resueltos y por qué: `crear-shorts/METODOLOGIA/09-conducir-apps-kali.md`.
