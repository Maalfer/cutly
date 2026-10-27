"""Plantillas de escena: animaciones explicativas listas para usar que se ajustan solas a la duración de la capa.

Cada plantilla es una función `(params, duración) → dict de Scene`. Los tiempos se expresan como fracciones de la
duración, así que la misma plantilla sirve para 8 s o para 40 s. Con `orient="tall"` la escena es 900x1600 (vertical,
para ocupar la pantalla de un Reel) y la topología se gira 90°.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from cutly.schema.scene import Scene

CYAN, GREEN, AMBER, VIOLET, PINK, BLUE, ORANGE = (
    "#34E3FF", "#37F5A3", "#FFCB47", "#9B6BFF", "#FF5D8F", "#5DA8FF", "#FF9D47",
)  # fmt: skip
PALETTE = [CYAN, GREEN, AMBER, VIOLET, PINK, BLUE, ORANGE, "#4DF0D0", "#C77DFF", "#7DFFB0", "#FF7D9C", "#7DD0FF"]
MUTED = "#8EA0C6"


class TemplateError(ValueError):
    pass


@dataclass
class Template:
    name: str
    title: str
    description: str
    params: dict[str, dict[str, Any]]
    build: Callable[[dict[str, Any], "B"], None]
    min_duration: float = 6.0
    recommended: float = 14.0
    tags: list[str] = field(default_factory=list)


COMMON = {
    "orient": {"type": "string", "enum": ["wide", "tall"], "default": "wide",
               "description": "wide = 1600x900 (se coloca como recuadro); tall = 900x1600 (pantalla completa vertical)"},
    "accent": {"type": "string", "default": CYAN, "description": "Color de acento #RRGGBB"},
    "background": {"type": "string", "enum": ["space", "grid", "solid", "transparent"], "default": "space",
                   "description": "transparent deja ver el vídeo de fondo (solo los elementos flotan encima)"},
    "panel": {"type": "boolean", "default": False, "description": "Esquinas redondeadas y borde (recuadro tipo tarjeta)"},
}  # fmt: skip


class B:
    """Constructor de escenas: reúne objetos y resuelve geometría según la orientación."""

    def __init__(self, dur: float, p: dict[str, Any]):
        self.dur = dur
        self.tall = p.get("orient") == "tall"
        self.accent = p.get("accent", CYAN)
        self.W, self.H = (900, 1600) if self.tall else (1600, 900)
        self.objs: list[dict] = []
        self.cam: list[dict] = []
        self.bg_style = p.get("background", "space")
        self.panel = bool(p.get("panel"))
        self.handheld = 0.4

    def t(self, f: float) -> float:
        """Fracción de la duración → segundos."""
        return round(max(0.0, min(f, 1.0)) * self.dur, 3)

    def pt(self, x: float, y: float) -> list[float]:
        """Punto de la composición apaisada (1600x900) → mundo actual (gira 90° si es vertical)."""
        return [y, 80 + x * 0.8] if self.tall else [x, y]

    def xy(self, x: float, y: float) -> dict[str, float]:
        px, py = self.pt(x, y)
        return {"x": px, "y": py}

    def add(self, **o: Any) -> dict:
        self.objs.append(o)
        return o

    def caption_pos(self) -> tuple[float, float, float]:
        return (450.0, 1490.0, 820.0) if self.tall else (800.0, 850.0, 1400.0)

    def captions(
        self,
        texts: list[str],
        start: float = 0.08,
        end: float = 0.97,
        size: float = 40,
        last_until: float | None = None,
    ) -> None:
        """Subtítulo explicativo por tramos (sustituye al anterior)."""
        if not texts:
            return
        cx, cy, mw = self.caption_pos()
        n = len(texts)
        span = (end - start) / n
        for i, tx in enumerate(texts):
            a, b = start + i * span, start + (i + 1) * span
            self.add(type="text", text=tx, x=cx, y=cy, size=size, max_w=mw, at=self.t(a),
                     until=self.t(b) - 0.45 if i < n - 1 else (self.t(last_until) if last_until else None), enter="fade", dur=0.4, exit="fade", z=20, fixed=True)  # fmt: skip

    def scene(self) -> dict:
        bg = {"style": self.bg_style, "accent": self.accent}
        if self.panel:
            bg.update(radius=0.045, border=self.accent + "55")
        return {"world": {"w": self.W, "h": self.H}, "background": bg, "camera": self.cam, "handheld": self.handheld,
                "objects": self.objs}  # fmt: skip


def _split(v: Any, default: list) -> list:
    return v if isinstance(v, list) and v else default


def _clip(s: Any, n: int) -> str:
    return str(s)[:n]


# ---------------------------------------------------------------------------------------------------------------
# 1. packet_network: el viaje de los paquetes (TCP/IP)
# ---------------------------------------------------------------------------------------------------------------

_NET = {
    "S": (170, 450), "D": (1430, 450),
    "A1": (470, 200), "A2": (800, 140), "A3": (1130, 210),
    "B1": (470, 450), "B2": (800, 450), "B3": (1130, 450),
    "C1": (470, 700), "C2": (800, 760), "C3": (1130, 690),
}  # fmt: skip
_LINKS = [("S", "A1"), ("S", "B1"), ("S", "C1"), ("A1", "A2"), ("A2", "A3"), ("A3", "D"), ("B1", "B2"), ("B2", "B3"),
          ("B3", "D"), ("C1", "C2"), ("C2", "C3"), ("C3", "D"), ("A1", "B1"), ("B1", "C1"), ("A2", "B2"), ("B2", "C2"),
          ("A3", "B3"), ("B3", "C3")]  # fmt: skip
_ROUTES = [["S", "A1", "A2", "A3", "D"], ["S", "B1", "B2", "B3", "D"], ["S", "C1", "C2", "C3", "D"]]


def _packet_network(p: dict, b: B) -> None:
    n = max(3, min(int(p["packets"]), 12))
    for i, (key, (x, y)) in enumerate(_NET.items()):
        if key in ("S", "D"):
            continue
        b.add(type="node", id=key, kind="router", size=64, color=b.accent, label=f"R{i - 1}", **b.xy(x, y),
              at=b.t(0.02 + 0.004 * i), enter="pop", dur=0.4, glow=0.3, loop="pulse", loop_period=2.6)  # fmt: skip
    b.add(type="node", id="S", kind="computer", size=150, color=GREEN, label=_clip(p["source_label"], 20), **b.xy(*_NET["S"]),
          at=b.t(0.0), enter="pop", dur=0.5)  # fmt: skip
    b.add(type="node", id="D", kind="server", size=150, color=PINK, label=_clip(p["dest_label"], 20), **b.xy(*_NET["D"]),
          at=b.t(0.015), enter="pop", dur=0.5)  # fmt: skip
    for i, (u, v) in enumerate(_LINKS):
        b.add(type="link", a=u, b=v, color=b.accent, width=2, alpha=0.18, gap=38 if "S" not in (u, v) and "D" not in (u, v) else 78,
              at=b.t(0.05 + 0.002 * i), enter="draw", dur=0.6, glow=0.15, z=-1)  # fmt: skip
    # protagonistas con seguimiento de cámara
    t1, t2 = 0.2, 0.44
    tr = 0.18
    b.add(type="dot", id="hero1", path=list(_ROUTES[0]), at=b.t(t1), travel=b.t(tr), shape="packet", size=24, color=AMBER,
          label="#4", halo=True, on_arrive="both", trail=24)  # fmt: skip
    b.add(type="dot", id="hero2", path=list(_ROUTES[2]), at=b.t(t2), travel=b.t(tr), shape="packet", size=24, color=VIOLET,
          label="#5", halo=True, on_arrive="both", trail=24)  # fmt: skip
    # el enjambre: un viajero por paquete, cada uno por una ruta
    for i in range(n):
        b.add(type="dot", id=f"pk{i}", path=list(_ROUTES[i % 3]), at=b.t(0.68 + i * 0.28 / n), travel=b.t(0.16 + 0.04 * (i % 3)),
              shape="packet", size=16, color=PALETTE[(i + 2) % len(PALETTE)], label=f"#{i + 1}", on_arrive="burst", trail=14)  # fmt: skip
    b.cam = [
        {"t": 0, "zoom": 1.0},
        {"t": b.t(t1 - 0.01), "zoom": 1.0},
        {"t": b.t(t1 + 0.03), "follow": "hero1", "zoom": 2.0 if not b.tall else 1.8, "look": 120},
        {"t": b.t(t1 + tr), "follow": "hero1", "zoom": 2.0 if not b.tall else 1.8, "look": 60},
        {"t": b.t(t2 - 0.02), "zoom": 1.0},
        {"t": b.t(t2 + 0.03), "follow": "hero2", "zoom": 2.0 if not b.tall else 1.8, "look": 120},
        {"t": b.t(t2 + tr), "follow": "hero2", "zoom": 2.0 if not b.tall else 1.8, "look": 60},
        {"t": b.t(0.66), "zoom": 1.05},
        {"t": b.t(0.9), "zoom": 1.05},
        {"t": b.t(0.95), "x": b.pt(*_NET["D"])[0], "y": b.pt(*_NET["D"])[1], "zoom": 1.7},
    ]
    b.captions(_split(p["captions"], [
        "El **ORIGEN** divide el mensaje en pequeños **paquetes**.",
        "Un paquete viaja **solo** por la red, saltando de router en router.",
        "Otro toma una **ruta distinta** hacia el mismo destino.",
        "Todos viajan **en paralelo**: nadie espera a los demás.",
        "El **DESTINO** los **reensambla** por su número de secuencia.",
    ]))  # fmt: skip


# ---------------------------------------------------------------------------------------------------------------
# 2. flow_steps: cadena de nodos con un mensaje que viaja (genérica)
# ---------------------------------------------------------------------------------------------------------------


def _flow_steps(p: dict, b: B) -> None:
    steps = _split(p["steps"], [])[:8]
    if len(steps) < 2:
        raise TemplateError('`steps` necesita al menos 2 elementos: [{"kind":"computer","label":"Tu PC"}, …]')
    n = len(steps)
    xs = [180 + i * (1240 / (n - 1)) for i in range(n)]
    size = 150 if n <= 4 else 120 if n <= 6 else 96
    names = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise TemplateError('cada paso de `steps` es un objeto: {"kind":…, "label":…, "sublabel":…, "color":…}')
        color = s.get("color") or PALETTE[i % len(PALETTE)]
        nid = f"n{i}"
        names.append(nid)
        b.add(type="node", id=nid, kind=s.get("kind", "circle"), size=size, color=color, label=_clip(s.get("label", ""), 30) or None,
              sublabel=_clip(s["sublabel"], 40) if s.get("sublabel") else None, **b.xy(xs[i], 450),
              at=b.t(0.02 + 0.03 * i), enter="pop", dur=0.5, loop="pulse" if i in (0, n - 1) else "none", loop_period=2.4)  # fmt: skip
    for i in range(n - 1):
        b.add(type="link", id=f"l{i}", a=names[i], b=names[i + 1], color=b.accent, width=3, alpha=0.5,
              gap=size * 0.62, at=b.t(0.08 + 0.03 * i), enter="draw", dur=0.5, z=-1)  # fmt: skip
    go = 0.2
    leg = (0.5 if p["return_trip"] else 0.7) / (n - 1)
    label = _clip(p["message"], 20) or None
    b.add(type="dot", id="msg", path=list(names), at=b.t(go), travel=b.t(leg * (n - 1)), shape=p["message_shape"], size=22,
          color=AMBER, label=label, halo=True, on_arrive="both", ease="segment")  # fmt: skip
    for i in range(1, n):  # destello del enlace y aro en cada nodo al pasar el mensaje
        tt = go + leg * i
        b.add(
            type="ring",
            where=names[i],
            at=b.t(tt) - 0.4,
            r0=size * 0.5,
            r1=size * 1.3,
            color=PALETTE[i % len(PALETTE)],
            period=0.6,
        )
    if p["return_trip"]:
        back = go + leg * (n - 1) + 0.06
        b.add(type="dot", id="resp", path=list(reversed(names)), at=b.t(back), travel=b.t(leg * (n - 1)), shape="packet" if p["message_shape"] != "packet" else "mail",
              size=22, color=GREEN, label=_clip(p["response"], 20) or None, halo=True, on_arrive="both")  # fmt: skip
    caps = _split(p["captions"], [])
    if caps:
        b.captions([_clip(c, 160) for c in caps])


# ---------------------------------------------------------------------------------------------------------------
# 3. dns_lookup
# ---------------------------------------------------------------------------------------------------------------


def _dns_lookup(p: dict, b: B) -> None:
    dom = _clip(p["domain"], 40)
    ip = _clip(p["ip"], 40)
    tld = "." + dom.rsplit(".", 1)[-1] if "." in dom else ".com"
    nodes = {
        "pc": ("computer", "Tu navegador", GREEN, (190, 450)),
        "res": ("router", "Resolver DNS", b.accent, (560, 450)),
        "root": ("globe", "Raíz  .", AMBER, (990, 160)),
        "tld": ("database", f"TLD  {tld}", VIOLET, (1380, 450)),
        "auth": ("server", "Servidor autoritativo", PINK, (990, 690)),
    }
    for i, (k, (kind, label, col, (x, y))) in enumerate(nodes.items()):
        b.add(
            type="node",
            id=k,
            kind=kind,
            size=130,
            color=col,
            label=label,
            **b.xy(x, y),
            at=b.t(0.02 + 0.03 * i),
            enter="pop",
            dur=0.5,
        )
    for i, (u, v) in enumerate([("pc", "res"), ("res", "root"), ("res", "tld"), ("res", "auth")]):
        b.add(
            type="link",
            a=u,
            b=v,
            color=b.accent,
            width=2.5,
            alpha=0.35,
            gap=90,
            at=b.t(0.1 + 0.02 * i),
            enter="draw",
            dur=0.5,
            z=-1,
            curve=0.0,
        )
    legs = [
        ("pc", "res", f"¿{dom}?", AMBER, f"Tu navegador pregunta: ¿cuál es la IP de **{dom}**?"),
        ("res", "root", f"¿{dom}?", AMBER, "El resolver no lo sabe: pregunta a un servidor **raíz**."),
        ("root", "res", f"pregunta a {tld}", VIOLET, f"La raíz responde: «pregunta a los servidores de **{tld}**»."),
        ("res", "tld", f"¿{dom}?", AMBER, f"El resolver pregunta al **TLD {tld}**."),
        ("tld", "res", "NS del dominio", VIOLET, "El TLD indica quién es el servidor **autoritativo** del dominio."),
        ("res", "auth", f"¿{dom}?", AMBER, "El resolver pregunta al servidor autoritativo."),
        ("auth", "res", ip, GREEN, f"¡Respuesta! **{dom}** = **{ip}**"),
        ("res", "pc", ip, GREEN, "El resolver devuelve la IP al navegador (y la guarda en **caché**)."),
    ]
    start, span = 0.16, 0.7 / len(legs)
    caps_t = []
    for i, (u, v, lab, col, cap) in enumerate(legs):
        at = start + i * span
        b.add(type="dot", id=f"q{i}", path=[u, v], at=b.t(at), travel=b.t(span * 0.8), shape="mail", size=22, color=col, label=_clip(lab, 28),
              on_arrive="ring", trail=12)  # fmt: skip
        caps_t.append(cap)
    b.captions(caps_t, start=start, end=start + len(legs) * span + 0.04, last_until=0.88)
    cx, cy = (330, 190) if not b.tall else (450, 1440)
    b.add(type="card", x=cx, y=cy, w=560 if not b.tall else 760, title=f"{dom} = {ip}", body="Ya puedes conectarte: el navegador usa esa dirección IP.", color=GREEN,
          size=34, icon="check", at=b.t(0.9), enter="pop", dur=0.5, z=15, fixed=True)  # fmt: skip


# ---------------------------------------------------------------------------------------------------------------
# 4. tls_handshake
# ---------------------------------------------------------------------------------------------------------------


def _tls_handshake(p: dict, b: B) -> None:
    dom = _clip(p["domain"], 40)
    cl = b.xy(230, 430)
    sv = b.xy(1370, 430)
    b.add(
        type="node",
        id="cl",
        kind="computer",
        size=170,
        color=GREEN,
        label="Navegador",
        **cl,
        at=0,
        enter="pop",
        dur=0.5,
    )
    b.add(
        type="node", id="sv", kind="server", size=170, color=PINK, label=dom, **sv, at=b.t(0.02), enter="pop", dur=0.5
    )
    ys = [240, 330, 420, 510] if not b.tall else [240, 330, 420, 510]
    msgs = [
        (
            0,
            "ClientHello  ·  «hola, hablo TLS 1.3»",
            AMBER,
            "El navegador saluda y propone los **algoritmos de cifrado**.",
        ),
        (1, "ServerHello + certificado", VIOLET, "El servidor responde con su **certificado**: la prueba de quién es."),
        (
            0,
            "Clave compartida (cifrada)",
            CYAN,
            "Navegador y servidor acuerdan una **clave secreta** que solo ellos conocen.",
        ),
        (1, "Finished (todo listo)", GREEN, "Los dos confirman: **el canal ya está cifrado**."),
    ]
    start, span = 0.1, 0.5 / len(msgs)
    for i, (direction, label, col, _cap) in enumerate(msgs):
        y = ys[i]
        a = [500, y] if direction == 0 else [1100, y]
        c = [1100, y] if direction == 0 else [500, y]
        a, c = (b.pt(*a), b.pt(*c))
        at = start + i * span
        b.add(
            type="link",
            a=a,
            b=c,
            color=col,
            width=2,
            alpha=0.3,
            dashed=True,
            arrow=True,
            at=b.t(at),
            enter="draw",
            dur=b.t(span * 0.8),
            z=-1,
        )
        b.add(type="text", text=label, x=b.pt(800, y - 34)[0], y=b.pt(800, y - 34)[1], size=30 if not b.tall else 24, color=col, at=b.t(at + 0.02), enter="fade", max_w=520 if b.tall else None)  # fmt: skip
        b.add(type="dot", path=[a, c], at=b.t(at), travel=b.t(span * 0.8), shape="mail" if i < 3 else "check", size=20, color=col, on_arrive="ring")  # fmt: skip
    t_lock = start + len(msgs) * span + 0.03
    lock_a, lock_b = b.pt(230, 250), b.pt(1370, 250)
    for k, pos in (("a", lock_a), ("b", lock_b)):
        b.add(
            type="node",
            id=f"lock{k}",
            kind="lock",
            size=70,
            color=GREEN,
            x=pos[0],
            y=pos[1],
            at=b.t(t_lock),
            enter="pop",
            dur=0.5,
        )
    b.add(
        type="link",
        a="cl",
        b="sv",
        color=GREEN,
        width=6,
        alpha=0.8,
        glow=0.7,
        gap=120,
        at=b.t(t_lock),
        enter="draw",
        dur=0.8,
        z=-2,
    )
    cards_t = t_lock + 0.1
    ax, ay = (500, 760) if not b.tall else (450, 1000)
    bx, by = (1100, 760) if not b.tall else (450, 1200)
    b.add(type="card", x=ax, y=ay, w=520 if not b.tall else 700, title="HTTP (sin cifrar)", body="usuario=ana&clave=1234", color=PINK, size=26,
          icon="warning", at=b.t(cards_t), enter="slide_up", dur=0.5, z=15)  # fmt: skip
    b.add(type="card", x=bx, y=by, w=520 if not b.tall else 700, title="HTTPS (TLS)", body="x9$#a7f0c2e1b4d8…", color=GREEN, size=26, icon="lock",
          scramble=0.85, at=b.t(cards_t + 0.04), enter="slide_up", dur=0.5, z=15)  # fmt: skip
    b.captions(
        [m[3] for m in msgs] + ["Con TLS, quien intercepte el tráfico solo ve **datos ilegibles**."],
        start=start,
        end=0.97,
        size=34,
    )


# ---------------------------------------------------------------------------------------------------------------
# 5. url_anatomy
# ---------------------------------------------------------------------------------------------------------------


def _url_parts(url: str) -> list[tuple[str, str, str, str]]:
    """[(texto, nombre, explicación, color)] de una URL, en orden y cubriéndola entera."""
    u = urlsplit(url if "://" in url else "https://" + url)
    host = u.hostname or ""
    parts: list[tuple[str, str, str, str]] = []
    if u.scheme:
        parts.append(
            (u.scheme + "://", "Esquema", "El protocolo: cómo hablar con el servidor (https = cifrado).", GREEN)
        )
    if host:
        parts.append((host, "Dominio", "El nombre del servidor. DNS lo convierte en una dirección IP.", CYAN))
    if u.port:
        parts.append((f":{u.port}", "Puerto", "La «puerta» del servidor (443 para HTTPS, 80 para HTTP).", AMBER))
    if u.path and u.path != "/":
        parts.append((u.path, "Ruta", "Qué recurso concreto pides dentro del servidor.", VIOLET))
    elif url.rstrip().endswith("/") or u.path == "/":
        parts.append(("/", "Ruta", "La raíz del sitio.", VIOLET))
    if u.query:
        parts.append(("?" + u.query, "Parámetros", "Datos extra para el servidor: clave=valor separados por &.", PINK))
    if u.fragment:
        parts.append(
            (
                "#" + u.fragment,
                "Fragmento",
                "Una zona de la página: lo gestiona solo el navegador, no viaja al servidor.",
                BLUE,
            )
        )
    return parts


def _url_anatomy(p: dict, b: B) -> None:
    parts = _url_parts(_clip(p["url"], 200))
    total = sum(len(t) for t, *_ in parts) or 1
    size = max(22.0, min(76.0, (b.W * 0.9) / (0.602 * total)))
    cw = 0.602 * size
    x = (b.W - total * cw) / 2
    y = b.H * (0.30 if not b.tall else 0.28)
    n = len(parts)
    t0, span = 0.12, 0.8 / n
    b.add(
        type="node",
        kind="globe",
        id="globe",
        size=90,
        color=b.accent,
        x=b.W / 2,
        y=y - size * 1.9,
        at=0,
        enter="pop",
        dur=0.5,
        glow=0.5,
    )
    cur = x
    for i, (txt, name, expl, col) in enumerate(parts):
        w = len(txt) * cw
        mid = cur + w / 2
        at, until = b.t(t0 + i * span), b.t(t0 + (i + 1) * span)
        b.add(
            type="text", text=txt, x=mid, y=y, size=size, mono=True, color="#5A6B8C", at=0.2, enter="fade", dur=0.6, z=1
        )
        b.add(type="text", text=txt, x=mid, y=y, size=size, mono=True, color=col, at=at, until=until if i < n - 1 else None, enter="pop", dur=0.35, exit="fade", z=2)  # fmt: skip
        b.add(type="link", a=[cur, y + size * 0.78], b=[cur + w, y + size * 0.78], color=col, width=5, alpha=1, glow=0.6, at=at, until=until if i < n - 1 else None, enter="draw", dur=0.4, z=2)  # fmt: skip
        b.add(type="card", x=b.W / 2, y=b.H * (0.64 if not b.tall else 0.5), w=min(900, b.W * 0.82), title=name, body=expl, color=col, size=40 if not b.tall else 34,
              at=at + 0.15, until=until if i < n - 1 else None, enter="slide_up", dur=0.4, z=10)  # fmt: skip
        cur += w


# ---------------------------------------------------------------------------------------------------------------
# 6. recap_cards
# ---------------------------------------------------------------------------------------------------------------


def _recap_cards(p: dict, b: B) -> None:
    items = _split(p["items"], [])[:6]
    if not items:
        raise TemplateError('`items` necesita al menos 1 elemento: [{"icon":"lock","title":"Cifrado","body":"…"}]')
    n = len(items)
    b.add(
        type="text",
        text=_clip(p["title"], 60),
        x=b.W / 2,
        y=b.H * 0.12,
        size=62 if not b.tall else 54,
        color="#FFFFFF",
        at=0,
        enter="type",
        dur=0.9,
        max_w=b.W * 0.9,
    )
    b.add(
        type="link",
        a=[b.W * 0.3, b.H * 0.18],
        b=[b.W * 0.7, b.H * 0.18],
        color=b.accent,
        width=5,
        alpha=1,
        glow=0.6,
        at=b.t(0.05),
        enter="draw",
        dur=0.7,
    )
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise TemplateError('cada elemento de `items` es un objeto: {"icon":…, "title":…, "body":…}')
        col = it.get("color") or PALETTE[i % len(PALETTE)]
        if b.tall:
            h = min(360, (b.H * 0.7) / n - 20)
            cx, cy, w = b.W / 2, b.H * 0.26 + h / 2 + i * (h + 20), b.W * 0.88
        else:
            gap = 24
            w = min(470, (b.W * 0.92 - gap * (n - 1)) / n)
            cx = b.W / 2 - (n * w + (n - 1) * gap) / 2 + w / 2 + i * (w + gap)
            cy, h = b.H * 0.56, 420
        b.add(type="card", x=cx, y=cy, w=w, h=h, title=_clip(it.get("title", ""), 40) or None, body=_clip(it.get("body", ""), 200) or None, color=col,
              size=34 if (n <= 3 or b.tall) else 28, icon=it.get("icon") or "check", accent="border", at=b.t(0.12 + 0.7 * i / n), enter="pop", dur=0.5, z=5)  # fmt: skip
        b.add(type="ring", where=[cx, cy], at=b.t(0.12 + 0.7 * i / n), r0=40, r1=min(w, h) * 0.7, color=col, period=0.7)
    b.handheld = 0.2


# ---------------------------------------------------------------------------------------------------------------
# 7. title_card
# ---------------------------------------------------------------------------------------------------------------


def _title_card(p: dict, b: B) -> None:
    cx, cy = b.W / 2, b.H / 2
    if p["icon"] and p["icon"] != "none":
        b.add(
            type="node",
            kind=p["icon"],
            size=180 if not b.tall else 200,
            color=b.accent,
            x=cx,
            y=cy - (230 if not b.tall else 260),
            at=0,
            enter="pop",
            dur=0.6,
            glow=0.7,
            loop="float",
            loop_period=3,
        )
        b.add(
            type="ring",
            where=[cx, cy - (230 if not b.tall else 260)],
            at=b.t(0.04),
            r0=60,
            r1=260,
            color=b.accent,
            period=1.2,
            repeat=2,
        )
    b.add(
        type="text",
        text=_clip(p["title"], 90),
        x=cx,
        y=cy + 10,
        size=84 if not b.tall else 78,
        max_w=b.W * 0.88,
        color="#FFFFFF",
        weight="black",
        at=b.t(0.05),
        enter="type",
        dur=1.0,
    )
    b.add(
        type="link",
        a=[cx - b.W * 0.2, cy + (110 if not b.tall else 190)],
        b=[cx + b.W * 0.2, cy + (110 if not b.tall else 190)],
        color=b.accent,
        width=6,
        alpha=1,
        glow=0.7,
        at=b.t(0.2),
        enter="draw",
        dur=0.7,
    )
    if p["subtitle"]:
        b.add(
            type="text",
            text=_clip(p["subtitle"], 140),
            x=cx,
            y=cy + (190 if not b.tall else 290),
            size=40,
            max_w=b.W * 0.8,
            color=MUTED,
            at=b.t(0.28),
            enter="slide_up",
            dur=0.6,
        )
    b.handheld = 0.6


# ---------------------------------------------------------------------------------------------------------------
# registro
# ---------------------------------------------------------------------------------------------------------------

REGISTRY: dict[str, Template] = {}


def _reg(t: Template) -> None:
    t.params = {**t.params, **COMMON}
    REGISTRY[t.name] = t


_reg(Template(
    "packet_network", "El viaje de los paquetes (TCP/IP)",
    "Un mensaje se parte en paquetes que cruzan una red de routers por rutas distintas; la cámara sigue a dos de ellos y al final el destino los reensambla. Ideal para explicar TCP/IP, enrutamiento o por qué internet es robusto.",
    {"packets": {"type": "integer", "default": 8, "minimum": 3, "maximum": 12, "description": "Paquetes del enjambre"},
     "source_label": {"type": "string", "default": "ORIGEN"}, "dest_label": {"type": "string", "default": "DESTINO"},
     "captions": {"type": "array", "default": [], "description": "Subtítulos explicativos (vacío = los de por defecto); se reparten en el tiempo"}},
    _packet_network, 10, 22, ["redes", "tcp", "ip", "routers"]))  # fmt: skip
_reg(Template(
    "flow_steps", "Cadena de pasos con un mensaje que viaja",
    "N nodos en línea (2-8) con un mensaje que los recorre uno a uno (y, opcional, la respuesta de vuelta). Sirve para casi cualquier flujo: cliente→servidor, login, pipeline CI/CD, correo…",
    {"steps": {"type": "array", "default": [{"kind": "computer", "label": "Tu PC"}, {"kind": "router", "label": "Router"}, {"kind": "cloud", "label": "Internet"}, {"kind": "server", "label": "Servidor"}],
               "description": "[{kind, label, sublabel?, color?}] · kind: " + "server|router|computer|phone|cloud|database|lock|key|shield|globe|doc|user|chip|mail|gear…"},
     "message": {"type": "string", "default": "petición"}, "response": {"type": "string", "default": "respuesta"},
     "message_shape": {"type": "string", "enum": ["dot", "packet", "mail", "key", "lock", "check"], "default": "packet"},
     "return_trip": {"type": "boolean", "default": True}, "captions": {"type": "array", "default": []}},
    _flow_steps, 6, 12, ["flujo", "genérica"]))  # fmt: skip
_reg(Template(
    "dns_lookup", "Cómo funciona el DNS",
    "El navegador pregunta a un resolver, que consulta raíz → TLD → servidor autoritativo hasta obtener la IP del dominio. Con subtítulos paso a paso y tarjeta final.",
    {"domain": {"type": "string", "default": "cogny.es"}, "ip": {"type": "string", "default": "203.0.113.10"}},
    _dns_lookup, 12, 22, ["dns", "redes"]))  # fmt: skip
_reg(Template(
    "tls_handshake", "HTTPS: el handshake TLS",
    "ClientHello, certificado, clave compartida y canal cifrado; al final compara un dato en HTTP (legible) frente a HTTPS (ilegible).",
    {"domain": {"type": "string", "default": "cogny.es"}}, _tls_handshake, 12, 20, ["https", "tls", "seguridad"]))  # fmt: skip
_reg(Template(
    "url_anatomy", "Partes de una URL",
    "Escribe la URL y resalta una a una sus partes (esquema, dominio, puerto, ruta, parámetros, fragmento) con su explicación. Se descompone sola a partir de `url`.",
    {"url": {"type": "string", "default": "https://www.cogny.es:443/blog/post?id=7#intro"}},
    _url_anatomy, 8, 18, ["url", "web"]))  # fmt: skip
_reg(Template(
    "recap_cards", "Resumen en tarjetas",
    "Título y de 1 a 6 tarjetas con icono que van apareciendo (en fila, o apiladas si es vertical). Para cierres de capítulo y listas de ideas clave.",
    {"title": {"type": "string", "default": "Resumen"},
     "items": {"type": "array", "default": [{"icon": "globe", "title": "DNS", "body": "Convierte nombres en IPs."}, {"icon": "packet", "title": "TCP/IP", "body": "Reparte y reensambla paquetes."}, {"icon": "lock", "title": "TLS", "body": "Cifra la conversación."}],
               "description": "[{icon, title, body, color?}]"}},
    _recap_cards, 5, 10, ["resumen", "lista"]))  # fmt: skip
_reg(Template(
    "title_card", "Rótulo de título cinematográfico",
    "Icono animado, título que se escribe, línea de acento y subtítulo. Para abrir un tema o separar secciones.",
    {"title": {"type": "string", "default": "¿Qué pasa cuando pulsas Enter?"}, "subtitle": {"type": "string", "default": ""},
     "icon": {"type": "string", "default": "globe", "description": "Tipo de nodo (globe, lock, server…) o «none»"}},
    _title_card, 3, 6, ["título", "intro"]))  # fmt: skip


# ---------------------------------------------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------------------------------------------


def normalize_params(t: Template, params: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(params) - set(t.params))
    if unknown:
        raise TemplateError(
            f"Parámetros desconocidos para '{t.name}': {', '.join(unknown)}. Válidos: {', '.join(sorted(t.params))}"
        )
    out: dict[str, Any] = {}
    for k, spec in t.params.items():
        v = params.get(k, spec["default"])
        ty = spec["type"]
        ok = {"string": isinstance(v, str), "boolean": isinstance(v, bool), "array": isinstance(v, list),
              "integer": isinstance(v, int) and not isinstance(v, bool),
              "number": isinstance(v, int | float) and not isinstance(v, bool)}[ty]  # fmt: skip
        if not ok:
            raise TemplateError(f"El parámetro '{k}' de '{t.name}' debe ser de tipo {ty}")
        if "enum" in spec and v not in spec["enum"]:
            raise TemplateError(f"'{k}' debe ser uno de: {', '.join(spec['enum'])}")
        if ty in ("integer", "number") and not (spec.get("minimum", v) <= v <= spec.get("maximum", v)):
            raise TemplateError(f"'{k}' debe estar entre {spec['minimum']} y {spec['maximum']}")
        if k == "accent" and not (isinstance(v, str) and len(v) == 7 and v.startswith("#")):
            raise TemplateError("'accent' debe ser un color #RRGGBB")
        out[k] = v
    return out


def get_template(name: str) -> Template:
    t = REGISTRY.get(name)
    if t is None:
        raise TemplateError(f"La plantilla '{name}' no existe. Disponibles: {', '.join(sorted(REGISTRY))}")
    return t


def build_template(name: str, params: dict[str, Any], duration: float) -> Scene:
    t = get_template(name)
    p = normalize_params(t, params)
    b = B(max(duration, 0.5), p)
    t.build(p, b)
    try:
        return Scene.model_validate(b.scene())
    except Exception as e:  # noqa: BLE001
        raise TemplateError(f"La plantilla '{name}' con esos parámetros no genera una escena válida: {e}") from e


def expand(layer) -> Scene:
    """Escena de una capa: la generada por su plantilla (ajustada a su duración) o la escrita a mano."""
    if layer.template:
        return build_template(layer.template, layer.params, layer.end - layer.start)
    return layer.scene


def describe(t: Template) -> dict[str, Any]:
    return {
        "name": t.name, "title": t.title, "description": t.description, "tags": t.tags,
        "min_duration": t.min_duration, "recommended_duration": t.recommended,
        "params": t.params,
        "example_layer": {"type": "scene", "template": t.name, "start": 2.0, "end": 2.0 + t.recommended,
                          "box": {"x": 0.5, "y": 0.5, "w": 1.0}, "params": {k: s["default"] for k, s in t.params.items() if k not in COMMON}},
    }  # fmt: skip
