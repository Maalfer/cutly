from cutly.services.render.effects_api import env, f, window


def build(p, ctx):
    e = env(p["envelope"], ctx, p["attack"], p["release"])
    z = f"(1+{f(p['scale'] - 1)}*{e})"
    W, H = ctx.width, ctx.height
    return [
        f"scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame",
        f"crop=w={W}:h={H}:x='min(max({f(p['focus_x'])}*in_w-{W}/2,0),in_w-{W})':y='min(max({f(p['focus_y'])}*in_h-{H}/2,0),in_h-{H})'",
    ] + [f"tblend=all_mode=average:enable='{window(ctx)}'"] * (int(p["blur_frames"]) - 1)  # estela: `tmix` con `enable` corrompe la imagen
