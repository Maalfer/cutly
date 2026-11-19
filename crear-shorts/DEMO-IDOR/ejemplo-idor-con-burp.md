# Ejemplo completo — Demo de IDOR en vídeo (navegador + Burp Suite)

> Ejemplo de referencia (GUI/navegador; para terminal ver `DEMO-SSHOLE/`). Muestra cómo el agente conduce
> **varias apps** —navegador y Burp Suite— para explicar en vídeo una vulnerabilidad **IDOR**
> (Insecure Direct Object Reference). La grabación la hace VirtualBox en el anfitrión (`vm_control.py rec
> start`), no OBS — ver `crear-shorts/ARQUITECTURA.md`.
>
> Usa los patrones de `METODOLOGIA/05-controlar-aplicaciones.md` (ciclo universal, wait-for,
> multi-app) y `METODOLOGIA/06-navegador-y-herramientas-gui.md` (navegador + Burp). Todo se ejecuta en la VM con
> `vm_control.py` (`../METODOLOGIA/00-empezar-aqui-vm.md`).

---

## 0. Marco ÉTICO (imprescindible)

Esta demo es **educativa y 100% controlada**, igual que la de ClickFix:

- Se ejecuta contra un **laboratorio vulnerable a propósito** o un **objetivo autorizado**
  (un lab local hecho para el vídeo, o un entorno tipo PortSwigger Web Security Academy / una
  máquina de CTF / una app propia de pruebas). **Nunca contra un sitio real sin permiso.**
- Los "usuarios" y sus datos son **ficticios**, creados para la grabación.
- Objetivo: enseñar qué es un IDOR y cómo se detecta/explica, no atacar a nadie.

> Si no hay lab, el agente puede **montar uno mínimo** (igual que en ClickFix se montó el
> `c2_server.py`): una web local con un endpoint `/cuenta?id=N` que devuelve los datos del
> usuario N **sin comprobar** que la sesión sea la de ese usuario. Ese es el fallo IDOR a enseñar.

---

## 1. Qué es IDOR (para el guion del vídeo)

Una app expone un identificador directo de un objeto (`id=1001`) y **no comprueba que el usuario
tenga permiso** sobre ese objeto. Cambiando el `id` accedes a datos de otra persona. Es de los
fallos más comunes y fáciles de entender — ideal para un short.

**Escenario de ejemplo:** `https://lab.local` con login. Al entrar como *usuarioA* y abrir "Mi
cuenta", la petición es `GET /cuenta?id=1001`. Si cambiamos a `id=1002`, salen los datos de
*usuarioB*. Eso es el IDOR.

---

## 2. Preparación (FASE 0 — sin grabar)

1. **Lab levantado** y probado (el endpoint vulnerable responde). Dos cuentas ficticias:
   usuarioA (id 1001) y usuarioB (id 1002), con datos distintos y reconocibles.
2. **Apps listas:** navegador + Burp Suite instalados y abiertos una vez para aceptar diálogos
   iniciales (así en la toma Burp arranca más rápido).
3. **Layout fijo** pensado para la cámara (ejemplo 1280×832 lógico):

```
┌───────────────────────────────┬───────────────────────────┐
│   NAVEGADOR (izquierda)        │   BURP SUITE (derecha)    │
│   {0,40 → 760,790}             │   {770,40 → 1280,790}     │
│   la víctima navega aquí       │   intercepta y Repeater   │
└───────────────────────────────┴───────────────────────────┘
        clic aquí = foco navegador     clic aquí = foco Burp
```

4. **Probar el flujo end-to-end** una vez (sin grabar) y **resetear** el estado (logout, cerrar
   pestañas de Repeater) antes de la toma real.

---

## 2b. Lab listo y flujo YA PROBADO

El lab existe: en la VM, `python3 ~/lab/lab_idor.py >/tmp/lab.log &` (solo `127.0.0.1:8765`; `prepare` lo lanza). Imprime una línea por petición, que `vm_control.py labcheck "GET /cuenta?id=1002"` usa para verificar sin OCR.
El acto 2 (Burp: escribir la petición, enviar, cambiar `1001`→`1002`, reenviar) está **verificado de
punta a punta** con Burp Suite Community 2026.10 y entrada humana: ver
`METODOLOGIA/06-navegador-y-herramientas-gui.md`, secciones 1.0 (perfil limpio de Chrome), 1.1
(`type_url`) y 2.3 (flujo Repeater con `select_text`). Resultado medido: respuesta 1 `Cuenta de
usuarioA`, respuesta 2 `Cuenta de usuarioB`.

## 3. La toma (FASES 1-3 — grabando, una secuencia continua)

