# 10 — Plantilla para una demo de terminal "perfecta a la primera"

> Destilado de 10 iteraciones reales (`DEMO-SSHOLE/demo_sshole.py`, CVE ficticio "sshole") hasta que el
> usuario dio el Short por bueno. Síguelo **desde el principio** en la próxima demo para no repetir el
> mismo camino de prueba y error. Es la plantilla; copia `demo_sshole.py` como punto de partida real.

## 0. Antes de escribir una sola línea de guion

1. **Sube el tamaño de letra del terminal.** `ssh ... "sed -i 's/^fontSize=18/fontSize=24/' ~/.config/qterminal.org/qterminal.ini"`
   — una vez por VM, antes de la primera toma. Es la causa nº 1 de que un Short "se vea pequeño" y la
   única palanca segura (ver §3). No esperes a que el usuario lo señale: compruébalo tú con una captura
   de prueba antes de grabar nada.
2. **Prueba el flujo de ataque entero, sin grabar y sin GUI**, a base de `v.ssh(...)` sueltos en una
   consola Python, hasta tener los comandos EXACTOS que vas a teclear luego (IPs, flags, orden). Un
   guion escrito a ciegas cuesta 5-10 iteraciones; uno probado a mano cuesta 1-2.
3. Decide el **layout de ventanas** (p. ej. dos terminales en dos mitades de pantalla: atacante +
   listener) y resérvalo como constantes al principio del script (`ATK_RECT`, `LIS_RECT`, …).

## 1. Despliegue del objetivo: SIEMPRE en primer plano y síncrono

Si el laboratorio trae un script tipo `auto_deploy.sh` con un `while true; sleep 1` esperando Ctrl+C,
**no lo ejecutes en segundo plano por SSH** (con `nohup`, `setsid`, o cualquier variante): con `sudo` de
por medio se cuelga el canal SSH de forma indeterminista, a veces minutos, a veces para siempre — medido
varias veces, mismo comando exacto, resultados distintos.

En su lugar, **replica sus pasos reales a mano**, en primer plano y síncronos (nunca se han colgado):
```python
v.ssh(f"sudo docker rm -f {CONTAINER} >/dev/null 2>&1", check=False)
v.ssh(f"cd {LAB_DIR} && sudo docker load -i {TAR}", capture=True, timeout=60)
v.ssh(f"sudo docker run -d --name {CONTAINER} {IMAGEN}", capture=True, timeout=30)
ip = v.ssh(f"sudo docker inspect -f '{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}{{{{end}}}}' {CONTAINER}",
          capture=True, timeout=15)
```
Esto va ANTES de `take_start`/`rec_start`: el despliegue no se graba, es preparación (Fase 0).
`docker rm -f` solo borra el contenedor, no mata el script del laboratorio si lo lanzaste antes: añade
`pkill -9 -f auto_deploy.sh` (o el nombre que sea) antes de cada redeploy.

Si el host key del objetivo cambia de IP a IP reciclada: `ssh-keygen -f ~/.ssh/known_hosts -R '<ip>'`.

## 2. Ventanas: por ID, nunca por título

Dos terminales comparten el mismo título por defecto ("usuario@host: ~"). Usa:
```python
atacante = v.launch_terminal("Atacante")     # devuelve un ID de ventana ESTABLE
listener = v.launch_terminal("Listener")
v.place_id(atacante, 0, 39, 960, 973)         # mitad izquierda de 1920×1012
v.place_id(listener, 960, 39, 960, 973)       # mitad derecha
```
`type_in(wid, texto, ...)` exige que `wid` tenga el foco (guarda de foco por ID, no por título).

## 3. Encuadre del Short: las reglas que de verdad funcionan

