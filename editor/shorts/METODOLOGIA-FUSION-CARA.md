# Fusionar CARA + PANTALLA en un Short final

> **Cuándo aplica:** el usuario pasa DOS vídeos verticales 1080×1920 (normalmente arrastrándolos a las ranuras
> "Cara" y "Pantalla" de la sección «Cara + pantalla» de cutly estudio, que lanza `/fusionar-cara-pantalla <cara> <pantalla>`;
> si no vienen como argumentos: `python editor/comun/material.py ruta cara|pantalla`). Abajo, `cara.mp4` y
> `pantalla.mp4` son nombres de ejemplo:
> - **pantalla** (p. ej. `crudo/pantalla.mp4`): el Short mudo ya construido (normalmente con `short_desde_toma.py`),
>   con la banda negra de 648 px arriba;
> - **cara** (p. ej. `crudo/cara.mp4`): el usuario grabado arriba hablando, **con su voz**, y el resto en negro.
>   A veces, en algún tramo, la parte de abajo enseña su propia pantalla (p. ej. su PowerShell).
>
> **Encargo:** juntarlos para que la cara quede en el hueco negro y el Short quede "perfecto".
>
> Validado el 2026-11-19 con el Short de SSH (`short_Entrar-Por-SSH-Sin-Saber-La-Contrasena_editado.mp4`): el
> usuario lo dio por muy bueno. Detalle de cada corte en `videos-editados/_cortes.log`.

## La realidad de este material (no es un error, es así siempre)

1. **No cuadran las duraciones** (ejemplo: cara 202 s, pantalla 179,5 s). El usuario narra en directo mirando la
   pantalla, pero se equivoca y **repite frases**, hace pausas, y a veces se para a enseñar algo en su ordenador.
2. **Tomas repetidas**: la misma frase empezada 2-3 veces ("Pues aquí viene lo interesante…"), o solo la segunda
   mitad de una frase repetida, o una palabra en falso ("Tal… Tal y como se puede ver"). Hay que quitarlas todas.
3. **Insertos de su pantalla** debajo de la cara (ejemplo: PowerShell con `python -c "print('A'*300)"`): **el usuario
   los quiere en el vídeo**, son un añadido que lo mejora. En ese tramo se ve la parte de abajo de la grabación de
   cara en vez de la pantalla de la VM.
4. **La cara no mide 648 px**: en su grabación ocupaba 758 px. Se recorta (sin escalar, para no deformarla) para
   que la banda siga midiendo EXACTAMENTE 648.
5. **La pantalla es muda** y la voz está en el vídeo de cara.

## Principio: la VOZ manda, la pantalla se adapta

La narración no se acelera ni se deforma: se corta por frases buenas. Cada frase se pone sobre el momento de
pantalla del que habla, acelerando o ralentizando ese tramo de pantalla para que dure lo mismo que la frase:
- tecleo largo y silencioso → acelerado (×2-×3,5 se ve natural; el autocompletado ya enseña el comando entero);
- salida estática que se comenta largo → ralentizada (×0,75-×1) o alargada;
- cada **momento clave** cae justo cuando se nombra: "puerto 22" ↔ aparece `22/tcp open`; "ejecuto este comando"
  ↔ Enter; "ya estamos dentro" ↔ la shell remota.

## Estilo de corte del usuario: lo más al grano posible (medido)

El 2026-11-19 el usuario re-editó a mano el Short que hizo el agente (`ssh vuln.mp4`, 73,4 s, frente a los 90,5 s
del agente) "para que vaya lo más al grano posible". Se emparejó fotograma a fotograma con la versión del agente y se
midió la energía del audio en cada corte. Esto es lo que hace, y lo que hay que hacer por defecto:

| Qué | Versión del agente | Versión del usuario → **regla** |
|---|---|---|
| Pausas entre frases | 23 pausas ≥ 150 ms (mediana 380 ms) | **Solo 3, la mayor de 290 ms.** Corta toda pausa > ~0,25 s, también dentro de la misma frase ("habilitado. ✂ Pero yo no sé…", "el comando ✂ id") |
| Margen alrededor de la voz | — | **0-90 ms** (casi siempre 0-30 ms antes de arrancar, hasta ~60 ms tras acabar). Cortes pegados a la palabra |
| Silencio inicial | 0 ms tras recortar | **0 ms**: arranca en la primera sílaba ("Hoy…") |
| Pausa dramática tras "ejecuto este comando" (3,6 s) | se dejaba | **Fuera.** Del Enter se salta directamente a la conexión ("y vemos cómo de repente…") |
| Relleno de ambiente tras una frase (3,4 s) | se dejaba para respirar | **Fuera** |
| Conector titubeante ("Y… lo interesante") | se dejaba | **Fuera el "Y"** cuando va separado por un micro-hueco de la frase: "Lo interesante es que…" |
| Final | corte seco | **Corte justo tras la última palabra + fundido a negro de ~0,25 s** (imagen y audio) |
| Volumen | −19,4 LUFS | **≈ −14 LUFS** (lo subió +5 dB, ganancia uniforme, sin compresión) |
| Velocidad, encuadre, sincronía, inserto del PowerShell | — | **Intactos.** Solo cortó: cada trozo suyo coincide fotograma a fotograma con el del agente |

