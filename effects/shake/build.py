from cutly.services.render.effects_api import env, f


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    i, W, H = p["intensity"], ctx.width, ctx.height
    z = f"(1+{f(2.4 * i)}*{e})"
    w1, w2 = f(6.2832 * p["frequency"]), f(6.2832 * p["frequency"] * 0.83)
    return [
        f"scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame",
        f"crop=w={W}:h={H}:x='(in_w-{W})/2+{f(i * W)}*{e}*sin({w1}*t)':y='(in_h-{H})/2+{f(i * H * 0.8)}*{e}*cos({w2}*t+1)'",
    ]
