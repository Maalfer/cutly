from cutly.services.render.effects_api import env, f


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    w = p["warmth"]
    return [
        f"eq=brightness='{f(p['strength'])}*{e}':gamma_g='1-{f(0.22 * w)}*{e}':gamma_b='1-{f(0.6 * w)}*{e}':saturation='1+{f(0.5 * w)}*{e}':eval=frame"
    ]
