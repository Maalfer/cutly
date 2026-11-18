# 04 — Flujo de toma de video (protocolo completo)

> **Independiente del sistema operativo.** Las fases, el pacing cinematográfico, la toma única
> "sin tocar" y la verificación post-toma valen igual en macOS, Windows y Linux. Solo los comandos
> concretos del ejemplo son de macOS; su equivalente está en `../../PORTABILIDAD.md` §2.

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
4. Verificar con screenshot+OCR que TODO está en su sitio

### FASE 1 — El anuncio (crítico)
```
"⚠️ TOMA ÚNICA — NO TOQUES EL MAC HASTA QUE TE DIGA CORTEN (~15s)"
```
**Por qué:** una interacción del usuario a mitad de toma rompe el z-order
(ver doc 03, lección 7). Anunciar duración reduce la tentación.

### FASE 2 — La secuencia continua
UN solo bloque de shell con todos los pasos y sus pausas:

```bash
# (ejemplo de la toma ClickFix v2 — 15 segundos totales)
sleep 4                                    # pausa: leer el señuelo
cliclick m:250,350; sleep 0.6              # cursor glided (visual)
cliclick m:420,550; sleep 0.6
cliclick m:639,684; sleep 0.8
cliclick c:639,684; sleep 1.5              # CLIC en COPIAR → verde
cliclick c:1100,300; sleep 1.5             # foco a la víctima
osascript ... keystroke "v" using {command down}   # ⌘V — la pared base64
sleep 3.5                                  # pausa dramática
osascript ... keystroke return             # ENTER — ejecuta el payload
sleep 6                                   # payload + exfiltración + flood del C2
cliclick c:150,400                        # REVEAL: foco al C2 con el botín
sleep 2.5
screencapture -x /tmp/take_final.png      # captura de verificación
```

### FASE 3 — Verificación post-toma
OCR de la captura final para confirmar que cada momento clave ocurrió:
- El comando pegado aparece en la ventana víctima
- El output del payload visible ("completada ✓")
- El C2 muestra el botín
**Si algo falló:** rehacer SOLO la fase fallida (el clipboard y los estados persisten).

### FASE 4 — El mapa de edición (entregable al usuario)
Tabla con cada momento, qué se ve y su duración — para que edite rápido:

| # | Momento | Qué se ve | Dura |
|---|---------|-----------|------|
| 1 | Señuelo | Página de amenazas | 4s |
| 2 | El clic | Botón rojo → verde | 4s |
| ... | ... | ... | ... |

## Reglas de pacing (cine, no teatro)

1. **Pauses de lectura:** 4s en pantallas con texto denso (el espectador lee)
2. **Cursor glided:** mover en 3-4 saltos hacia el objetivo, no teletransporte
3. **Pausa pre-Enter:** el momento antes de ejecutar el peligro = tensión máxima
4. **El "reveal" con clic:** traer el resultado al frente CON un clic deliberado
   ("veamos qué tiene el atacante...") — mucho más cinematográfico que ⌘Tab
5. **Un solo plano continuo:** nada de cortes del agente — el usuario corta al editar

## Grabación del usuario

- OBS oculto SIGUE grabando (ocultar ventana ≠ parar proceso)
- Verificar ANTES de la toma que la grabadora está activa
- La toma es reproducible: si no se grabó, se rehace (todo el flujo es re-ejecutable)
