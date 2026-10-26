# Cómo añadir efectos

Un efecto es algo que se aplica **sobre el vídeo ya compuesto** durante una ventana de tiempo (zoom, vibración, destello,
glitch, color…). Se usa como una layer `type: "effect"` y el núcleo no se toca nunca. Hay **dos formas** de añadir uno.

## 1) Por API, sin código (la que usa Claude Code)

`POST /api/v1/effects` con una cadena de filtros de FFmpeg parametrizada. Solo admite los filtros de
`GET /api/v1/effects/allowed-filters`, todos los números están acotados por el esquema y **se prueba de verdad con
FFmpeg** antes de guardarse (si falla, no se crea y te dice por qué).

```bash
curl -s -X POST $URL/api/v1/effects -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{
  "name": "warm_pulse",
  "title": "Pulso cálido",
  "description": "Calienta el color un momento para dar sensación de energía",
  "tags": ["color", "calidez"],
  "params_schema": {"type": "object", "properties": {
    "amount": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.3, "description": "Cuánto se calienta"}}},
  "chain": ["eq=gamma_r='"'"'1+{amount}*{env}'"'"':gamma_b='"'"'1-{amount}*{env}'"'"':eval=frame"]
}'
```

Huecos que puedes usar en `chain`: `{nombre_de_parametro}`, `{env}` (intensidad 0..1 en el tiempo, según el parámetro
`envelope`: pulse, in_out, decay, hold, ramp), `{t0}`, `{t1}` (inicio/fin de la layer), `{W}`, `{H}` (tamaño de la zona) y
`{window}` (condición `between(t,t0,t1)` para `enable=`). Para usarlo: añade una layer
`{"type":"effect","effect":"warm_pulse","start":2,"end":3,"params":{"amount":0.5}}`.

Qué filtros aceptan expresiones con el tiempo (`t`) y cuáles no: `eq` (con `eval=frame`), `scale` (con `eval=frame`),
`crop` (`x`/`y`), `drawbox`, `hue`. Con `enable='{window}'` valen casi todos pero con valores **constantes** (`rgbashift`,
`vignette`, `noise`, `gblur`, `negate`…). Por eso se prueban al crear el efecto.

Borrar: `DELETE /api/v1/effects/{name}` (solo los creados por API).

## 2) Con código: copiar la plantilla

1. Copia `effects/_template/` a `effects/<nombre>/` (el nombre debe coincidir con `name` en `effect.json`:
   minúsculas, números y `_`).
2. Edita `effect.json` (metadatos y **JSON Schema de parámetros**: todo número con `minimum`, `maximum` y `default`),
   `build.py` (función `build(p, ctx)` que devuelve la lista de filtros) y `preview.js` (imitación para el navegador).
3. `POST /api/v1/effects-reload` o reinicia la API. No hay que tocar nada más: el registro se autodescubre, el
   frontend carga `GET /api/v1/effects/{nombre}/preview.js` y la API valida los parámetros.

```
effects/mi_efecto/
├─ effect.json    nombre, título, descripción, categoría, tags, render_backend, fidelity, params_schema
├─ build.py       def build(p, ctx) -> list[str]   # filtros de FFmpeg
└─ preview.js     export function render(ctx, img, p, progress, size)
```

### Ejemplo completo: `zoom_punch`

`effect.json` (resumen): parámetros `scale` (1.03–2.0), `focus_x`, `focus_y`, `envelope`, `attack`, `release`.

```python
from cutly.services.render.effects_api import env, f

def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    z = f"(1+{f(p['scale'] - 1)}*{e})"                       # zoom en función del tiempo
    W, H = ctx.width, ctx.height
    return [
        f"scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame",          # agranda cada fotograma
        f"crop=w={W}:h={H}:x='min(max({f(p['focus_x'])}*in_w-{W}/2,0),in_w-{W})':y='min(max({f(p['focus_y'])}*in_h-{H}/2,0),in_h-{H})'",
    ]
```

## Reglas que ya nos costaron un susto

- **Nunca** `exp()`/`pow()` con un argumento sin acotar: fuera de la ventana desborda a infinito, `0*inf = NaN` y el
  vídeo entero se queda negro. `env()` ya acota; si escribes expresiones a mano, usa `min(1,max(0,…))`.
- Un efecto debe valer 0 y ser finito en **todo** el vídeo, no solo en su ventana (hay tests con ventanas a los 88 s).
- Fuera de su ventana el efecto no debe alterar nada: el test `test_every_effect_renders_and_changes_only_its_window`
  lo comprueba con SSIM para todos los efectos del registro (también los tuyos).
- Los efectos se aplican por orden de `z`: por defecto 0, es decir, **debajo** de textos, iconos y subtítulos (el zoom afecta
  al metraje, no a los rótulos). Súbelo por encima si quieres que también los afecte.
- `region` (`{x,y,w,h}` en 0–1 del fotograma de salida) limita el efecto a una zona: p. ej. zoom solo sobre la cara.
  Dentro de `build`, `ctx.width/height` ya son los de la región.
- `render_backend: "browser"` (Chromium para efectos que FFmpeg no pueda hacer) está reservado: aún no hay renderer, y el
  servidor actual no tiene memoria para uno.

## Coherencia preview/render

`fidelity` (`exact`) describe el render; `preview_fidelity` (`exact`|`approximate`) el preview del navegador. Diferencias
conocidas: los previews de `glitch`, `film_grain` y `blur_focus` son aproximados (Canvas no tiene `rgbashift` ni ruido
idéntico). El render es la referencia: las pruebas de imagen de `tests/golden/` comparan fotogramas renderizados con
referencias (SSIM) para reencuadre, subtítulos, iconos animados, efectos en región y transiciones.