**Anuncio:** `"⚠️ TOMA — NO TOQUES LA VM HASTA 'CORTEN' (~30-40s)"` y confirmar que OBS graba
(doc 04). Luego el agente ejecuta, verificando cada paso (doc 05 §1). Guion:

```text
# --- Acto 1: la víctima ve SUS datos (legítimo) ---
1. Foco navegador → ir a https://lab.local → login usuarioA / Passw0rd!
   wait_for "Bienvenido usuarioA"
2. Clic en "Mi cuenta" → se ve la ficha de usuarioA.  (pausa 3s para leer)
3. Mostrar el id: Cmd+L, Cmd+C, pbpaste → la URL es /cuenta?id=1001   (señalar el id)

# --- Acto 2: Burp intercepta y manipula ---
4. Clic en la franja derecha → foco Burp.  Proxy → Intercept ON.
5. Foco navegador → recargar "Mi cuenta" (Cmd+R).
6. Foco Burp → aparece la petición GET /cuenta?id=1001 → Send to Repeater (Cmd/Ctrl+R).
7. Pestaña Repeater → clic en el "1001" → cambiarlo a "1002".   (pausa dramática 2s)
8. Send → leer la RESPUESTA: ahora salen los datos de usuarioB.   ← IDOR CONFIRMADO
   wait_for "usuarioB"   (verificación objetiva de que funcionó)

# --- Acto 3 (opcional, muy visual): lo mismo SIN Burp ---
9. Intercept OFF. Foco navegador → en la barra, cambiar id=1001 por id=1002 → Enter.
   Se ve la cuenta de usuarioB directamente en el navegador. (el IDOR "para todos los públicos")

# --- Cierre ---
10. Captura final de verificación.  "CORTEN."
```

Cada paso = ciclo del doc 05 (localizar por OCR/atajo → actuar → **verificar**). **Todo el tecleo y el
movimiento del cursor con entrada humana** (`type_human`, `mover_humano`, `click_text`; doc 04, regla 0). Los `wait_for`
y las pausas de lectura marcan el pacing; el movimiento del cursor, "glided" (doc 04).

---

## 4. Mapa de edición (entregable al usuario)

| # | Momento | Qué se ve | Dura aprox. |
|---|---------|-----------|-------------|
| 1 | Login legítimo | usuarioA entra en su cuenta | 4s |
| 2 | El identificador | la URL `/cuenta?id=1001` resaltada | 3s |
| 3 | Burp intercepta | la petición capturada en Proxy | 3s |
| 4 | A Repeater | enviar y cambiar `1001`→`1002` | 4s |
| 5 | El robo | la respuesta muestra datos de usuarioB | 4s |
| 6 | Sin Burp | cambiar el id en la barra del navegador | 4s |
| 7 | Cierre | resumen "esto es un IDOR" | 3s |

> Para un **Short vertical**, este material se edita con `editor/shorts/METODOLOGIA-SHORTS.md`: recortes
> verticales de la zona que importa (barra de URL, panel de Repeater, respuesta), banda superior
> para la cara, y **paneo** para leer una URL o una respuesta larga a tamaño completo.

---

## 5. Verificación post-toma (FASE 3)

OCR de la captura final para confirmar los momentos clave:
- La respuesta de Repeater con `id=1002` contiene datos de **usuarioB** (no de usuarioA).
- La barra del navegador en el acto 3 muestra `id=1002` con la cuenta de usuarioB.
Si algún acto falló, **rehacer solo ese acto** (el login y el estado persisten).

---

## 6. Limpieza (FASE 4)

- Cerrar Burp y las pestañas de Repeater; parar el lab (`pkill -f lab_idor.py`); logout en el navegador.
- Borrar datos de prueba generados. Dejar la VM como estaba.
- Patrón real de referencia: el bloque final de `demo_idor.py` (limpieza fuera de la grabación, igual que
  `demo_sshole.py` hace `docker rm -f` tras `take_end()`).

---

## 7. Cómo generalizar esto a OTRA vulnerabilidad

El esqueleto es reutilizable para casi cualquier demo web (XSS, SQLi, CSRF, SSRF, upload…):

```
Preparar lab/autorizado  →  Acto 1: comportamiento legítimo  →  Acto 2: la manipulación
(con la herramienta: Burp, navegador, terminal)  →  Acto 3: la prueba del impacto  →  Cierre + limpieza
```

Cambia la herramienta y el paso de "manipulación" según el fallo; el **método de control**
(abrir apps, esperar, localizar, actuar, verificar, multi-app) es siempre el de los docs 05 y 06.
