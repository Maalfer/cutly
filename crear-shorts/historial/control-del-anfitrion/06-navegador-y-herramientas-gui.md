# 06 — Conducir el navegador y herramientas GUI (Burp Suite, etc.)

> **⚠️ Vigencia:** este documento nació controlando el anfitrión macOS. Los **principios y fallos** siguen
> vigentes; los **comandos** de los ejemplos (`cliclick`, `osascript`, `type_human`…) fueron sustituidos por
> `herramientas/vm_control.py` dentro de la VM. Punto de entrada: `00-empezar-aqui-vm.md`.
> Las referencias sueltas a "doc 01", "doc 02" o "doc 03" son a documentos YA RETIRADOS (control
> del anfitrión macOS): ignora el número, el principio que acompañan sigue siendo válido.

> **Entrada humana:** en los ejemplos, el texto se teclea con `type_human` y el cursor se mueve con
> `mover_humano`/`click_text` (ver doc 02, herramienta 9). Los atajos (`Cmd+T`, `Cmd+L`…) siguen
> siendo pulsaciones sueltas y no necesitan ritmo.
>
> Patrones concretos para las dos cosas que más aparecen en una demo de seguridad web: el
> **navegador** y una **herramienta GUI compleja** (aquí Burp Suite como ejemplo denso). Se apoya
> en el ciclo universal del doc 05. Comandos de ejemplo en macOS; equivalentes por sistema en
> `../../PORTABILIDAD.md` §2. Atajo de teclado: **`Cmd` en macOS = `Ctrl` en Windows/Linux**.

---

## 1. Navegador — el caballo de batalla

### 1.0 Perfil LIMPIO para grabar (importante para el vídeo y la privacidad)

`open -a "Google Chrome"` abre **tu perfil real**: sale tu nombre de cuenta ("Hola, …"), tus extensiones
(una abrió una pestaña "Upgraded - Wappalyzer" sola), tus marcadores, el autocompletado de tu historial… y
todo eso queda **grabado**. Para grabar usa un perfil desechable:

```bash
PROF=/tmp/chrome-demo-profile        # cualquier carpeta; se crea sola y se puede borrar después
open -na "Google Chrome" --args --user-data-dir="$PROF" --no-first-run --no-default-browser-check \
     --disable-extensions "http://127.0.0.1:8765/"
# -n abre una instancia NUEVA aparte de tu Chrome normal. Verificado: sin cuenta, sin extensiones, sin avisos.
# Al terminar: pkill -f chrome-demo-profile      (solo mata la instancia de la demo, no tu Chrome)
```
Un perfil nuevo tampoco tiene historial, así que no hay autocompletado de URLs viejas (ver 1.1).

### 1.1 Abrir e ir a una URL (teclado, más fiable que clic)

```bash
source crear-shorts/herramientas/mac-control.sh
type_url "Google Chrome" "127.0.0.1:8765/cuenta?id=1002" --wpm 45     # Cmd+L, teclea, Suprimir, Enter
wait_for "usuarioB" 10          # esperar a que cargue (texto que solo sale cargado)
```
**Por qué `type_url` y no teclear + Enter:** el navegador **autocompleta en línea con el historial**. Medido:
al teclear `127.0.0.1:8765/` Chrome lo completó a `…/cuenta?id=1002` (una URL visitada antes) y Enter
cargó **la página anterior en vez de la tecleada**; en el vídeo el espectador habría visto escribir una
cosa y cargar otra. La solución es pulsar **Suprimir (borrado hacia delante, `key code 117`)** antes de
Enter: quita el texto autocompletado si lo hay y no hace nada si no lo hay (un retroceso borraría una
letra real). Con perfil limpio (1.0) el problema casi no aparece, pero `type_url` lo cubre siempre.

Las URLs tecleadas con `type_human` llegan **íntegras** aunque se simulen errores (probado al 4 %).

### 1.2 Clicar un elemento de la página

> Usa `click_text "Texto" 1 c "Google Chrome"` (la app como 4.º argumento): busca solo en la ventana de esa
> app, la trae delante y mueve el cursor como una persona. Sin la app, clica la primera coincidencia de
> TODA la pantalla, que puede ser texto de otra ventana (error real, doc 07 nº 22).

