# 04 — Flujo de toma de video (protocolo completo)

> Protocolo para la VM (`00-empezar-aqui-vm.md`). Las fases, el pacing y la toma única "sin tocar" valen en cualquier SO.
> Las referencias sueltas a "doc 03" son a un documento YA RETIRADO (control del anfitrión macOS): ignora
> el número, el gate anti-solape en sí sigue siendo un principio válido (hoy: `vm_control.py windows`).

## El modelo de trabajo

```
USUARIO: "haz X en video" 
   → AGENTE: monta escenario + anuncia 
   → USUARIO: graba (OBS/QuickTime) SIN TOCAR 
   → AGENTE: ejecuta la secuencia completa con pacing cinematográfico
   → AGENTE: "CORTEN" + mapa de edición
   → USUARIO: edita, pone cara/voz
```

## Fases de una toma perfecta

### FASE 0 — Preparación (sin grabación)
1. Crear TODOS los archivos (páginas, payloads, servidores, decoys)
2. **Probar el pipeline end-to-end** con un test que no ensucie la toma
   (borrar logs/loot del test antes de la toma real)
3. Ocultar apps estorbosas, construir el escenario (orden back-to-front)
4. **Pasar el gate anti-solape** (doc 03): `ventanas --only <apps del layout> --exit-code` → que
   ninguna quede enterrada, cortada por el borde ni tapada por una notificación. Y **mirar la captura** (visión): confirmar a ojo que todo lo que
   debe verse, se ve, y nada tapa lo importante.

### FASE 1 — El anuncio (crítico)
```
"⚠️ TOMA ÚNICA — NO TOQUES LA VENTANA DE LA VM HASTA QUE TE DIGA CORTEN (~15s)"
```
**Por qué:** una interacción del usuario a mitad de toma rompe el z-order
(ver doc 03, lección 7). Anunciar duración reduce la tentación.

### FASE 2 — La secuencia continua
Un script con todos los pasos, cada uno con su verificación, bajo un registro de toma:

```bash
vm_control.py take start clip-01 && vm_control.py rec start     # registro + ffmpeg dentro de la VM
vm_control.py mark "Señuelo"        && sleep 4                  # pausa: leer
vm_control.py clicktext "COPIAR"    && vm_control.py waitstill  # clic humano + esperar a que se pinte
vm_control.py mark "El payload"
vm_control.py type "comando" --in "Terminal" --wpm 40           # tecleo humano con guarda de foco
vm_control.py labcheck "POST /exfil"                            # verificación sin OCR
vm_control.py take end                                          # trae .mp4 y escribe .mapa.md
```

### FASE 3 — Verificación post-toma
`take end` imprime los pasos fallidos del registro (`ok:false`). Comprueba además con `waitfor`/captura final que cada
momento clave ocurrió. **Si algo falló:** rehacer SOLO la fase fallida (los estados persisten en la VM).

### FASE 4 — El mapa de edición (ya generado)
`editor/crudo/<toma>.mapa.md` se escribe solo: un bloque por `mark` con su rango en segundos del vídeo, su duración y
el nº de pasos. Se pasa tal cual a la edición (`editor/CLAUDE.md`).

## Reglas de pacing (cine, no teatro)

0. **Entrada HUMANA siempre (regla nº 0 del vídeo):** el texto que aparece de golpe y el cursor que
   salta al botón delatan que es una máquina. Mientras OBS graba:
   - **Teclear:** `vm_control.py type "texto" --in "Título"` (ritmo variable, pausas tras espacios/signos, algún error
     corregido con retroceso). **Nunca** pegar texto de golpe (es instantáneo).
   - **Mover/clicar:** `move X Y` / `clicktext PALABRA` (trayecto curvo, lento-
     rápido-lento, 0,5-1,8 s según distancia). **Nunca** teletransportar el cursor.
   - Velocidad: `--wpm 55` por defecto; **bájala (35-45)** para que se lea cada comando en un short.
1. **Pauses de lectura:** 4s en pantallas con texto denso (el espectador lee)
2. **Cursor glided:** `mover_humano` ya traza el trayecto; no hace falta trocearlo a mano
3. **Pausa pre-Enter:** el momento antes de ejecutar el peligro = tensión máxima
4. **El "reveal" con clic:** traer el resultado al frente CON un clic deliberado
   ("veamos qué tiene el atacante...") — mucho más cinematográfico que ⌘Tab
5. **Un solo plano continuo:** nada de cortes del agente — el usuario corta al editar

## Grabación del usuario

- Por defecto graba la VM (`rec start`, ffmpeg dentro del invitado, cursor incluido). Con OBS sobre la ventana de VirtualBox, comprueba antes que sale el cursor.
- Verificar ANTES de la toma que la grabación está activa (`rec start` falla si ffmpeg no arranca)
- La toma es reproducible: si no se grabó, se rehace (todo el flujo es re-ejecutable)
