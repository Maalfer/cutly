# editor/ — Fase 2: editar (índice)

Tres líneas de trabajo, cada una en su carpeta, sobre una librería común (`nucleo/`, en la raíz). **Antes de nada,
¿de dónde viene el vídeo?**

**El material lo aporta el usuario arrastrándolo en cutly estudio** (o con `python editor/comun/material.py anadir`):
vive en `editor/crudo/` con su papel (cara, pantalla, short, toma, directo…) en `material.json`. Mira primero
`python editor/comun/material.py`.

| Te pasan… | Línea | Empieza por |
|---|---|---|
| Una **toma de `crear-shorts/`** (hay `editor/crudo/<toma>.steps.jsonl`) | Short mudo automático | `python editor/shorts/short_desde_toma.py <toma> --titulo Titulo-Con-Gancho` |
| El **Short de pantalla** (mudo, banda negra arriba) **+ un vídeo con su cara y su voz** | Fusión → Short final | `editor/shorts/METODOLOGIA-FUSION-CARA.md` |
| Un **directo o grabación sin registro de pasos** que hay que convertir en **clips 16:9** | Directos | `editor/directos/CLAUDE.md` |
| Una grabación suelta (sin registro) para hacer un **Short 9:16** | Short manual | `/short-desde-grabacion` · `editor/shorts/METODOLOGIA-SHORTS.md` (`construir_short.py` con un plan JSON) |

**Objetivo de todo Short final:** `editor/shorts/SHORT-IDEAL.md` (referencia aprobada por el usuario). Antes de
entregarlo, `python editor/shorts/verificar_short.py VIDEO.mp4` debe decir "cumple la especificación".

## Mapa

```
editor/
├── comun/       lo que usan TODAS las líneas
│   ├── transcribir.py            transcripción (large-v3-turbo + VAD, timestamps por palabra)
│   ├── energia.py                energía a 10 ms (rms + alta frecuencia) para afinar un corte
│   ├── material.py               el material aportado y el papel de cada archivo (material.json)
│   ├── verificar_corte.sh        re-transcribe una ventana alrededor de un empalme
│   ├── detectar_silencio.sh      silencios alrededor de un instante
│   ├── partir_para_movil.py      parte un vídeo SIN recodificar para mandarlo al chat (≤ 30 MiB por trozo)
│   ├── asegurar_mejor_modelo.sh  modelo de whisper.cpp (si usas whisper.cpp en vez de faster-whisper)
│   ├── BENCHMARK-WHISPER.md      qué modelo usar y por qué (medido)
│   ├── glosario.json             términos técnicos mal escritos por Whisper -> bien escritos
│   └── fuentes/                  letra de los subtítulos (Inter, OFL)
├── shorts/      Short vertical 1080x1920 @ 60 con la cara arriba
│   ├── SHORT-IDEAL.md            CÓMO DEBE QUEDAR (especificación medible)
│   ├── METODOLOGIA-FUSION-CARA.md  juntar el Short de pantalla con la cara y la voz del usuario
│   ├── METODOLOGIA-SHORTS.md     Short mudo a mano (sin registro de pasos)
│   ├── short_desde_toma.py       toma de la Fase 1 -> Short mudo (automático)
│   ├── construir_short.py        Short mudo desde grabaciones sueltas, según un plan JSON
│   ├── analizar_fusion.py        mide cara/pantalla/voz, hojas de contacto, comprueba palabras y sincronía
│   ├── fusionar_cara_pantalla.py cara + voz + pantalla según un plan -> Short montado
│   ├── subtitular.py             subtítulos karaoke (preparar -> revisar -> quemar)
│   ├── verificar_short.py        comprueba el Short final contra SHORT-IDEAL.md
│   └── plantillas/               plan de fusión de ejemplo
├── directos/    clips 16:9 de un directo
│   ├── CLAUDE.md                 metodología completa (transcribir, elegir, cortar, verificar)
│   ├── construir_clip.sh         trim + concat + micro-fundidos
│   ├── normalizar_audio.py       normaliza a -14 LUFS, obligatorio tras construir (CLAUDE.md §5.1)
│   └── aplicar_zoom.py           zoom estratégico a cámara sobre el clip ya construido (CLAUDE.md §5.5)
├── crudo/            el material (LOCAL, no se versiona): lo llena la interfaz al arrastrar; material.json
└── videos-editados/  resultados + _cortes.log (LOCAL; el log solo se AÑADE, nunca se recrea)
```

## Reglas comunes a las tres líneas

- **Precisión por encima de coste**, pero el resultado va **al grano** (precisión no es lentitud).
- **La energía del audio manda sobre Whisper** para cortar: sus timestamps fallan 50-500 ms y en silencios inventa
  texto. Afina con `python editor/comun/energia.py VIDEO T0 T1` (o `editor/comun/detectar_silencio.sh`);
  verifica cada empalme re-transcribiéndolo (`editor/comun/verificar_corte.sh`).
- Todo lo de un vídeo concreto (transcripciones, planes, subtítulos, vídeos) vive en `crudo/` y `videos-editados/`
  y **no se sube** a git. Al repo solo va la metodología.
- **Dónde va el código nuevo:** lo que sirva a más de una línea, en `nucleo/` (un módulo por responsabilidad, sin
  CLI); lo propio de una línea, en su carpeta. Un script nunca importa a otro script. `python -m unittest discover
  -s pruebas -t pruebas` comprueba todo esto (y que ninguna ruta citada en los .md esté muerta).
