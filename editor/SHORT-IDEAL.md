# El Short ideal: el objetivo final de todo el sistema

> **Referencia aprobada por el usuario (2026-11-19): "este es el ideal de cómo quiero que queden los shorts al final".**
> - Vídeo: `videos-editados/short_Entrar-Por-SSH-Sin-Saber-La-Contrasena_editado.mp4` (73,2 s; no está en git).
> - Se reproduce exactamente con `crudo/fusion_plan.json` + `scripts/fusionar_cara_pantalla.py`. Cortes en
>   `videos-editados/_cortes.log`.
> - **Antes de entregar cualquier Short:** `python editor/scripts/verificar_short.py VIDEO.mp4` debe decir
>   "cumple la especificación". Si falla un punto, se arregla; no se entrega "casi".

## 1. Qué es, en una frase
Un vertical de ~1 minuto en el que el usuario explica de corrido, sin una sola pausa muerta, una técnica de
ciberseguridad. **Arriba se ve su cara y abajo la pantalla**, que enseña justo lo que está diciendo en cada
momento. Termina con una llamada a comentar y un fundido a negro.

## 2. Cómo se llega a él (cadena completa)
```
1. Demo en la VM (crear-shorts/)                 → toma .mp4 + .steps.jsonl
2. short_desde_toma.py                            → Short MUDO 1080x1920 con hueco negro de 648 px arriba
3. El usuario se graba narrando mirándolo         → cara.mp4 (cara arriba + su voz; con errores y repeticiones)
4. transcribir.py → analizar_fusion.py → plan     → decidir tomas y emparejar frases con pantalla
5. fusionar_cara_pantalla.py                      → Short final (aprieta pausas, -14 LUFS, fundido)
6. verificar_short.py                             → cumple la especificación → entregar
```
Procedimiento detallado de los pasos 4 y 5: `METODOLOGIA-FUSION-CARA.md`.

## 3. Especificación medible (lo que comprueba `verificar_short.py`)

| Punto | Ideal | Valor del Short de referencia |
|---|---|---|
| Formato | 1080×1920, 60 fps, H.264 + AAC 48 kHz | ✔ |
| Duración | lo justo para contar la técnica; referencia ~73 s, nunca de más de ~90 s | 73,2 s |
| Banda de la cara | filas 0-647 con la cara en TODOS los fotogramas; la pantalla empieza en la 648 | 0 fallos |
| Arranque | voz en los primeros ≤ 120 ms: el gancho empieza en la primera sílaba | 40 ms |
| Pausas | ninguna de > 400 ms; normalmente ≤ 250 ms | máx 170 ms |
| Final | ≤ 450 ms desde la última palabra hasta el final, con fundido a negro de ~0,25 s | 90 ms |
| Volumen | −14 LUFS (±1), pico ≤ −1 dBTP (se tolera −0,5 por el AAC) | −14,1 LUFS / −0,9 dBTP |

## 4. La estructura narrativa del ideal (73 s)

| s | Bloque | Qué se dice | Qué se ve abajo |
|---|---|---|---|
| 0-3 | **Gancho** | "Hoy vas a conocer una de las vulnerabilidades más ridículas, pero a su vez más peligrosas." | se teclea el nmap (acelerado) |
| 3-10 | Contexto | "puerto 22 abierto… SSH habilitado… pero yo no sé la contraseña" | resultado de nmap: `22/tcp open` justo al decir "22" |
| 10-16 | El truco | "puedo generar una cadena de texto bastante grande, **como puede ser esta**" | **inserto: su PowerShell** con `print('A'*300)` |
| 16-30 | Preparación | "me la guardo en la variable pass… si pongo esa cadena… voy a poder entrar" | `PASS=$(…)` y el tecleo de `sshpass` |
| 31-37 | Prueba | "ejecutando el comando id… veo la respuesta" | `uid=1000(alice)` |
| 37-45 | Escalada | "con netcat escuchando por el 4444… ejecutar un comando malicioso" | el listener |
| 45-60 | Ataque | "el mismo comando pero… reverse shell… **ejecuto este comando**" | tecleo del comando; Enter justo al decirlo |
| 60-67 | Resultado | "y vemos cómo de repente… ya estamos dentro… con total libertad" | conexión y shell remota |
| 67-73 | **Llamada a la acción** | "Si te gustan estas cosas, comenta la palabra SSH y te mando una guía…" | la shell; fundido a negro |

Patrón: **gancho → contexto → truco → prueba → ataque → resultado → llamada a comentar una palabra**. La narración
es del usuario (no se reescribe ni se resume); el trabajo es dejarla limpia y que la pantalla la acompañe.

## 5. Las reglas que lo hacen así

**Ritmo: lo más al grano posible**
- Cero pausas de respiro, de tensión o dramáticas. Cortes pegados a la voz: 40 ms antes de arrancar y 60 ms tras
  acabar (medido en la re-edición del usuario: 0-90 ms).
- Jump cuts de la cara: aceptados y normales, porque cada pausa quitada es un salto.
- Fuera tomas repetidas (vale la última buena), falsos arranques, chasquidos y conectores titubeantes ("Y… lo
  interesante" → "Lo interesante").
- La voz nunca se acelera ni se deforma. Lo que se acelera es la pantalla: tecleo ×2-×3,5 (hasta ×4,6 en el
  gancho); salidas que se comentan, ×0,8-×1,2.

**Imagen**
- Cara: recorte de 648 px de alto de su grabación, sin escalar. Se quita sudadera antes que cabeza (`cara_y`).
- Pantalla: terminal en letterbox completo, con la fuente a 24 pt (legible en el móvil); ningún texto cortado.
- Sincronía: cada momento clave aparece cuando se nombra ("22", "como puede ser esta", "comando id", "4444",
  "ejecuto este comando" = Enter, "ya estamos dentro").
- Insertos de la pantalla del usuario (su PowerShell, su navegador): se conservan; mejoran el vídeo.

**Audio**
- Solo la voz del usuario. Normalización lineal a −14 LUFS con techo de −1 dBTP: subir a mano satura (+1,9 dBTP
  en la re-edición manual).
- Micro-fundidos de 15 ms en cada empalme (sin clics) y fundido de 0,25 s al final.

## 6. Errores ya cometidos (no repetir)
| Error | Consecuencia | Regla |
|---|---|---|
| Dejar pausas "para respirar" y una espera de 3,6 s tras el Enter | el usuario tuvo que re-editarlo: 90,5 → 73,4 s | el script aprieta por defecto; no lo desactives |
| Cortar con el timestamp de Whisper | se comió "pass" (fallaba 280 ms) | afinar con `analizar_fusion.py energia` (rms + alta frecuencia) |
| Pasar tiempos del vídeo final al original sin sumar un desfase | se comió "lo" de "Lo interesante" | re-transcribe el resultado y compáralo con el plan, palabra a palabra |
| Fiarse del texto de Whisper en silencios | "Gracias por ver el vídeo" donde no había voz | VAD siempre; la energía manda |
| Volumen a mano | saturación | `lufs` en el plan (−14 por defecto) |
