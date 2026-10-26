"""Motor de escenas: calcula el fotograma RGBA de cualquier instante a partir del JSON de la escena.

Sin estado entre fotogramas (todo es función del tiempo): vale para renders completos, por tramos y para
fotogramas sueltos. Coordenadas del mundo → píxeles con `S = ajuste · zoom`; el fondo ocupa toda la caja.
"""

import math
import random
from dataclasses import dataclass, field

import cv2
import numpy as np

from cutly.schema.scene import Burst, Card, Dot, Link, Meter, Node, Ring, Scene, Text
from cutly.services.render.animation import ease
from cutly.services.scene import canvas as C
from cutly.services.scene import glyphs as G
from cutly.services.scene import text as T

_RANK = {"link": 0, "ring": 1, "meter": 2, "node": 3, "dot": 4, "burst": 5, "card": 6, "text": 7}
_STATIC = ("node", "text", "card", "meter")
MUTED = "#8EA0C6"


def clamp(v: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if v < a else b if v > b else v


def ease_io(t: float) -> float:
    return 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t


@dataclass
class St:
    """Propiedades resueltas de un objeto en un instante."""

    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    opacity: float = 1.0
    rot: float = 0.0
    dx: float = 0.0  # desplazamiento de la entrada (no cuenta como posición para los enlaces)
    dy: float = 0.0
    draw: float = 1.0  # progreso de trazado/escritura 0-1
    p_in: float = 1.0
    p_out: float = 0.0


@dataclass
class Copy:
    """Una copia de un viajero (Dot.count)."""

    dot: Dot
    idx: int
    at: float
    color: str
    label: str | None
    key: str


@dataclass
class Item:
    obj: object
    order: int
    copy: Copy | None = None
    rank: int = 0


class Player:
    def __init__(self, scene: Scene, W: int, H: int, fit: str = "contain"):
        self.scene, self.W, self.H = scene, W, H
        ww, wh = scene.world.w, scene.world.h
        self.S0 = min(W / ww, H / wh) if fit == "contain" else max(W / ww, H / wh)
        self.cx0, self.cy0 = ww / 2, wh / 2
        self.items: list[Item] = []
        self.ids: dict[str, object] = {}
        self._dots: dict[str, list[Copy]] = {}
        self._rng: dict[int, list] = {}
        self._prep()
        self._bg = self._build_bg()
        b0 = scene.background
        self.opaque = self._bg is not None and b0.opacity >= 0.999 and b0.radius == 0
        self._corner = None
        bg = scene.background
        if bg.radius > 0:
            self._corner = C.rounded_mask(W, H, round(bg.radius * min(W, H)))

    # ---------------------------------------------------------------- preparación

    def _prep(self) -> None:
        order = 0
        extra: list[object] = []
        for o in self.scene.objects:
            if o.id:
                self.ids[o.id] = o
            if isinstance(o, Dot):
                copies = []
                for i in range(o.count):
                    colors = o.colors or [o.color]
                    label = f"#{i + 1}" if o.label_numbered else o.label
                    copies.append(
                        Copy(o, i, o.at + i * o.stagger, colors[i % len(colors)], label, f"{o.id or id(o)}#{i}")
                    )
                if o.id:
                    self._dots[o.id] = copies
                for cp in copies:
                    self.items.append(Item(o, order, cp, _RANK["dot"]))
                    order += 1
                    arrive = cp.at + o.travel
                    last = o.path[-1]
                    if o.on_arrive in ("burst", "both"):
                        extra.append(Burst(where=last, at=arrive, n=18, color=cp.color, seed=cp.idx + 3, enter="none",
                                           exit="none", z=o.z))  # fmt: skip
                    if o.on_arrive in ("ring", "both"):
                        extra.append(Ring(where=last, at=arrive, r0=o.size, r1=o.size * 5, color=cp.color, enter="none",
                                          exit="none", z=o.z, period=0.8))  # fmt: skip
                continue
            self.items.append(Item(o, order, None, _RANK[o.type]))
            order += 1
        for o in extra:
            self.items.append(Item(o, order, None, _RANK[o.type]))
            order += 1
        self.items.sort(key=lambda it: (it.obj.z, it.rank, it.order))

    def _build_bg(self):
        b = self.scene.background
        if b.style == "transparent":
            return None
        W, H = self.W, self.H
        c1, _ = C.parse_color(b.color)
        c2, _ = C.parse_color(b.color2)
        sw, sh = max(8, W // 8), max(8, H // 8)
        yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
        nx, ny = (xx / sw - 0.5) * (W / max(W, H)) * 2, (yy / sh - 0.45) * (H / max(W, H)) * 2
        d = np.sqrt(nx**2 + ny**2)
        if b.style == "solid":
            k = np.zeros_like(d)
        elif b.style == "gradient":
            k = np.clip(yy / sh, 0, 1)
        else:
            k = np.clip(d / 1.1, 0, 1)
        rgb = c1[None, None, :] + (c2 - c1)[None, None, :] * k[..., None]
        if b.vignette > 0:
            v = np.clip((d - 0.55) / 0.75, 0, 1) ** 1.5 * b.vignette
            rgb = rgb * (1 - v[..., None])
        rgb = cv2.resize(rgb.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
        return rgb * b.opacity

    # ---------------------------------------------------------------- tiempos y estados

    def _st(self, o, t: float, bx: float = 0.0, by: float = 0.0, key: str = "") -> St | None:
        tau = t - o.at
        if tau < 0:
            return None
        st = St(x=bx, y=by)
        if o.until is not None and t > o.until:
            if o.exit == "none":
                return None
            st.p_out = clamp((t - o.until) / o.dur)
            if st.p_out >= 1:
                return None
        pin = clamp(tau / o.dur)
        st.p_in = pin
        e = ease("ease_out", pin)
        name = o.enter
        if name == "fade":
            st.opacity = e
        elif name == "pop":
            st.scale, st.opacity = 0.5 + 0.5 * ease("ease_out_back", pin), min(1.0, pin * 3)
        elif name == "zoom":
            st.scale, st.opacity = 0.3 + 0.7 * e, min(1.0, pin * 2)
        elif name.startswith("slide_"):
            dx, dy = {"slide_up": (0, 70), "slide_down": (0, -70), "slide_left": (90, 0), "slide_right": (-90, 0)}[name]
            st.dx, st.dy, st.opacity = dx * (1 - e), dy * (1 - e), min(1.0, pin * 2.5)
        elif name == "drop":
            st.dy, st.opacity = -90 * (1 - ease("ease_out_bounce", pin)), min(1.0, pin * 4)
        elif name in ("draw", "type"):
            st.draw = e if name == "draw" else pin
            st.opacity = min(1.0, pin * 6)
        st.opacity *= o.opacity
        if st.p_out > 0:
            f = 1 - ease("ease_in", st.p_out)
            st.opacity *= f
            if o.exit == "shrink":
                st.scale *= 0.7 + 0.3 * f
        if o.loop != "none":
            w = math.sin(2 * math.pi * (t - o.at) / o.loop_period)
            if o.loop == "pulse":
                st.scale *= 1 + 0.06 * w
            elif o.loop == "float":
                st.y += 7 * w
            elif o.loop == "blink":
                st.opacity *= 0.65 + 0.35 * w
            elif o.loop == "spin":
                st.rot += 360 * ((t - o.at) / o.loop_period % 1.0)
            elif o.loop == "wiggle":
                st.rot += 8 * w
        if o.keys:
            for attr, base in (("x", st.x), ("y", st.y), ("scale", st.scale), ("opacity", st.opacity),
                               ("rotation", st.rot)):  # fmt: skip
                v = _key_value(o.keys, attr, base, t)
                if v is not None:
                    if attr == "rotation":
                        st.rot = v
                    else:
                        setattr(st, attr, v)
        st.opacity = clamp(st.opacity)
        return st

    # ---------------------------------------------------------------- posiciones

    def _dot_xy(self, cp: Copy, t: float, pos: dict) -> tuple[float, float, float] | None:
        """Posición del viajero en `t` (ya con la cabecera en reposo tras llegar si `persist`)."""
        o = cp.dot
        pts = [self._ref(p, pos) for p in o.path]
        segs = [math.dist(a, b) for a, b in zip(pts, pts[1:], strict=False)]
        total = sum(segs) or 1.0
        u = (t - cp.at) / o.travel
        if u < 0:
            return None
        if u >= 1:
            u = 1.0
        if o.ease == "whole":
            u = ease_io(u)
        # ¿en qué tramo estamos?
        acc = 0.0
        for i, ln in enumerate(segs):
            f0, f1 = acc / total, (acc + ln) / total
            if u <= f1 + 1e-9 or i == len(segs) - 1:
                p = clamp((u - f0) / max(f1 - f0, 1e-9))
                if o.ease == "segment":
                    p = ease_io(p)
                a, b = pts[i], pts[i + 1]
                x, y = a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p
                if o.curve:
                    nx, ny = -(b[1] - a[1]), b[0] - a[0]
                    bump = math.sin(math.pi * p) * o.curve * 0.5
                    x, y = x + nx * bump, y + ny * bump
                return x, y, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            acc += ln
        return None

    def _ref(self, r, pos: dict) -> tuple[float, float]:
        if isinstance(r, str):
            return pos.get(r, (self.cx0, self.cy0))
        return float(r[0]), float(r[1])

    def _positions(self, t: float) -> dict:
        pos: dict[str, tuple[float, float]] = {}
        for it in self.items:
            o = it.obj
            if o.type in _STATIC and o.id:
                st = self._st(o, t, o.x, o.y)
                if st is not None:
                    pos[o.id] = (st.x, st.y)
                else:  # aún no aparecido: su posición base sirve de referencia
                    pos[o.id] = (_key_value(o.keys, "x", o.x, t) or o.x, _key_value(o.keys, "y", o.y, t) or o.y)
        for oid, copies in self._dots.items():
            active = None
            for cp in copies:
                xy = self._dot_xy(cp, t, pos)
                if xy is not None and (active is None or t - cp.at < cp.dot.travel + 0.05):
                    active = xy
                    if t - cp.at < cp.dot.travel:
                        break
            if active is not None:
                pos[oid] = (active[0], active[1])
            else:
                pos[oid] = self._ref(copies[0].dot.path[0], pos)
        return pos

    # ---------------------------------------------------------------- cámara

    def _camera(self, t: float, pos: dict) -> tuple[float, float, float]:
        keys = sorted(self.scene.camera, key=lambda k: k.t)
        cx, cy = self.cx0, self.cy0
        if not keys:
            x, y, z = cx, cy, 1.0
        else:

            def at_key(k):
                if k.follow:
                    fx, fy = pos.get(k.follow, (cx, cy))
                    if k.look:
                        gx, gy = self._pos_ahead(k.follow, t)
                        d = math.hypot(gx - fx, gy - fy) or 1.0
                        fx, fy = fx + (gx - fx) / d * k.look, fy + (gy - fy) / d * k.look
                    return fx, fy, k.zoom
                return (cx if k.x is None else k.x), (cy if k.y is None else k.y), k.zoom

            if t <= keys[0].t:
                x, y, z = at_key(keys[0])
            elif t >= keys[-1].t:
                x, y, z = at_key(keys[-1])
            else:
                for k0, k1 in zip(keys, keys[1:], strict=False):
                    if t <= k1.t:
                        p = ease(k1.easing, (t - k0.t) / max(k1.t - k0.t, 1e-6))
                        a, b = at_key(k0), at_key(k1)
                        x, y, z = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p, a[2] + (b[2] - a[2]) * p)
                        break
        h = self.scene.handheld
        if h:
            x += (math.sin(t * 0.77) * 5 + math.sin(t * 1.32) * 2.5) * 0.4 * h
            y += (math.cos(t * 0.67) * 4 + math.sin(t * 1.11) * 2) * 0.4 * h
        return x, y, z

    def _pos_ahead(self, oid: str, t: float) -> tuple[float, float]:
        pos = {}
        for it in self.items:
            o = it.obj
            if o.type in _STATIC and o.id:
                pos[o.id] = (o.x, o.y)
        for cp in self._dots.get(oid, [])[:1]:
            xy = self._dot_xy(cp, min(t + 0.12, cp.at + cp.dot.travel), pos)
            if xy:
                return xy[0], xy[1]
        return pos.get(oid, (self.cx0, self.cy0))

    # ---------------------------------------------------------------- fotograma

    def frame(self, t: float, layer_opacity: float = 1.0) -> np.ndarray:
        W, H = self.W, self.H
        cv = C.Canvas(W, H)
        if self._bg is not None:
            cv.c[:] = self._bg
            cv.a[:] = self.scene.background.opacity
        pos = self._positions(t)
        cam_x, cam_y, zoom = self._camera(t, pos)
        S = self.S0 * zoom
        ctx = _Ctx(self, cv, t, pos, S, cam_x, cam_y)
        hud = _Ctx(self, cv, t, pos, self.S0, self.cx0, self.cy0)  # espacio de pantalla: sin zoom ni seguimiento
        self._ambient(ctx)
        for it in self.items:
            o = it.obj
            fn = getattr(self, f"_draw_{o.type}")
            c = hud if o.fixed else ctx
            if o.type == "dot":
                fn(c, o, it.copy)
            else:
                fn(c, o)
        b = self.scene.background
        if self._corner is not None:
            cv.c *= self._corner[..., None]
            cv.a *= self._corner
        if b.border and b.style != "transparent":
            col, ba = C.parse_color(b.border)
            r = round(b.radius * min(W, H))
            cv.paint((0, 0, W, H), col, ba, lambda img, ox, oy: C.d_rrect(img, ox, oy, W / 2, H / 2, W - 2, H - 2, r,
                                                                             fill=False, thick=3))  # fmt: skip
        if layer_opacity < 0.999:
            cv.c *= layer_opacity
            cv.a *= layer_opacity
        return cv.to_rgba(opaque=self.opaque and layer_opacity >= 0.999)

    # ---------------------------------------------------------------- ambiente

    def _ambient(self, x: "_Ctx") -> None:
        b = self.scene.background
        if b.style == "grid":
            col, _ = C.parse_color(b.accent)
            step = 80 * x.S
            if step >= 8:
                ox = (-x.cam_x * x.S + self.W / 2) % step
                oy = (-x.cam_y * x.S + self.H / 2) % step

                def grid(img, ax, ay):
                    n = 0
                    px = ox
                    while px < self.W and n < 120:
                        C.d_line(img, ax, ay, px, 0, px, self.H, 1)
                        px += step
                        n += 1
                    py = oy
                    while py < self.H and n < 240:
                        C.d_line(img, ax, ay, 0, py, self.W, py, 1)
                        py += step
                        n += 1

                x.cv.paint((0, 0, self.W, self.H), col, 0.07, grid)
        if b.stars and b.style in ("space", "grid"):
            col, _ = C.parse_color(b.accent)
            rng = random.Random(7)
            stars = [(rng.random(), rng.random(), rng.random(), rng.random()) for _ in range(b.stars)]
            par = 0.25

            for sx, sy, sz, ph in stars:
                px = (sx * self.W - x.cam_x * x.S * par) % self.W
                py = (sy * self.H - x.cam_y * x.S * par) % self.H
                tw = 0.5 + 0.5 * math.sin(x.t * (0.8 + sz) + ph * 6.28)
                r = (0.6 + sz * 1.4) * max(self.W / 1600, 0.5)
                x.cv.paint((px - r - 2, py - r - 2, px + r + 2, py + r + 2), col, 0.8 * (0.15 + 0.5 * tw),
                           lambda img, ax, ay, px=px, py=py, r=r: C.d_circle(img, ax, ay, px, py, r))  # fmt: skip

    # ---------------------------------------------------------------- objetos

    def _draw_node(self, x: "_Ctx", o: Node) -> None:
        st = self._st(o, x.t, o.x, o.y)
        if st is None:
            return
        col, _ = C.parse_color(o.color)
        fill, fa = C.parse_color(o.fill)
        px, py = x.P(st.x + st.dx, st.y + st.dy)
        size = o.size * st.scale * x.S
        sw = max(1.5, o.size * 0.035 * st.scale * x.S)
        if o.glow > 0:
            pulse = 0.85 + 0.15 * math.sin(x.t * 2.2 + o.x * 0.01)
            C.glow(x.cv, px, py, size * 1.25, col, o.glow * 0.45 * pulse * st.opacity)
        G.draw_glyph(x.cv, o.kind, px, py, size, col, fill, sw, o.rotation + st.rot, st.opacity, fa)
        asp = G.ASPECT.get(o.kind, 1.0)
        lsz = max(24.0, min(48.0, o.size * 0.27))
        if o.label:
            lc, _ = C.parse_color(o.label_color)
            if o.label_pos == "inside":
                x.text(o.label, px, py + (size * 0.1 if o.kind == "packet" else 0), lsz * 0.9 * st.scale, lc, st.opacity,
                       weight="black")  # fmt: skip
            else:
                tx, ty, al = px, py, "center"
                if o.label_pos == "below":
                    ty = py + size * 0.5 + lsz * 0.95 * x.S
                elif o.label_pos == "above":
                    ty = py - size * 0.5 - lsz * 0.95 * x.S
                elif o.label_pos == "left":
                    tx, al = px - size * asp * 0.5 - lsz * 0.5 * x.S, "right"
                else:
                    tx, al = px + size * asp * 0.5 + lsz * 0.5 * x.S, "left"
                x.text(o.label, tx, ty, lsz * st.scale, lc, st.opacity, weight="black", align=al)
                if o.sublabel:
                    sc, _ = C.parse_color(MUTED)
                    x.text(o.sublabel, tx, ty + lsz * 1.25 * x.S, lsz * 0.78 * st.scale, sc, st.opacity, align=al)

    def _draw_text(self, x: "_Ctx", o: Text) -> None:
        st = self._st(o, x.t, o.x, o.y)
        if st is None:
            return
        col, ca = C.parse_color(o.color)
        px, py = x.P(st.x + st.dx, st.y + st.dy)
        clean, marked = T.parse_markup(o.text)
        hl = [*o.highlight, *marked]
        txt = T.scramble_text(clean, o.scramble, sum(map(ord, clean)), int(x.t * 12)) if o.scramble else clean
        reveal = st.draw if o.enter == "type" else 1.0
        if o.bg:
            blk = T.render_text(txt, o.font, o.weight, o.mono, o.size * st.scale * x.S, o.align,
                                o.max_w * x.S * st.scale if o.max_w else None, o.spacing, reveal=1.0)  # fmt: skip
            if blk is not None:
                bgc, ba = C.parse_color(o.bg)
                padx, pady = o.size * 0.55 * x.S * st.scale, o.size * 0.3 * x.S * st.scale
                bw, bh = blk.w + padx * 2, blk.h + pady * 2
                x.cv.paint((px - bw / 2 - 4, py - bh / 2 - 4, px + bw / 2 + 4, py + bh / 2 + 4), bgc,
                           ba * st.opacity,
                           lambda img, ax, ay: C.d_rrect(img, ax, ay, px, py, bw, bh, min(bh / 2, o.size * 0.5 * x.S))
                           )  # fmt: skip
        x.text(txt, px, py, o.size * st.scale, col, st.opacity * ca, weight=o.weight, font=o.font, align=o.align,
               max_w=o.max_w, spacing=o.spacing, mono=o.mono, outline=o.outline, highlight=hl,
               hl_color=o.highlight_color, reveal=reveal)  # fmt: skip

    def _draw_card(self, x: "_Ctx", o: Card) -> None:
        st = self._st(o, x.t, o.x, o.y)
        if st is None:
            return
        s = x.S * st.scale
        px, py = x.P(st.x + st.dx, st.y + st.dy)
        col, _ = C.parse_color(o.color)
        fill, fa = C.parse_color(o.fill)
        tcol, _ = C.parse_color(o.text_color)
        pad = o.size * 0.55
        stacked = bool(o.icon and o.h and o.h >= o.size * 7)  # icono grande arriba, texto centrado debajo
        icon_w = o.size * 1.5 if (o.icon and not stacked) else 0
        inner = o.w - pad * 2 - icon_w
        tfont = T.get_font("Poppins", "black", False, max(4, round(o.size * s)))
        bfont = T.get_font("Poppins", "bold", False, max(4, round(o.size * 0.72 * s)))
        th = len(T.wrap_lines(o.title, tfont, inner * s)) * o.size * 1.28 if o.title else 0
        bh = len(T.wrap_lines(o.body, bfont, inner * s)) * o.size * 0.72 * 1.28 if o.body else 0
        ih = o.size * 2.4 if stacked else 0
        gap = o.size * 0.3
        content = ih + (gap if ih and (th or bh) else 0) + th + (gap if th and bh else 0) + bh
        h = o.h or (pad * 2 + content)
        top = (h - content) / 2 if o.h else pad
        W_, H_ = o.w * s, h * s
        r = min(o.size * 0.5, h / 2) * s
        op = st.opacity
        box = (px - W_ / 2 - 3, py - H_ / 2 - 3, px + W_ / 2 + 3, py + H_ / 2 + 3)
        C.glow(x.cv, px, py, max(W_, H_) * 0.75, col, 0.10 * op)
        x.cv.paint(box, fill, fa * 0.94 * op, lambda img, ax, ay: C.d_rrect(img, ax, ay, px, py, W_, H_, r))
        if o.accent in ("border", "left", "top"):
            bw_ = max(1.5, 2.2 * s)
            x.cv.paint(
                box, col, op, lambda img, ax, ay: C.d_rrect(img, ax, ay, px, py, W_, H_, r, fill=False, thick=bw_)
            )
        if o.accent == "left":
            x.cv.paint(
                box,
                col,
                op,
                lambda img, ax, ay: C.d_rrect(img, ax, ay, px - W_ / 2 + 4.5 * s, py, 9 * s, H_ - 2 * r * 0.8, 4 * s),
            )
        left = px - W_ / 2 + (pad + (6 if o.accent == "left" else 0)) * s
        cur = py - H_ / 2 + top * s  # cursor vertical (px del lienzo)
        centered = stacked or not o.icon
        tx = px if centered else left + icon_w * s
        sw = max(1.5, o.size * 0.05 * s)
        if stacked:
            G.draw_glyph(x.cv, o.icon, px, cur + ih * s / 2, ih * s * 0.85, col, fill, sw * 1.4, 0, op)
            cur += (ih + gap) * s
        elif o.icon:
            G.draw_glyph(
                x.cv, o.icon, left + icon_w * s * 0.4, cur + th * s / 2, o.size * 1.5 * s, col, fill, sw, 0, op
            )
        if o.title:
            x.text(o.title, tx if centered else tx, cur + th * s / 2, o.size * st.scale, col if o.accent != "none" else tcol, op,
                   weight="black", align="center" if centered else "left", max_w=inner, anchor_x=None if centered else tx)  # fmt: skip
            cur += (th + gap) * s
        if o.body:
            body = T.scramble_text(o.body, o.scramble, sum(map(ord, o.body)), int(x.t * 12)) if o.scramble else o.body
            x.text(body, tx, cur + bh * s / 2, o.size * 0.72 * st.scale, tcol, op, weight="bold",
                   align="center" if centered else "left", max_w=inner, anchor_x=None if centered else tx)  # fmt: skip

    def _draw_link(self, x: "_Ctx", o: Link) -> None:
        st = self._st(o, x.t)
        if st is None:
            return
        a, b = x.ref(o.a), x.ref(o.b)
        dist = math.dist(a, b)
        if dist < 1:
            return
        ux, uy = (b[0] - a[0]) / dist, (b[1] - a[1]) / dist
        a = (a[0] + ux * o.gap, a[1] + uy * o.gap)
        b = (b[0] - ux * o.gap, b[1] - uy * o.gap)
        n = 28 if o.curve else 2
        pts = []
        for i in range(n + 1):
            p = i / n
            px_, py_ = a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p
            if o.curve:
                bump = math.sin(math.pi * p) * o.curve * dist * 0.5
                px_, py_ = px_ - uy * bump, py_ + ux * bump
            pts.append(x.P(px_, py_))
        k = max(2, round(len(pts) * st.draw)) if st.draw < 1 else len(pts)
        pts = pts[: max(2, k)]
        if st.draw < 1 and len(pts) >= 2 and n == 2:  # recta: recorte exacto
            ex = pts[0][0] + (pts[1][0] - pts[0][0]) * st.draw
            ey = pts[0][1] + (pts[1][1] - pts[0][1]) * st.draw
            pts = [pts[0], (ex, ey)]
        col, _ = C.parse_color(o.color)
        g = 0.0
        for f0 in o.flash:
            if x.t >= f0:
                g = max(g, 1 - (x.t - f0) * 2.2)
        g = clamp(g)
        width = max(1.0, o.width * x.S * (1 + g * 2.6))
        alpha = clamp(o.alpha + g * 0.65) * st.opacity
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bbox = (min(xs) - width * 6, min(ys) - width * 6, max(xs) + width * 6, max(ys) + width * 6)
        dash = o.dashed

        def draw(thick):
            def fn(img, ax, ay):
                if not dash:
                    C.d_poly(img, ax, ay, pts, fill=False, closed=False, thick=thick)
                    return
                run = 0.0
                for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
                    seg = math.hypot(x2 - x1, y2 - y1)
                    d0 = 0.0
                    while d0 < seg:
                        on = (run + d0) % (16 * x.S) < 9 * x.S
                        d1 = min(seg, d0 + 3 * x.S)
                        if on:
                            C.d_line(img, ax, ay, x1 + (x2 - x1) * d0 / seg, y1 + (y2 - y1) * d0 / seg,
                                     x1 + (x2 - x1) * d1 / seg, y1 + (y2 - y1) * d1 / seg, thick)  # fmt: skip
                        d0 = d1
                    run += seg

            return fn

        if o.glow > 0:
            x.cv.paint(bbox, col, alpha * o.glow * 0.5, draw(width * 3.2))
        x.cv.paint(bbox, col, alpha, draw(width))
        if o.arrow and st.draw >= 0.98 and len(pts) >= 2:
            (x1, y1), (x2, y2) = pts[-2], pts[-1]
            ang = math.atan2(y2 - y1, x2 - x1)
            hl = 16 * x.S
            tri = [(x2, y2), (x2 - hl * math.cos(ang - 0.45), y2 - hl * math.sin(ang - 0.45)),
                   (x2 - hl * math.cos(ang + 0.45), y2 - hl * math.sin(ang + 0.45))]  # fmt: skip
            x.cv.paint(bbox, col, alpha, lambda img, ax, ay: C.d_poly(img, ax, ay, tri))
        if o.label:
            lc, _ = C.parse_color(o.label_color)
            mx, my = x.P((a[0] + b[0]) / 2 - uy * (o.curve * dist * 0.25 if o.curve else 0) - uy * 22 * (0 if o.curve else 1),
                         (a[1] + b[1]) / 2 + ux * (o.curve * dist * 0.25 if o.curve else 0) + ux * 22 * (0 if o.curve else 1))  # fmt: skip
            x.text(o.label, mx, my, 20, lc, st.opacity * min(1.0, st.draw * 2), weight="bold")

    def _draw_dot(self, x: "_Ctx", o: Dot, cp: Copy) -> None:
        t = x.t
        u = (t - cp.at) / o.travel
        if u < 0:
            return
        fade = 1.0
        if u > 1:
            if o.persist:
                fade = 1.0
            else:
                fade = 1 - clamp((t - cp.at - o.travel) / 0.2)
                if fade <= 0:
                    return
        if o.until is not None and t > o.until:
            fade *= 1 - clamp((t - o.until) / o.dur)
            if fade <= 0:
                return
        fade *= min(1.0, (t - cp.at) / 0.12 + 0.2) * o.opacity
        col, _ = C.parse_color(cp.color)
        xy = self._dot_xy(cp, t, x.pos)
        if xy is None:
            return
        # estela: posiciones pasadas del propio viajero
        if o.trail:
            for k in range(o.trail):
                tt = t - (o.trail - k) * 0.016
                past = self._dot_xy(cp, tt, x.pos) if tt >= cp.at else None
                if past is None:
                    continue
                a = (k + 1) / o.trail
                tx, ty = x.P(past[0], past[1])
                x.cv.paint((tx - o.size * x.S * 2, ty - o.size * x.S * 2, tx + o.size * x.S * 2, ty + o.size * x.S * 2),
                           col, a * 0.35 * fade,
                           lambda img, ax, ay, tx=tx, ty=ty, a=a: C.d_circle(img, ax, ay, tx, ty, (0.25 + a * 0.55) * o.size * x.S))  # fmt: skip
        px, py = x.P(xy[0], xy[1])
        r = o.size * x.S
        if o.glow > 0:
            C.glow(x.cv, px, py, r * 2.6, col, o.glow * fade)
        if o.halo:
            rr = r * 1.55 + math.sin(t * 5.5) * 0.15 * r
            ang0 = t * 90

            def halo(img, ax, ay):
                for k in range(8):
                    C.d_ellipse(img, ax, ay, px, py, rr, rr, ang0 + k * 45, ang0 + k * 45 + 24, 0, fill=False,
                                thick=max(1.5, 2 * x.S))  # fmt: skip

            x.cv.paint((px - rr - 6, py - rr - 6, px + rr + 6, py + rr + 6), col, 0.9 * fade, halo)
        if o.shape == "dot":
            x.cv.paint((px - r - 2, py - r - 2, px + r + 2, py + r + 2), col, fade,
                       lambda img, ax, ay: C.d_circle(img, ax, ay, px, py, r * 0.62))  # fmt: skip
            if cp.label:
                lc, _ = C.parse_color("#FFFFFF")
                x.text(cp.label, px, py - r * 1.7, max(12.0, o.size * 0.8), lc, fade, weight="black")
        else:
            fill, _ = C.parse_color("#06101F")
            kind = {"packet": "packet", "mail": "mail", "key": "key", "lock": "lock", "check": "check"}[o.shape]
            G.draw_glyph(x.cv, kind, px, py, r * 1.9, col, fill, max(1.5, r * 0.12), 0, fade)
            if cp.label and o.shape == "packet":
                x.text(cp.label, px, py + r * 0.22, max(11.0, o.size * 0.72), col, fade,
                       weight="black")  # fmt: skip

    def _draw_ring(self, x: "_Ctx", o: Ring) -> None:
        cx_, cy_ = x.ref(o.where)
        px, py = x.P(cx_, cy_)
        col, _ = C.parse_color(o.color)
        for k in range(o.repeat):
            tau = x.t - o.at - k * o.period
            if tau < 0 or tau > o.period:
                continue
            p = tau / o.period
            r = (o.r0 + (o.r1 - o.r0) * ease("ease_out", p)) * x.S
            x.cv.paint((px - r - 8, py - r - 8, px + r + 8, py + r + 8), col, (1 - p) * 0.9 * o.opacity,
                       lambda img, ax, ay, r=r, p=p: C.d_circle(img, ax, ay, px, py, r, fill=False, thick=max(1.0, o.width * x.S * (1 - p * 0.5))))  # fmt: skip

    def _draw_burst(self, x: "_Ctx", o: Burst) -> None:
        tau = x.t - o.at
        if tau < 0 or tau > o.life:
            return
        parts = self._rng.get(id(o))
        if parts is None:
            rng = random.Random(o.seed)
            parts = [(rng.random() * math.tau, (0.35 + rng.random() * 0.65) * o.speed, 0.6 + rng.random() * 0.8)
                     for _ in range(o.n)]  # fmt: skip
            self._rng[id(o)] = parts
        cx_, cy_ = x.ref(o.where)
        col, _ = C.parse_color(o.color)
        life = 1 - tau / o.life
        reach = (1 - math.exp(-5 * tau)) / 5
        pts = [(x.P(cx_ + math.cos(a) * sp * reach, cy_ + math.sin(a) * sp * reach), sz) for a, sp, sz in parts]
        px, py = x.P(cx_, cy_)
        rad = o.speed * x.S * 0.25 + o.size * x.S * 2

        def draw(img, ax, ay):
            for (qx, qy), sz in pts:
                C.d_circle(img, ax, ay, qx, qy, max(0.6, o.size * sz * life * x.S))

        x.cv.paint((px - rad, py - rad, px + rad, py + rad), col, clamp(life * 1.2) * o.opacity, draw)

    def _draw_meter(self, x: "_Ctx", o: Meter) -> None:
        st = self._st(o, x.t, o.x, o.y)
        if st is None:
            return
        px, py = x.P(st.x + st.dx, st.y + st.dy)
        s = x.S * st.scale
        w, h = o.w * s, o.h * s
        v = o.v0 + (o.v1 - o.v0) * ease("ease_in_out", clamp((x.t - o.at) / o.fill_dur))
        col, _ = C.parse_color(o.color)
        bg, _ = C.parse_color("#1A2540")
        box = (px - w / 2 - 4, py - h / 2 - 4, px + w / 2 + 4, py + h / 2 + 4)
        x.cv.paint(box, bg, st.opacity, lambda img, ax, ay: C.d_rrect(img, ax, ay, px, py, w, h, h / 2))
        fw = max(h, w * v)
        if v > 0.001:
            C.glow(x.cv, px - w / 2 + fw, py, h * 2.2, col, 0.4 * st.opacity)
            x.cv.paint(box, col, st.opacity,
                       lambda img, ax, ay: C.d_rrect(img, ax, ay, px - w / 2 + fw / 2, py, fw, h, h / 2))  # fmt: skip
        if o.label:
            x.text(o.label, px, py - h - 14 * s, 20 * st.scale, C.parse_color("#FFFFFF")[0], st.opacity, weight="bold")


class _Ctx:
    """Contexto de un fotograma: transformación del mundo al lienzo y helpers de texto."""

    def __init__(self, pl: Player, cv: C.Canvas, t: float, pos: dict, S: float, cam_x: float, cam_y: float):
        self.pl, self.cv, self.t, self.pos, self.S, self.cam_x, self.cam_y = pl, cv, t, pos, S, cam_x, cam_y

    def P(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self.cam_x) * self.S + self.pl.W / 2, (wy - self.cam_y) * self.S + self.pl.H / 2

    def ref(self, r) -> tuple[float, float]:
        return self.pl._ref(r, self.pos)

    def text(self, txt: str, px: float, py: float, size: float, color, alpha: float, weight: str = "bold",
             font: str = "Poppins", align: str = "center", max_w: float | None = None, spacing: float = 0.0,
             mono: bool = False, outline: str | None = None, highlight: list[str] | None = None,
             hl_color: str = "#34E3FF", reveal: float = 1.0, anchor_x: float | None = None) -> None:  # fmt: skip
        """Pinta `txt` centrado en (px, py) (o con el borde izquierdo en `anchor_x` si align=left)."""
        if alpha <= 0.004 or not txt:
            return
        S = self.S
        blk = T.render_text(txt, font, weight, mono, size * S, align, max_w * S if max_w else None, spacing,
                            outline_px=(size * S * 0.07 if outline else 0), highlight=tuple(highlight or ()), reveal=reveal)  # fmt: skip
        if blk is None:
            return
        if anchor_x is not None and align == "left":
            x0 = round(anchor_x - size * S * 0.3 - 4)
        elif align == "left":
            x0 = round(px)
        elif align == "right":
            x0 = round(px - blk.w - size * S * 0.3 * 2 - 4)
        else:
            x0 = round(px - blk.ox)
        y0 = round(py - blk.oy)
        if outline:
            ob = T.render_text(txt, font, weight, mono, size * S, align, max_w * S if max_w else None, spacing,
                               outline_px=size * S * 0.09, reveal=reveal)  # fmt: skip
            if ob is not None:
                self.cv.over(
                    ob.mask, x0 - round(ob.ox - blk.ox), y0 - round(ob.oy - blk.oy), C.parse_color(outline)[0], alpha
                )
        if blk.hl is not None:
            base = np.clip(blk.mask - blk.hl, 0, 1)
            self.cv.over(base, x0, y0, color, alpha)
            self.cv.over(blk.hl, x0, y0, C.parse_color(hl_color)[0], alpha)
        else:
            self.cv.over(blk.mask, x0, y0, color, alpha)


def _key_value(keys, attr: str, base: float, t: float) -> float | None:
    pts = sorted(((k.t, getattr(k, attr), k.easing) for k in keys if getattr(k, attr) is not None), key=lambda p: p[0])
    if not pts:
        return None
    if pts[0][0] > 0:
        pts.insert(0, (0.0, base, "linear"))
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0, _), (t1, v1, easing) in zip(pts, pts[1:], strict=False):
        if t <= t1:
            return v0 + (v1 - v0) * ease(easing, (t - t0) / max(t1 - t0, 1e-6))
    return pts[-1][1]


@dataclass
class Info:
    objects: int = 0
    warnings: list[str] = field(default_factory=list)
