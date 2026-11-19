# Qué modelo Whisper usar: medido, no supuesto

> Pregunta: ¿hace falta el modelo que más recursos consume (`large-v3`) para transcribir bien, o hay uno que dé
> el mismo resultado gastando menos? Respuesta medida (2026-11-19): **`large-v3-turbo` por defecto**. En nuestro
> audio fue el doble de rápido, gastó un 40 % menos de RAM y se equivocó menos. `large-v3` queda como segunda
> opinión para tramos dudosos. Script: `scripts/transcribir.py`.

## Cómo se midió
- **Audio:** `crudo/cara.mp4`, 202 s de narración real del usuario (español, micro de escritorio, ruido de ventilador
  de fondo, tomas repetidas, términos técnicos: SSH, 22, `pass`, netcat, 4444, `id`, reverse shell, Kali).
- **Referencia:** transcripción corregida a mano, contrastada con lo que se oye y se ve en pantalla.
- **Misma configuración para todos:** faster-whisper 1.2.1 / CTranslate2 4.9, CPU int8, `beam_size=5`,
  `vad_filter=True`, `condition_on_previous_text=False`, `word_timestamps=True`.
- **Máquina:** AMD Ryzen 6 núcleos / 12 hilos (Zen+), 16 GB de RAM, Radeon RX 590 (sin CUDA, así que todo en CPU).
- **Timestamps:** se comparan contra los límites de palabra medidos con la energía del audio a 10 ms, que es la
  verdad física que se usó para cortar.

## Resultados

| Modelo | Tiempo (202 s de audio) | Velocidad | RAM pico | Disco | WER | Términos técnicos | Error de timestamp (peor caso) |
|---|---|---|---|---|---|---|---|
| **large-v3-turbo** | **121 s** | 1,67× tiempo real | **2,0 GB** | 1,6 GB | **1,2 %** | 9/12 | **±130 ms** |
| large-v3 | 235 s | 0,86× | 3,5 GB | 2,9 GB | 2,4 % | 9/12 | **−510 ms** ("Tal"), −280 ms ("pass") |
| medium | 137 s | 1,48× | 1,9 GB | 1,5 GB | 3,6 % | 8/12 | +840 ms |
| small | 44 s | 4,6× | 0,8 GB | 0,5 GB | 8,3 % | 5/12 | ±110 ms, pero se come palabras |

Errores típicos de cada modelo:
- **large-v3:** "porto 22", "reversal", "máquina call", "a la la máquina", y **omitió el "Tal." en falso** del cierre
  (justo el tipo de toma fallida que hay que cortar).
- **large-v3-turbo:** "reversell", "máquina cal". Detectó el "Tal." en falso y escribió bien "puerto 22".
- **medium:** "una de las *modalidades*", "porto", "reversal de todo el servidor", timestamps muy desplazados.
- **small:** "*porto vendidos*", "comando *IDE*", "*riversale*", "variable *PAS*". No sirve para contenido técnico.

## Conclusiones

1. **El modelo más grande NO es el más preciso en la práctica.** `large-v3-turbo` (decodificador de 4 capas en vez
   de 32) iguala o mejora a `large-v3` en español claro y tarda la mitad. El sobrecoste de `large-v3` no compra
   precisión en este tipo de audio. Los datos públicos van en la misma línea: diferencias de ~1 punto de WER
   en idiomas con muchos datos, como el español, aunque no hay comparación directa publicada en español.
2. **`medium` y `small` no tienen sitio.** `medium` es más lento que turbo y peor. `small` destroza los términos
   técnicos. Se retira `medium` como respaldo: el respaldo ahora es turbo, y la segunda opinión es `large-v3`.
3. **Lo que de verdad evita errores no es el tamaño del modelo, sino la configuración:**
   - **VAD activado.** La pasada de `large-v3` sin VAD inventó "Gracias" y "Gracias por ver el vídeo" en los
     silencios y **se saltó ~30 s de narración real**. Con VAD, ningún modelo alucinó nada.
   - **Sin arrastre de contexto** (`condition_on_previous_text=False` en faster-whisper, `-mc 0` en whisper.cpp).
4. **Ningún modelo sirve para cortar a ciegas.** Los timestamps por palabra fallan entre 50 y 500 ms en algunas
   palabras, en todos los modelos. Ejemplo real: `large-v3` situó el final de "pass" 280 ms antes de tiempo y el
   primer render del Short se comió la palabra. Regla: **la transcripción localiza; el corte se afina con la
   energía del audio a 10 ms (rms + energía de alta frecuencia para sibilantes como la "s") y se verifica
   re-transcribiendo el empalme del vídeo final.**
5. **Las tomas en falso pueden desaparecer de la transcripción.** Una palabra suelta repetida ("Tal… Tal y como")
   a veces se funde con la frase siguiente: el segmento empieza antes de lo que dice su texto. Para encontrar
   tomas fallidas, cruza la transcripción con el mapa de energía. Un bloque de voz que ningún texto explica es
   sospechoso.

## Cuándo usar cada uno
- **Transcripción base** (directo entero, narración de un Short): `large-v3-turbo` + VAD.
- **Verificar un empalme** (ventana de pocos segundos): `large-v3-turbo`. Si sale ambiguo, repite esa ventana
  con `large-v3` y cruza resultados. Es más barato que pasar todo el archivo por `large-v3`.
- **Si cambia el material** (otro idioma con menos datos, audio muy ruidoso, varias voces superpuestas): repite
  esta medición con 2-3 minutos de ese material antes de cambiar el defecto. Turbo pierde más que large-v3 en
  idiomas con pocos datos, según los informes públicos.

## Margen pendiente: GPU AMD
La RX 590 no la usa faster-whisper (solo CUDA/NVIDIA). **whisper.cpp compilado con Vulkan** (`-DGGML_VULKAN=1`, ver
`../PORTABILIDAD.md`) sí puede usar GPUs AMD en Windows, y hay informes de aceleraciones grandes con
`ggml-large-v3-turbo.bin`. No está medido en esta máquina: si la transcripción se vuelve un cuello de botella,
es el siguiente paso (mismo modelo y misma precisión, menos tiempo).
