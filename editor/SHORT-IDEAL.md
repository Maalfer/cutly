# El Short ideal: el objetivo final de todo el sistema

> **Referencia aprobada por el usuario (2026-11-19): "este es el ideal de cómo quiero que queden los shorts al final".**
> - Vídeo: `videos-editados/short_Entrar-Por-SSH-Sin-Saber-La-Contrasena_editado.mp4` (73,2 s; no está en git), y su
>   versión FINAL con subtítulos `…_editado_subtitulado.mp4`. Subtítulos copiados del `ideal.mp4` del usuario (§6).
> - Se generó con un plan como `plantillas/fusion_plan.ejemplo.json` + `scripts/fusionar_cara_pantalla.py`. El plan, los
>   vídeos y el registro de cortes (`_cortes.log`) son material local de ese vídeo y no se versionan.
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
5. fusionar_cara_pantalla.py                      → Short montado (aprieta pausas, -14 LUFS, fundido)
6. subtitular.py preparar → REVISAR texto → quemar → Short FINAL con subtítulos karaoke (§6)
7. verificar_short.py                             → cumple la especificación → entregar
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
| Subtítulos | caja de subtítulo presente en ≥ 85 % de los fotogramas (`--sin-subtitulos` para pasos intermedios) | 98 % |

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

## 6. Subtítulos (estilo del `ideal.mp4` del usuario, medido)

El usuario hizo su ideal con subtítulos automáticos de un editor (parece CapCut). Se midieron píxel a píxel y fotograma
a fotograma, y `scripts/subtitular.py` los reproduce: la caja sale en la misma posición al píxel (filas 619-725) y con
la misma letra, el mismo color y el mismo comportamiento.

| Elemento | Valor medido en el ideal |
|---|---|
| Caja | negra opaca (0,0,0), 107 px de alto, radio 16, margen lateral 20 px, ancho según el texto, centrada en x=540 |
| Posición | filas 619-725 (centro 672): **sobre la unión cara/pantalla** (28 px sobre la cara, 78 sobre la pantalla) |
| Letra | Inter Bold ~52 px (la más parecida de 6 candidatas comparadas); en el repo: `editor/fuentes/Inter.ttf` (OFL) |
| Karaoke | palabra ya dicha en BLANCO (255), palabra por decir en GRIS (80); cambia al empezar a decirla (±50 ms) |
| Bloques | 1-5 palabras, ≤ ~24 caracteres, una sola línea; corte tras . ? !; ~1 s en pantalla (0,6-1,9 s) |
| Aparición | el bloque aparece con su primera palabra y se queda hasta que empieza el siguiente |
| Texto | bien escrito: mayúsculas, comas, puntos, tildes y términos técnicos (SSH, ID, Netcat, Kali, reverse shell) |

**Alcance: siempre el vídeo ENTERO.** Subtitular o transcribir no recorta nada: se hace de principio a fin, llamada
final incluida ("Si te gustan estas cosas, comenta…"). En el `ideal.mp4` faltaba esa llamada porque el usuario la
quitó en esa exportación, cosa que hace solo a veces y por decisión propia. No es una regla: no la quites salvo que
te lo pida.

**Cómo se hacen:**
```bash
python editor/scripts/subtitular.py preparar editor/videos-editados/short_<Titulo>_editado.mp4
#   -> transcribe en modo --subtitulos y escribe short_<Titulo>_editado.subtitulos.json + lo imprime
#   REVISA los bloques: tildes ("cómo" interrogativo), términos técnicos, nombres. Corrige "texto" en el JSON.
python editor/scripts/subtitular.py quemar editor/videos-editados/short_<Titulo>_editado.mp4
#   -> short_<Titulo>_editado_subtitulado.mp4 (entregable final)
```

**Lo que se aprendió haciéndolos:**
- **El texto, mejor que el del editor automático:** CapCut escribió "una reverse shell *desde otro* servidor" donde se
  dice "*dentro del* servidor". Nosotros partimos de Whisper + glosario + revisión, así que no tiene que pasar.
- **Whisper puntúa mal con VAD**, porque corta en segmentos cortos: salía "comando Veo la respuesta", "Netcat De esta
  forma". Arreglo: `transcribir.py --subtitulos` (texto de contexto puntuado con los términos técnicos + contexto
  encadenado). El resultado sale puntuado y con "Netcat", "Kali", "reverse shell" e "ID" bien escritos. Solo sobre
  el Short FINAL: encadenar contexto en una grabación con silencios provoca alucinaciones.
- **`editor/glosario.json`** recoge las correcciones fijas de términos (por frase: "cal" solo es "Kali" detrás de
  "máquina"). Cada error nuevo que veas al revisar se añade ahí.
- **Se dibuja con Pillow** (`pip install pillow`) y se superpone con ffmpeg: el `drawtext`/libass de ffmpeg se
  cuelga en Windows por fontconfig.
- **Revisión obligatoria antes de quemar:** un subtítulo mal escrito no se puede arreglar después sin rehacer el vídeo.

## 7. Errores ya cometidos (no repetir)
| Error | Consecuencia | Regla |
|---|---|---|
| Dejar pausas "para respirar" y una espera de 3,6 s tras el Enter | el usuario tuvo que re-editarlo: 90,5 → 73,4 s | el script aprieta por defecto; no lo desactives |
| Cortar con el timestamp de Whisper | se comió "pass" (fallaba 280 ms) | afinar con `analizar_fusion.py energia` (rms + alta frecuencia) |
| Pasar tiempos del vídeo final al original sin sumar un desfase | se comió "lo" de "Lo interesante" | re-transcribe el resultado y compáralo con el plan, palabra a palabra |
| Fiarse del texto de Whisper en silencios | "Gracias por ver el vídeo" donde no había voz | VAD siempre; la energía manda |
| Volumen a mano | saturación | `lufs` en el plan (−14 por defecto) |
| Subtítulos del editor automático sin revisar | "desde otro servidor" en vez de "dentro del servidor" | `subtitular.py preparar` + revisión del JSON |
| Transcribir los subtítulos en modo normal (con VAD) | sin puntos y con mayúsculas a mitad de frase | `transcribir.py --subtitulos` (lo usa `subtitular.py`) |
