from cutly.services.render.effects_api import env, f


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    W, H = ctx.width, ctx.height
    a = f"({f(p['angle'] * 3.14159265 / 180)}*{e})"
    z = f"(1+(cos({a})-1)+{f(max(H / W, W / H))}*abs(sin({a})))"  # cubre las esquinas al girar
    return [
        f"scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame",
        f"rotate=a='{a}':ow=iw:oh=ih:c=black@0",
        f"crop=w={W}:h={H}",
    ]
