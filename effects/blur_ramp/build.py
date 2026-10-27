from cutly.services.render.effects_api import f


def build(p, ctx):
    n, smax = int(p["steps"]), p["sigma"]
    levels = [smax * (i + 1) / n for i in range(n)]
    if p["mode"] == "out":
        levels.reverse()
    elif p["mode"] == "in_out":
        levels = levels + levels[::-1]
    span = (ctx.t1 - ctx.t0) / len(levels)
    out = []
    for i, s in enumerate(levels):
        a, b = ctx.t0 + i * span, ctx.t0 + (i + 1) * span
        out.append(f"gblur=sigma={f(s)}:steps=1:enable='gte(t,{f(a)})*lt(t,{f(b)})'")
    return out
