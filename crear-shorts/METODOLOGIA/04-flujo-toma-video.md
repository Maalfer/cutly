# 04 — Flujo de toma de video (protocolo completo)

> Protocolo para la VM (`00-empezar-aqui-vm.md`). Las fases, el pacing y la toma única "sin tocar" valen en cualquier SO.
> Desde cutly estudio: botón/skill `/grabar-demo`; la sección VM enseña la pantalla del invitado en directo.

## El modelo de trabajo

```
USUARIO: "haz X en video" 
   → AGENTE: monta escenario + anuncia 
   → AGENTE: rec start (VirtualBox graba en el anfitrión; el usuario no toca nada)
   → AGENTE: ejecuta la secuencia completa con pacing cinematográfico
   → AGENTE: "CORTEN" + mapa de edición
   → USUARIO: edita, pone cara/voz
```

## Fases de una toma perfecta

### FASE 0 — Preparación (sin grabación)
1. Crear TODOS los archivos (páginas, payloads, servidores, decoys)
2. **Probar el pipeline end-to-end** con un test que no ensucie la toma
   (borrar logs/loot del test antes de la toma real)
3. Cerrar lo que estorbe y construir el escenario: cada ventana en su sitio y tamaño (`place`/`maximize`), la
   importante delante.
4. **Comprobar el escenario antes de grabar:** `vm_control.py windows` (qué ventanas hay, dónde y de qué tamaño) y
   **mirar la captura** (`shot`, o la sección VM): que nada quede enterrado, cortado por el borde ni tapado por una
   notificación, y que todo lo que debe verse se vea.

### FASE 1 — El anuncio (crítico)
```
"⚠️ TOMA ÚNICA — NO TOQUES LA VENTANA DE LA VM HASTA QUE TE DIGA CORTEN (~15s)"
```
**Por qué:** un clic del usuario dentro de la VM a mitad de toma le roba el foco al guion (y la guarda de foco
para el tecleo). Anunciar la duración reduce la tentación.

### FASE 2 — La secuencia continua
Un script con todos los pasos, cada uno con su verificación, bajo un registro de toma:

```bash
vm_control.py take start clip-01 && vm_control.py rec start     # registro + grabación de VirtualBox en el anfitrión
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
el nº de pasos. Se pasa tal cual a la edición (`editor/shorts/short_desde_toma.py`; contrato: `nucleo/toma.py`).

## Reglas de pacing (cine, no teatro)

0. **Entrada HUMANA siempre (regla nº 0 del vídeo):** el texto que aparece de golpe y el cursor que
   salta al botón delatan que es una máquina. Mientras se graba:
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

## Grabación

- Por defecto `rec start` usa la grabación nativa de VirtualBox en el anfitrión (cursor incluido, sin SSH). `rec start --guest` es la alternativa con ffmpeg dentro de la VM. OBS ya no hace falta.
- Verificar ANTES de la toma que la grabación está activa (`rec start` falla si no arranca)
- La toma es reproducible: si no se grabó, se rehace (todo el flujo es re-ejecutable)
