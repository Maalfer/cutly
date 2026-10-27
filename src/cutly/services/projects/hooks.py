"""Validación de capas contra los registros del servidor: efectos, assets y fuentes."""

import difflib

from cutly.registry import effects as fx_registry
from cutly.schema.ops import OpError
from cutly.schema.project import EffectLayer, IconLayer, ImageLayer, SceneLayer, SubtitleLayer, TextLayer
from cutly.schema.scene import Text as SceneText
from cutly.services.render.fonts import available_fonts
from cutly.services.render.rasterize import AssetNotFound, all_asset_ids, resolve_asset
from cutly.services.scene.templates import TemplateError, build_template


def _near(name: str, options: list[str]) -> str:
    near = difflib.get_close_matches(name, options, n=4, cutoff=0.4)
    return f" ¿Quizá {', '.join(near)}?" if near else ""


def check_layer(layer) -> None:
    """Lanza OpError con un mensaje accionable; normaliza `params` de los efectos (valores por defecto)."""
    if isinstance(layer, EffectLayer):
        try:
            layer.params = fx_registry.normalized_params(layer.effect, layer.params)
        except fx_registry.EffectParamError as e:
            raise OpError(f"Layer '{layer.id}' (efecto {layer.effect}): {e}") from e
    elif isinstance(layer, IconLayer | ImageLayer):
        try:
            resolve_asset(layer.asset)
        except AssetNotFound as e:
            raise OpError(f"Layer '{layer.id}': {e}.{_near(layer.asset, all_asset_ids())}") from e
    elif isinstance(layer, SceneLayer):
        if layer.code is not None:
            return  # motor de navegador: los errores de JS se ven en /scenes/preview o al renderizar, no aquí
        try:
            scene = layer.scene
            if layer.template:
                scene = build_template(layer.template, layer.params, layer.end - layer.start)
        except TemplateError as e:
            raise OpError(f"Layer '{layer.id}' (escena): {e}") from e
        fonts = available_fonts()
        for o in scene.objects:
            if isinstance(o, SceneText) and o.font not in fonts:
                raise OpError(
                    f"Layer '{layer.id}': la fuente '{o.font}' de un texto de la escena no existe. "
                    f"Disponibles: {', '.join(sorted(fonts))}"
                )
    elif isinstance(layer, TextLayer | SubtitleLayer):
        fonts = available_fonts()
        used = [layer.style.font] + [e.font for e in getattr(layer.style, "emphasis", []) if e.font]
        for font in used:
            if font != "default" and font not in fonts:
                raise OpError(
                    f"Layer '{layer.id}': la fuente '{font}' no existe. Disponibles: default, {', '.join(sorted(fonts))}"
                )
