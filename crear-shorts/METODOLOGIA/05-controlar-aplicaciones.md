# 05 — Controlar CUALQUIER aplicación (no solo una demo)

> **⚠️ Vigencia:** este documento nació controlando el anfitrión macOS. Los **principios y fallos** siguen
> vigentes; los **comandos** de los ejemplos (`cliclick`, `osascript`, `type_human`…) fueron sustituidos por
> `herramientas/vm_control.py` dentro de la VM. Punto de entrada: `00-empezar-aqui-vm.md`.

> El objetivo real de esta herramienta: que un modelo de IA (Claude u otro) **controle el
> ordenador por completo** — cursor, teclado, abrir/cerrar apps, escribir en ellas — para montar
> **cualquier** demostración en vídeo mientras el usuario graba con OBS. La demo ClickFix es solo
> un ejemplo; este documento es el **patrón general** que sirve igual para un navegador, Burp
> Suite, una terminal, un editor, etc.
>
> **Multiplataforma:** los comandos de ejemplo son de macOS. El equivalente de cada uno (mover
> cursor, teclear, abrir/mover/cerrar ventana, OCR, portapapeles) para Windows y Linux está en
> `../../PORTABILIDAD.md` §2. La *lógica* de este documento es idéntica en los tres sistemas.

---

## 1. El ciclo universal (vale para toda app)

Cada paso que da el agente es **siempre** este bucle de 4 tiempos. No lo rompas nunca:

```
   PERCIBIR  →  DECIDIR  →  ACTUAR  →  VERIFICAR
   (OCR /       (¿dónde     (clic,     (otra captura:
    captura /    clico?      teclear,   ¿pasó lo
    enum.        ¿qué        atajo,     esperado?
    ventanas)    tecleo?)    abrir)      si no → reintenta)
```

**Regla de oro (heredada de todo el repo): NUNCA asumas que una acción funcionó — VERIFÍCALA**
antes del siguiente paso. En una demo de varias apps, un solo paso no verificado arruina la toma.

---

## 2. Ciclo de vida de una aplicación

### 2.1 Abrir y ESPERAR a que esté lista (lo más importante)

El error #1 en demos reales: **actuar antes de que la app haya cargado**. Abrir no es
instantáneo (un navegador tarda ~1-2 s; Burp Suite **10-30 s**). Nunca pongas un `sleep` fijo
"a ojo": **espera activamente** hasta ver en pantalla una señal de que ya está lista.

```bash
# Abrir (macOS; ver PORTABILIDAD §2 para Windows/Linux):
open -a "Google Chrome"        # o Safari, "Burp Suite Community Edition", Terminal, etc.

# Patrón WAIT-FOR: bucle que captura + OCR hasta ver el texto esperado, con timeout.
wait_for() {   # uso: wait_for "texto que debe aparecer" [segundos_max]
  local needle="$1" max="${2:-20}" t=0
  while [ $t -lt $max ]; do
    screencapture -x /tmp/_wait.png
    if ~/Desktop/ctrl-kit/ocr /tmp/_wait.png | grep -qiF "$needle"; then return 0; fi
    sleep 1; t=$((t+1))
  done
  echo "TIMEOUT esperando: $needle" >&2; return 1
}

open -a "Google Chrome" && wait_for "Nueva pestaña" 15   # ya está lista para teclear la URL
```

Alternativa sin OCR: esperar a que la **ventana exista** (enumeración de ventanas, doc 03).

### 2.2 Enfocar la ventana correcta (por nombre/ID, jamás "front")

Antes de teclear, asegúrate de que el foco está donde crees (doc 03, lección 3 y 7). Un teclazo
en la app equivocada (p. ej. en el TUI del propio agente) arruina la toma.

```bash
# Activar una app por nombre:
osascript -e 'tell application "Google Chrome" to activate'
# Verificar quién tiene el foco AHORA:
osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'
# → debe decir "Google Chrome" antes de empezar a teclear.
```

### 2.3 Cerrar al terminar

```bash
osascript -e 'tell application "Burp Suite Community Edition" to quit'   # o Cmd+Q sobre la app enfocada
# Apps sin "quit" limpio: cerrar ventana con Cmd+W, o pkill del proceso si procede.
```

---

## 3. Cómo decidir DÓNDE actuar

1. **Teclado antes que ratón, siempre que exista atajo.** Un atajo es 100% fiable; un clic por
   coordenada puede fallar si la app se movió. Ejemplos: barra de URL (`Cmd/Ctrl+L`), nueva
   pestaña (`Cmd/Ctrl+T`), enviar a Repeater en Burp (`Cmd/Ctrl+R`), menús por teclado.