```bash
screencapture -x /tmp/pag.png
~/Desktop/ctrl-kit/ocr /tmp/pag.png | grep -iF "Iniciar sesión"   # → [x,y WxH] físico
# centro lógico = (x + W/2)/escala , (y + H/2)/escala   (Retina = 2)
cliclick m:CX,CY; sleep 0.4; cliclick c:CX,CY               # mover despacio (se ve) y clicar
```

Sin texto (iconos): posición relativa a algo con texto, color (`find_button.py`), o DevTools.

### 1.3 Formularios y login

```bash
# Clic en el primer campo (o Tab para saltar entre campos), teclear, Tab, teclear, enviar:
cliclick c:CAMPO_USUARIO_X,Y
type_human "Google Chrome" "usuarioA" --wpm 40
osascript -e 'tell application "System Events" to keystroke tab'
type_human "Google Chrome" "Passw0rd!" --wpm 40 --typos 0   # sin errores simulados en contraseñas
osascript -e 'tell application "System Events" to keystroke return'      # enviar
wait_for "Bienvenido usuarioA" 10                                        # VERIFICAR que entró
```

### 1.4 Leer el estado de la página

- **Texto visible:** OCR de la zona relevante.
- **La URL exacta (p. ej. para ver el `id`):** foco a la barra, seleccionar todo, copiar, leer:
  ```bash
  osascript -e 'tell application "System Events" to keystroke "l" using {command down}'  # Cmd+L
  osascript -e 'tell application "System Events" to keystroke "c" using {command down}'  # Cmd+C
  pbpaste          # → https://lab.local/cuenta?id=1001   (ya puedes razonar sobre el id)
  osascript -e 'tell application "System Events" to key code 53'                         # Esc (deseleccionar)
  ```

### 1.5 Pestañas, scroll, DevTools

| Acción | Atajo (Cmd=macOS / Ctrl=Win·Linux) |
|---|---|
| Nueva pestaña / cerrarla | `Cmd+T` / `Cmd+W` |
| Cambiar de pestaña | `Ctrl+Tab` (o `Cmd+Alt+→/←`) o clic en la pestaña |
| Scroll | `Espacio` / `Shift+Espacio`, `AvPág/RePág`, o rueda con `cliclick` |
| Recargar | `Cmd+R` |
| DevTools | `F12` o `Cmd+Alt+I` (macOS) / `Ctrl+Shift+I` |

---

## 2. Herramienta GUI compleja — patrón general con Burp Suite

Toda herramienta GUI (Burp, Wireshark, un cliente de BBDD, un IDE…) se conduce con el **mismo
ciclo**: esperar a que cargue → localizar por OCR/atajo → clic/teclear → verificar. Burp es el
ejemplo más denso porque arranca lento y tiene muchas pestañas; si dominas Burp, dominas el resto.

### 2.1 Lanzar Burp y pasar el arranque (VERIFICADO con Burp Suite Community 2026.10)

```bash
source crear-shorts/herramientas/mac-control.sh
open -a "Burp Suite"                          # el .app se llama "Burp Suite", no "...Community Edition"
wait_for "Temporary project" 60               # ~5-10 s; timeout generoso por si tarda más
click_text "Next" 1 c "Burp Suite"           # proyecto temporal en memoria (Community no tiene proyectos en disco)
wait_for "Use Burp defaults" 20
click_text "Start" 1 c "Burp Suite"           # "Start Burp"
wait_for "Dashboard" 60                       # Burp listo
place_window_ax "Burp Suite" 0 29 1280 700    # agrandar para que se lea (sin permisos extra)
```
Cosas que se descubrieron probándolo:
- **El proceso se llama `JavaApplicationStub`** para System Events, pero `Burp Suite` para `winlist`. Las
  funciones de `mac-control.sh` resuelven la app **por PID**, así que usa siempre el nombre de `winlist`.
- Al arrancar hay una ventana transparente de ~1824×1020 y luego el diálogo de 985×640: `click_text` con
  la app busca en la ventana superior; si el clic cae donde no debe, `wait_for` te lo dirá (el paso
  siguiente no aparece). **Verifica siempre el resultado de cada clic.**
- Para salir: `Cmd+Q` abre "*are you sure you want to exit?*" → `click_text "Yes" 1 c "Burp Suite"`.

### 2.2 Proxy: interceptar tráfico del navegador

Dos vías (elige una):

