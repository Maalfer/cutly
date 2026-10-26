from cutly.services.render.effects_api import f, window


def build(p, ctx):
    angle = 1.5708 * (1 - 0.75 * p["strength"])
    return [f"vignette=angle={f(angle)}:enable='{window(ctx)}'"]
