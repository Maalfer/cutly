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
2. **Control sin SSH** (para cuando no haya SSH, p. ej. invitado Windows): separar `vm_control.py` en
   cerebro + backend intercambiable (SSH+xdotool actual → `VBoxManage guestcontrol` → API de VirtualBox).
   La GRABACIÓN ya no depende de SSH; el CONTROL (ratón/teclado) todavía sí.
3. `suspend`/`resume`: medir tiempos y si las apps quedan bien al reanudar.
4. Fichas de más apps de Kali (Wireshark, Metasploit, sqlmap…) en `METODOLOGIA/09-conducir-apps-kali.md`
   tras su primera sesión de reconocimiento con cada una.
5. Arquitectura multiagente (`crear-shorts/ARQUITECTURA.md` §4): diseñada, sin implementar como Workflow
   todavía — pendiente de que el usuario confirme que quiere ejecutarla así.
6. Windows como invitado, Wayland.
7. **Transcripción con la GPU AMD (RX 590):** faster-whisper solo usa CUDA, así que hoy va por CPU (~1,7× tiempo real
   con turbo). Probar whisper.cpp compilado con Vulkan y medirlo como en `editor/BENCHMARK-WHISPER.md`.

## Referencia rápida
- Herramienta de control: `crear-shorts/herramientas/vm_control.py`.
- Generar el Short: `editor/scripts/short_desde_toma.py TOMA --titulo Titulo-Con-Gancho`.
- Juntar el Short con la cara y la voz del usuario: `editor/METODOLOGIA-FUSION-CARA.md`.
- Transcribir: `editor/scripts/transcribir.py` (large-v3-turbo + VAD; por qué: `editor/BENCHMARK-WHISPER.md`).
- Demos de referencia (copiar su estructura para una nueva): `crear-shorts/DEMO-IDOR/`, `crear-shorts/DEMO-SSHOLE/`.
- Fallos ya resueltos y por qué: `crear-shorts/METODOLOGIA/09-conducir-apps-kali.md`.
