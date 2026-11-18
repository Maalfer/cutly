# 06 — Conducir el navegador y herramientas GUI (Burp Suite, etc.)

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

### 1.1 Abrir e ir a una URL (teclado, más fiable que clic)

```bash
open -a "Google Chrome" && wait_for "Nueva pestaña" 15   # wait_for: ver doc 05 §2.1
osascript -e 'tell application "Google Chrome" to activate'
# Nueva pestaña y foco a la barra de direcciones:
osascript -e 'tell application "System Events" to keystroke "t" using {command down}'   # Cmd+T
osascript -e 'tell application "System Events" to keystroke "l" using {command down}'   # Cmd+L (barra URL)
type_human "Google Chrome" "https://lab.local/cuenta" --wpm 45   # ritmo humano; NO keystroke (instantáneo)
osascript -e 'tell application "System Events" to keystroke return'
wait_for "Mi cuenta" 15      # esperar a que la página cargue (texto que solo sale cargada)
```

### 1.2 Clicar un elemento de la página

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

### 2.1 Lanzar Burp y pasar el arranque (es LENTO)

```bash
open -a "Burp Suite Community Edition"
wait_for "Temporary project" 60          # el arranque puede tardar 10-30 s: timeout GENEROSO
# "Next" (proyecto temporal) → "Use Burp defaults" → "Start Burp":
# localizar cada botón por OCR y clicar (están abajo a la derecha del diálogo):
screencapture -x /tmp/burp.png; ~/Desktop/ctrl-kit/ocr /tmp/burp.png | grep -iE "Next|Start"
# clic en Next ... wait_for "Use Burp defaults" ... clic en Start ... wait_for "Dashboard" 30
```

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

### 2.3 El flujo típico: interceptar → Repeater → modificar → reenviar

```
1. Intercept ON  → en el navegador, hacer la acción (cargar /cuenta?id=1001)
2. Burp captura la petición → clic derecho → "Send to Repeater"  (o Cmd/Ctrl+R)
3. Ir a la pestaña "Repeater" (OCR + clic)
4. Editar la petición (clic en el id, cambiar 1001 → 1002)
5. "Send" (botón, o Cmd/Ctrl+Espacio según versión) → leer la RESPUESTA (panel derecho) con OCR
6. Intercept OFF para que el navegador vuelva a fluir
```

Cada uno de esos pasos = ciclo del doc 05 (localizar por OCR/atajo, actuar, **verificar con OCR**
que la respuesta trae lo esperado). Para editar texto dentro de un campo de Burp: clic para situar
el cursor, `Cmd/Ctrl+A` si quieres reemplazar todo, teclear.

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
