from cutly.services.render.effects_api import window


def build(p, ctx):
    return [f"negate=enable='{window(ctx)}'"]
