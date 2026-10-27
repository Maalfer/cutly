from cutly.services.render.effects_api import env, f, window


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    d, W, H = p["distance"], ctx.width, ctx.height
    z = f"(1+{f(2 * d)}*{e})"  # el zoom crece con el desplazamiento: nunca se ven bordes
    sx = {"left": -1, "right": 1}.get(p["direction"], 0)
    sy = {"up": -1, "down": 1}.get(p["direction"], 0)
    return [
        f"scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame",
        f"crop=w={W}:h={H}:x='(in_w-{W})/2+{sx}*{f(d * W)}*{e}':y='(in_h-{H})/2+{sy}*{f(d * H)}*{e}'",
    ] + [f"tblend=all_mode=average:enable='{window(ctx)}'"] * (int(p["blur_frames"]) - 1)  # estela: `tmix` con `enable` corrompe la imagen
