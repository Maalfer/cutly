from cutly.services.render.effects_api import env, f, window


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    h = f"max(1,ih*{f(p['amount'])}*{e})"
    w = window(ctx)
    return [
        f"drawbox=x=0:y=0:w=iw:h='{h}':color=black:t=fill:enable='{w}'",
        f"drawbox=x=0:y='ih-{h}':w=iw:h='{h}':color=black:t=fill:enable='{w}'",
    ]