Consecuencia práctica: `fusionar_cara_pantalla.py` ya aplica todo esto por defecto. Aprieta pausas con la energía
del audio, quita los tramos sin voz, normaliza a −14 LUFS con techo de −1 dBTP (la versión a mano llegaba a
+1,9 dBTP, saturando un poco) y añade el fundido final. Al rehacer el Short así, salió de 73,2 s, con un 99,5 % de
texto igual al de la re-edición del usuario y la sincronía intacta. Lo único que sigue siendo decisión a mano es
quitar conectores titubeantes ("Y…") y elegir tomas.

## Flujo (en este orden)

### 1. Transcribir la voz (turbo + VAD)
```bash
python editor/comun/transcribir.py editor/crudo/cara.mp4        # -> crudo/cara_transcripcion.json/.srt/.txt
```
En CPU tarda ~1 min por cada 1,7 min de audio; lánzalo en segundo plano. Modelo y por qué: `editor/comun/BENCHMARK-WHISPER.md`.

### 2. Medirlo todo antes de cortar nada
```bash
python editor/shorts/analizar_fusion.py informe editor/crudo/cara.mp4 editor/crudo/pantalla.mp4 \
       --trans editor/crudo/cara_transcripcion.json                 # -> crudo/cara.fusion.md
```
El informe da:
- alto real de la banda de la cara y **tramos con su pantalla debajo** (insertos que se conservan);
- banda de la pantalla (≥ 648) y sus **eventos**: cambios grandes (Enter, salida, cambio de plano) y tramos quietos;
- **bloques de voz por energía** con su texto. La energía es la verdad: Whisper inventa "Gracias" en los silencios
  y a veces se traga un falso arranque;
- **avisos**: tomas repetidas (vale la última), segunda mitad repetida (empalmar), ruidos cortos (chasquidos).

Completa el mapa de pantalla con hojas de contacto cada 1-3 s en las zonas clave (qué comando hay en pantalla en
cada tramo). Así se llegó a esta tabla en el caso real:

| Pantalla (s) | Qué pasa |
|---|---|
| 0-20,5 | tecleo de `nmap` |
| 25,0 | resultado (22/tcp) |
| 31,3-46 | `PASS=$(python3 …)` |
| 46-87,4 | tecleo `sshpass … id` |
| 87,5 | salida `uid=1000(alice)` |
| 92,8-102,7 | listener `nc -lvnp 4444` |
| 102,7-157 | tecleo del comando final, Enter ~156,6 |
| 163,6 | conexión en el listener |

### 3. Decidir el guion de voz
Por cada bloque: ✅ se queda, ❌ toma fallida, ✂️ parte. Reglas:
- De varias tomas de la misma frase, **la última buena**, salvo que una anterior diga algo que la última no repite.
- Si repitió solo la **segunda mitad**: primera toma hasta justo antes de esa mitad + la repetición.
- Fuera: falsos arranques ("Tal."), chasquidos y **conectores titubeantes** separados por un micro-hueco
  ("Y… lo interesante" → "Lo interesante"). Localiza el hueco con `editor/comun/energia.py` y empieza el tramo justo antes de la
  palabra buena.
- **Sin pausas dramáticas ni de respiro:** el usuario las quita todas (ver tabla de arriba). No hace falta
  recortarlas a mano en el plan: los tramos pueden ir holgados, porque el script aprieta las pausas solo.
- El gancho empieza en la primera sílaba.

### 4. Afinar cada corte a 10 ms
Los timestamps de Whisper fallan entre 50 y 500 ms. Por cada corte:
```bash
python editor/comun/energia.py editor/crudo/cara.mp4 85.0 86.2
```
Corta en el valle entre palabras. **Las sibilantes ("pass") tienen rms bajo pero `hf` alto**: la palabra acaba
donde cae el `hf`, no el rms. Error real: cortar en 85,233 s se comió "pass" (acababa en 85,60 s).
Evita cortar dentro de un chasquido o una respiración.

