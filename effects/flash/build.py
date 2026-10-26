from cutly.services.render.effects_api import env, f


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    sign = "" if p["color"] == "white" else "-"
    return [f"eq=brightness='{sign}{f(p['strength'])}*{e}':eval=frame"]
