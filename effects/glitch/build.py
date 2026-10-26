from cutly.services.render.effects_api import window


def build(p, ctx):
    a, w, r = int(p["intensity"]), window(ctx), p["rate"]
    return [
        f"rgbashift=rh={a}:bh=-{a}:rv={max(a // 4, 1)}:enable='{w}*lt(mod(t*{r:g},1),0.5)'",
        f"rgbashift=rh=-{a}:bh={a}:gv={max(a // 3, 1)}:enable='{w}*gte(mod(t*{r:g},1),0.5)'",
    ]