### 5. Escribir el plan y construir
`crudo/fusion_plan.json` (local, no se versiona; parte de la plantilla `editor/shorts/plantillas/fusion_plan.ejemplo.json`):
un tramo por trozo de voz, con lo que se ve debajo.
```json
{"cara": "editor/crudo/cara.mp4", "pantalla": "editor/crudo/pantalla.mp4",
 "salida": "editor/videos-editados/short_<Titulo-Con-Gancho>_editado.mp4",
 "padtop": 648, "cara_alto": 758, "cara_y": 20,
 "tramos": [
  {"a0": 0.75,  "a1": 5.6,   "abajo": "pant", "p0": 0.0,  "p1": 22.5, "nota": "gancho; tecleo acelerado"},
  {"a0": 69.15, "a1": 75.133,"abajo": "cara", "nota": "su PowerShell"},
  {"a0": 75.133,"a1": 77.3,  "abajo": "pant", "p0": 31.6, "p1": 35.85}
 ]}
```
- `a0/a1`: trozo de la grabación de cara (voz + cara). `abajo: "pant"` + `p0/p1`: tramo de pantalla que se
  re-temporiza a la duración del trozo. `abajo: "cara"`: se ve la parte de abajo de la grabación de cara (inserto).
- `cara_alto`: alto medido de la cara; `cara_y`: desde qué fila se recortan los 648 px. Elígelo mirando fotogramas
  de varios instantes: el pelo no debe tocar el borde; sobra quitar sudadera abajo antes que cabeza arriba (en el
  caso real, `cara_y=20`: 20 px de fondo arriba y 90 de sudadera abajo).
- Dos tramos seguidos con `a1 == a0` del siguiente = audio continuo (solo cambia lo de abajo, sin fundido).
- Opciones con su valor por defecto (el estilo del usuario; solo hace falta escribirlas para cambiarlas):
  `"apretar": {"pausa_max": 0.25, "margen_antes": 0.04, "margen_despues": 0.06}` (o `false` para no apretar),
  `"lufs": -14` (o `null` para no tocar el volumen) y `"fundido_final": 0.25`.
  Apretar divide cada tramo por sus pausas medidas en el audio de la cara (rms > −38 dB o alta frecuencia > −42 dB,
  para no comerse una "s" final) y elimina los tramos sin voz. La pantalla de cada trozo sale del mismo mapeo del
  tramo, así que lo que se nombra sigue cayendo sobre su momento.

```bash
python editor/shorts/fusionar_cara_pantalla.py editor/crudo/fusion_plan.json
```
Un único render desde los originales (sin recodificar dos veces). Tiempos redondeados a fotogramas de 1/60 s para
que audio y vídeo de cada tramo duren exactamente lo mismo (sin deriva). Micro-fundido de 15 ms solo donde el audio
salta. Imprime la tabla final (tramo → instante en el Short) para la verificación.

### 6. Subtítulos
```bash
python editor/shorts/subtitular.py preparar editor/videos-editados/short_<Titulo>_editado.mp4   # revisa el JSON
python editor/shorts/subtitular.py quemar   editor/videos-editados/short_<Titulo>_editado.mp4
```
Estilo y reglas: `editor/shorts/SHORT-IDEAL.md` §6. El entregable es `short_<Titulo>_editado_subtitulado.mp4`.

### 7. Verificar (obligatorio, con algo que pueda fallar)
Primero, la especificación medible del Short ideal (formato, banda de la cara, subtítulos, fundido, arranque,
pausas > 0,4 s, final y volumen); todo eso lo mide el verificador, no hace falta repetirlo a mano:
```bash
python editor/shorts/verificar_short.py editor/videos-editados/short_<Titulo>_editado.mp4 --sin-subtitulos   # tras el paso 5
python editor/shorts/verificar_short.py editor/videos-editados/short_<Titulo>_editado_subtitulado.mp4         # entregable
```
Después, lo que el verificador no puede saber por sí solo:
- [ ] **Duración** del resultado = la que imprime el script (vídeo y audio iguales).
- [ ] **Cada empalme de voz**: re-transcribe ±3,5 s alrededor de cada corte del vídeo FINAL. Ni palabras cortadas
      ni repetidas ni tomas fallidas.
- [ ] **Cada punto de sincronía**: un fotograma en el instante en que se nombra cada momento clave. Lo que se dice
      debe estar en pantalla.
- [ ] **Ninguna palabra comida** por apretar: compara la transcripción del resultado con la del plan (un
      conector quitado a propósito sí; una palabra de contenido, nunca).
- [ ] Entrada APPEND en `videos-editados/_cortes.log` con todos los tramos (voz, pantalla, velocidad, qué se descartó).

## Resultado del caso real (referencia)
- Cara 202,3 s + pantalla 179,5 s → primera versión del agente de 90,5 s (13 tramos). El usuario la re-editó a
  73,4 s solo con cortes; con el estilo medido el script da 73,2 s y el mismo texto.
- Quitadas: 2 tomas fallidas, una segunda mitad repetida, un "Tal." en falso, un chasquido y ~70 s de silencios
  y tecleo sin narración.
- PowerShell del usuario conservado.
- Verificado: banda medida en todos los fotogramas, cada empalme re-transcrito y cada sincronía con fotograma.
