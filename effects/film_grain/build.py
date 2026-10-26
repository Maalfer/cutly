from cutly.services.render.effects_api import window


def build(p, ctx):
    return [f"noise=alls={int(p['strength'])}:allf=t+u:enable='{window(ctx)}'"]
