from cutly.services.render.effects_api import f, window


def build(p, ctx):
    th = max(2, round(p["thickness"] * ctx.height))
    y = "0" if p["position"] == "top" else f"ih-{th}"
    dur = max(ctx.t1 - ctx.t0, 0.05)
    color = "0x" + p["color"][1:].upper()
    return [
        f"drawbox=x=0:y={y}:w='iw*min(1,max(0,(t-{f(ctx.t0)})/{f(dur)}))':h={th}:color={color}@{f(p['opacity'])}:t=fill:enable='{window(ctx)}'"
    ]
