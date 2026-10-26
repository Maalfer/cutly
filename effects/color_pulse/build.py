from cutly.services.render.effects_api import env, f


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    return [f"eq=saturation='1+({f(p['saturation'])}-1)*{e}':contrast='1+({f(p['contrast'])}-1)*{e}':eval=frame"]
