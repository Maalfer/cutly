"""Constructor del efecto: recibe los parámetros YA validados contra `params_schema` y devuelve filtros de FFmpeg.

Reglas:
- Devuelve una lista de filtros (`["scale=...", "crop=..."]`) que se encadenan sobre el vídeo ya compuesto.
- Usa `env()` para una intensidad 0..1 que vale 0 fuera de la ventana de la layer (¡nunca uses exp() sin acotar!).
- Solo filtros de la lista blanca (GET /effects/allowed-filters). Todo número va formateado con `f()`.
- `ctx.width/height` son el tamaño de la zona donde actúa el efecto (la región, si la layer tiene `region`).
"""

from cutly.services.render.effects_api import env, f


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])  # expresión en función de t, 0 fuera de la ventana
    # Ejemplo: saturación que sube con la intensidad. `eval=frame` hace que se reevalúe en cada fotograma.
    return [f"eq=saturation='1+{f(p['intensity'])}*{e}':eval=frame"]