2. **Clic localizado por OCR, PALABRA a palabra:** `click_text "Guardar"` (de `mac-control.sh`) usa
   `ocr --words`, ignora tildes/mayúsculas y calcula la escala Retina real. **No clones el centro de
   la caja de una LÍNEA**: es la mitad de la frase, no la palabra (medido: solo acertaba la palabra
   del medio). Patrón completo en doc 02, herramienta 1.
3. **Elementos sin texto** (iconos): (a) posición relativa conocida respecto a algo con texto,
   (b) análisis de color/forma (`find_button.py`, doc 02), o (c) si todo falla, posición fija
   medida una vez con una captura.
4. **Leer el estado de la app** para decidir: OCR de la zona relevante; para leer la URL o un
   valor, selecciónalo y cópialo (`Cmd/Ctrl+C`) y lee el portapapeles con `pbpaste`.

---

## 4. Coordinar VARIAS apps en una misma demo

Una demo realista usa 2-3 apps a la vez (navegador + Burp + terminal). Claves:

- **Layout fijo y pensado para la cámara.** Coloca cada app en una posición estable (doc 03) y
  no la muevas durante la toma. Deja "franjas" visibles para cambiar el foco con un clic.
- **Cambiar de app de forma visible:** un clic en la franja de la otra ventana, o `Cmd+Tab`
  (macOS) / `Alt+Tab` (Win/Linux). El clic deliberado queda más cinematográfico ("ahora vamos a
  Burp…").
- **Verifica el foco tras CADA cambio** (sección 2.2) antes de teclear. Es el fallo más caro.
- **Un orden z claro:** decide qué app va delante en cada momento y constrúyelo back-to-front
  (doc 03, lección 4).

---

## 5. Sincronización: esperar bien es media demo

| Situación | Cómo esperar (no uses sleeps fijos a ciegas) |
|---|---|
| Una app arranca | `wait_for "<texto de su UI lista>"` (sección 2.1) |
| Una página web carga | `wait_for "<texto que solo aparece cargada>"` |
| Una herramienta lenta (Burp) | timeout largo (30-60 s) + señal concreta del splash/proyecto |
| Una petición/respuesta llega | `wait_for "<campo de la respuesta>"` o esperar el cambio en pantalla |
| Un comando de terminal termina | `wait_for "<prompt>"` o esperar su salida con OCR |

Los `sleep` cortos (0.3-1.5 s) **sí** se usan, pero para **pacing cinematográfico** (que el
espectador lea, tensión pre-acción), no como sustituto de verificar que algo cargó.

---

## 6. Robustez: qué hacer cuando algo falla a mitad de toma

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El clic no acierta | la app se movió / coordenada vieja | recapturar + OCR + recalcular el centro; preferir atajo de teclado |
| No aparece el texto esperado | aún no cargó / OCR falló esa palabra | subir el timeout; buscar otra palabra ancla de la misma pantalla |
| Tecleé y no pasó nada | foco en otra ventana | verificar frontmost (2.2), reactivar app, repetir solo ese paso |
| La app no abre | nombre/ruta mal, o permiso | verificar nombre exacto (`ls /Applications`), permisos (doc 01 / PORTABILIDAD §2) |
| Se contaminó el input del agente | el usuario tocó el Mac / z-order roto | limpiar sin Enter (`Cmd+A` → Delete), reponer foco, continuar |

**Reintenta solo el paso que falló** — el estado de las demás apps suele persistir, no rehagas
toda la toma.

---

## 7. Checklist antes de grabar una demo de varias apps

- [ ] Todas las apps necesarias **instaladas y probadas** (end-to-end) antes de grabar.
- [ ] Layout fijo decidido; cada ventana en su sitio; franjas de foco visibles.
- [ ] **Gate anti-solape pasado** (doc 03): `ventanas --only ... --exit-code` en verde (nada
      enterrado, cortado ni con overlay) **y** confirmado mirando la captura (visión).
- [ ] Datos/entorno de laboratorio listos (nada real sin autorización — ver los ejemplos DEMO-*).
- [ ] `wait_for` definido para cada arranque/carga; nada de sleeps fijos a ciegas.
- [ ] Anuncio "NO TOQUES EL MAC HASTA CORTEN" y OBS confirmado grabando (doc 04).
- [ ] Mapa de edición preparado para entregar al usuario al terminar (doc 04, fase 4).