- **Navegador embebido de Burp** (más simple para grabar): Proxy → Intercept → "Open browser".
- **Tu navegador vía proxy** `127.0.0.1:8080`: configúralo (o una extensión tipo FoxyProxy) y,
  para HTTPS, instala el **certificado CA de Burp** (http://burp → CA Certificate). En un lab es
  aceptable; **solo en entornos autorizados**.

```bash
# Ir a la pestaña Proxy y activar Intercept (localizar las pestañas por OCR):
screencapture -x /tmp/b.png; ~/Desktop/ctrl-kit/ocr /tmp/b.png | grep -iE "Proxy|Intercept"
# clic en "Proxy" → clic en "Intercept is off" para ponerlo "on" (verificar que cambió el texto)
```

### 2.3 Flujo Repeater: escribir la petición → enviar → cambiar el id → reenviar (VERIFICADO)

Ejecutado de punta a punta contra el lab local (`DEMO-IDOR/lab_idor.py`), todo con entrada humana:

```bash
click_text "Repeater" 1 c "Burp Suite"                       # pestaña Repeater (viene con un editor vacío)
clic_humano 233 350                                          # clic dentro del editor de la petición
type_human "Burp Suite" $'GET /cuenta?id=1001 HTTP/1.1\nHost: 127.0.0.1:8765\n\n' --wpm 45
#   -> Swing recibe bien Unicode y saltos de línea; el Inspector ya interpreta "1 parámetro, 2 cabeceras"
clic_humano 1223 169                                         # el lápiz de "Target: Not specified" NO tiene texto: clic por coordenada
#   -> diálogo "Configure target details": Burp RELLENA host y puerto desde la cabecera Host; solo pulsar:
click_text "OK" 1 c "Burp Suite"
click_text "Send" 1 c "Burp Suite"
wait_for "usuarioA" 12                                       # respuesta 1: Cuenta de usuarioA

# --- el cambio IDOR: seleccionar solo el valor y teclear encima ---
select_text "id=1001" 1 "Burp Suite" "1001"                  # doble clic VERIFICADO (copia y comprueba)
type_human "Burp Suite" "1002" --wpm 30 --typos 0            # reemplaza la selección
click_text "Send" 1 c "Burp Suite"
wait_for "usuarioB" 12                                       # respuesta 2: Cuenta de usuarioB  -> IDOR
```
**Por qué `select_text` y no un doble clic a pelo:** en Burp (Java) un doble clic ciego fallaba **1 de
cada 3 veces de forma periódica** (no seleccionaba nada; Cmd+C copiaba la petición entera) aunque el punto
fuera exacto, el OCR leyera bien y se esperaran 4 s entre intentos: es un contador interno de la
aplicación. `select_text` copia lo seleccionado, lo compara con lo esperado y reintenta: 12 de 12.
Además apunta a un **trozo dentro de la palabra** (`"1001"` dentro de `/cuenta?id=1001`) por
proporción de caracteres, que es exacto en la fuente monoespaciada del editor.

> **Proxy/Intercept** (la variante "el navegador pasa por Burp") se describe en 2.2; el flujo de arriba
> es el equivalente directo sin depender del proxy y es el más estable para grabar.

### 2.4 Otras herramientas, mismo patrón

- **Terminal:** `do script` crea una ventana y ejecuta (doc 02/03); verifica la salida con OCR o
  leyendo el archivo que genere.
- **Editor/IDE:** abrir con `open -a`, `Cmd/Ctrl+O` para abrir archivo, teclear, `Cmd/Ctrl+S`.
- **Cualquier GUI:** si tiene atajo, úsalo; si no, OCR+clic; siempre espera a que cargue y verifica.

---

## 3. Que se vea BIEN en el vídeo (el usuario graba con OBS)

- **Ventanas grandes y texto legible.** Sube el zoom del navegador (`Cmd/Ctrl + +`) y la fuente de
  la terminal/Burp si el texto queda pequeño; el espectador lo verá en el móvil.
- **Cursor despacio y en trayecto** (movimiento "glided", doc 04): la cámara ve el cursor "pensar".
- **Pausas para leer** antes de cada acción clave (3-4 s en pantallas con texto denso).
- **Revela con un clic deliberado** ("y ahora miramos la respuesta…") en vez de saltos bruscos.
- **Un solo plano continuo**: el agente no corta; el usuario recorta después (doc 04). Entrega
  siempre el **mapa de edición** (tabla de momentos) al terminar.
