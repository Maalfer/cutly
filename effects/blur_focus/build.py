from cutly.services.render.effects_api import f, window


def build(p, ctx):
    return [f"gblur=sigma={f(p['sigma'])}:steps=1:enable='{window(ctx)}'"]