1. **Foco por REGIÓN, siempre que se vaya a teclear en una terminal.** El ratón no se mueve mientras se
   teclea, así que un `focus` de un punto suelto no sabe hasta dónde llega el texto — se corta el borde
   derecho (medido: "22/tcp" salía como "cp"). Justo tras `activate_id(wid)` y antes de teclear:
   ```python
   def focus_rect(rect, why):
       x, y, w, h = rect
       v.focus(x + w // 2, y + h // 2, why, w=w, h=h)
   ```
   Esto da **letterbox de la ventana entera**, sin recortar nunca.
2. **"Se ve pequeño" se arregla con la fuente del terminal (§0), NO estrechando el recorte por
   comando.** Un recorte más estrecho (p. ej. 700 de 960 px) exige MEDIR con una captura que cada
   comando nuevo cabe, y se rompe en cuanto alguno es más largo de lo previsto. La fuente grande agranda
   TODO (nmap, comandos cortos, resultados largos) sin ese riesgo: lo que no cabe en una línea pasa a la
   siguiente, nunca se sale de la ventana.
3. **Que un comando importante no quede "enterrado"** bajo el resultado del paso anterior (p. ej. un
   `nmap` largo encima): `Ctrl+L` (limpia pantalla, instantáneo, no cuenta como tecleo) + `focus_rect`
   justo ANTES de teclear ese comando — sale solo, arriba del todo.
   ```python
   def clear_and_focus(rect, why):
       v.ssh("xdotool key ctrl+l"); time.sleep(0.3)
       focus_rect(rect, why)
   ```
4. **Nunca dejes un `focus` "de zoom"/estrecho activo antes de un comando LARGO.** Si una región angosta
   quedó fijada por el paso anterior y el siguiente comando es más ancho, vuelve explícitamente al rect
   completo con `focus_rect(RECT_COMPLETO, ...)` antes de teclear. Repasa el guion entero pensando "¿qué
   región está activa en este instante?" — no asumas que se resetea sola.
5. **Marca el foco también ANTES del primer `mark()`**, justo tras `rec_start()`: si no, los primeros
   segundos del vídeo usan el recorte por defecto (punto + 816 px) en vez de la región correcta.

## 4. Ritmo y verificación

- Tecleo 42-45 wpm, pausas de lectura 3-4 s tras resultados densos, 1,5 s antes de un paso "peligroso".
- **Un momento importante se queda en pantalla más tiempo del que parece necesario** (p. ej. un listener
  recién arrancado: 4 s, no 1,5 s) — pídelo tú mismo si el guion lo amerita, no esperes a que te lo
  pidan. Pecar de lento es gratis; un corte demasiado rápido no se arregla en edición.
- Cada paso con una verificación que PUEDA fallar (`waitfor`, `labcheck`-equivalente, nunca "informar"
  sin comprobar). `v.ssh()` lleva timeout: para un plan de tecleo largo (`play()`), el timeout ya es
  proporcional a su duración — no hace falta tocarlo a mano.
- VirtualBox NO deja cambiar resolución/fichero de grabación tras la primera vez habilitada en la
  sesión: `rec_start()` ya lo gestiona solo (fichero fijo reutilizado); no lo fuerces a mano.

## 5. Checklist final antes de dar un Short por bueno

- [ ] Fuente del terminal ya a 24pt (o mayor) antes de la primera toma.
- [ ] Cada terminal controlada por ID, no por título.
- [ ] Cada bloque de tecleo tiene su `focus_rect`/`clear_and_focus` explícito justo antes — repasado
  mentalmente de principio a fin, sin huecos ni regiones "heredadas" por error.
- [ ] Ningún comando largo teclea sobre una región estrecha.
- [ ] Momentos clave con pausa de lectura generosa, no la mínima que "funciona".
- [ ] Vídeo y Short verificados con capturas reales (varios instantes), no solo con los contadores de
  `short_desde_toma.py` (duración/banda OK no garantiza que el encuadre sea el correcto).
- [ ] Laboratorio limpiado (`docker rm -f` + matar el script de despliegue) fuera de la grabación.
