"""Esquema declarativo de las «escenas» animadas (capa `scene`): infografías/animaciones tipo explainer.

Una escena es un pequeño mundo 2D (por defecto 1600x900) con una cámara y objetos con tiempos propios
(`at`/`until`). Todo es determinista y sin estado: el fotograma de cualquier instante se calcula solo a partir
del JSON (así valen `frame`, `filmstrip` y los renders por tramos). Los tiempos de la escena son segundos desde
el INICIO DE LA CAPA.

Tipos de objeto: node, text, card, link, dot, ring, burst, meter. Posiciones: coordenadas del mundo, o el `id`
de otro objeto (un nodo, un punto en movimiento…) allí donde se admita `Ref`.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")]
ObjId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_\-]{0,39}$")]
FontName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9 _\-]{1,60}$")]
Easing = Literal["linear", "ease_in", "ease_out", "ease_in_out", "ease_out_back", "ease_out_bounce", "ease_out_elastic"]

MAX_OBJECTS = 400


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean(v: str) -> str:
    if any(ord(c) < 32 and c != "\n" for c in v) or "\x7f" in v:
        raise ValueError("el texto contiene caracteres de control no permitidos")
    return v


# Un punto del mundo [x, y] o el id de un objeto con posición (node, text, card, dot).
Point = Annotated[list[float], Field(min_length=2, max_length=2)]
Ref = Point | ObjId

EnterName = Literal[
    "none", "fade", "pop", "zoom", "slide_up", "slide_down", "slide_left", "slide_right", "draw", "type", "drop"
]
LoopName = Literal["none", "pulse", "float", "blink", "spin", "wiggle"]


class Key(Strict):
    """Fotograma clave de un objeto (valores absolutos; `t` desde el inicio de la ESCENA)."""

    t: float = Field(ge=0)
    x: float | None = Field(None, ge=-5000, le=5000)
    y: float | None = Field(None, ge=-5000, le=5000)
    scale: float | None = Field(None, gt=0, le=10)
    opacity: float | None = Field(None, ge=0, le=1)
    rotation: float | None = Field(None, ge=-720, le=720)
    easing: Easing = "ease_in_out"


class Obj(Strict):
    id: ObjId | None = None
    at: float = Field(0, ge=0, le=600, description="Segundo (desde el inicio de la capa) en que aparece")
    until: float | None = Field(
        None, ge=0, le=600, description="Segundo en que empieza a desaparecer (None = se queda)"
    )
    enter: EnterName = "fade"
    dur: float = Field(0.4, ge=0.05, le=5, description="Duración de la entrada y de la salida")
    exit: Literal["none", "fade", "shrink"] = "fade"
    loop: LoopName = "none"
    loop_period: float = Field(1.6, ge=0.2, le=20)
    opacity: float = Field(1, ge=0, le=1)
    z: int = Field(0, ge=-50, le=50, description="Orden de dibujo dentro de la escena (mayor = encima)")
    fixed: bool = Field(
        False, description="Fijo en pantalla: la cámara (zoom/seguimiento) no le afecta; para rótulos y subtítulos"
    )
    keys: list[Key] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def _order(self):
        if self.until is not None and self.until <= self.at:
            raise ValueError("`until` debe ser mayor que `at`")
        return self


NodeKind = Literal[
    "server", "router", "computer", "phone", "cloud", "database", "lock", "key", "shield", "globe", "doc", "user",
    "circle", "box", "pill", "chip", "bolt", "check", "cross", "warning", "gear", "mail", "packet",
]  # fmt: skip


class Node(Obj):
    type: Literal["node"] = "node"
    kind: NodeKind = "circle"
    x: float = Field(800, ge=-5000, le=5000)
    y: float = Field(450, ge=-5000, le=5000)
    size: float = Field(80, ge=8, le=1200, description="Tamaño aproximado (alto) en unidades del mundo")
    color: HexColor = "#34E3FF"
    fill: HexColor = "#0A1424"
    label: str | None = Field(None, max_length=60)
    sublabel: str | None = Field(None, max_length=80)
    label_pos: Literal["below", "above", "left", "right", "inside"] = "below"
    label_color: HexColor = "#FFFFFF"
    glow: float = Field(0.35, ge=0, le=1)
    rotation: float = Field(0, ge=-360, le=360)

    _t = field_validator("label", "sublabel")(lambda cls, v: v if v is None else _clean(v))


class Text(Obj):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=400)
    x: float = Field(800, ge=-5000, le=5000)
    y: float = Field(450, ge=-5000, le=5000)
    size: float = Field(40, ge=6, le=500)
    color: HexColor = "#FFFFFF"
    font: FontName = "Poppins"
    weight: Literal["regular", "bold", "black"] = "bold"
    align: Literal["left", "center", "right"] = "center"
    max_w: float | None = Field(None, ge=40, le=4000, description="Ancho máximo (ajuste de línea)")
    bg: HexColor | None = Field(None, description="Fondo tipo píldora")
    outline: HexColor | None = None
    mono: bool = False
    spacing: float = Field(0, ge=-0.2, le=2, description="Espaciado entre letras (fracción del tamaño)")
    highlight: list[str] = Field(default_factory=list, max_length=10)
    highlight_color: HexColor = "#34E3FF"
    scramble: float = Field(
        0, ge=0, le=1, description="0-1: fracción final de la entrada con letras revueltas (cifrado)"
    )

    _t = field_validator("text")(lambda cls, v: _clean(v))


class Card(Obj):
    type: Literal["card"] = "card"
    x: float = Field(800, ge=-5000, le=5000)
    y: float = Field(450, ge=-5000, le=5000)
    w: float = Field(360, ge=40, le=3000)
    h: float | None = Field(None, ge=30, le=2000, description="Alto (None = según el contenido)")
    title: str | None = Field(None, max_length=80)
    body: str | None = Field(None, max_length=300)
    color: HexColor = "#34E3FF"
    fill: HexColor = "#0D1628"
    text_color: HexColor = "#FFFFFF"
    size: float = Field(30, ge=8, le=200, description="Tamaño del título")
    icon: NodeKind | None = None
    scramble: float = Field(0, ge=0, le=1)
    accent: Literal["left", "top", "border", "none"] = "left"

    _t = field_validator("title", "body")(lambda cls, v: v if v is None else _clean(v))


class Link(Obj):
    type: Literal["link"] = "link"
    a: Ref
    b: Ref
    color: HexColor = "#34E3FF"
    width: float = Field(3, ge=0.5, le=60)
    curve: float = Field(0, ge=-1, le=1, description="Curvatura del arco (fracción de la longitud)")
    dashed: bool = False
    arrow: bool = False
    glow: float = Field(0.3, ge=0, le=1)
    alpha: float = Field(0.55, ge=0, le=1, description="Opacidad base de la línea")
    label: str | None = Field(None, max_length=60)
    label_color: HexColor = "#FFFFFF"
    flash: list[float] = Field(default_factory=list, max_length=30, description="Instantes en que la línea destella")
    gap: float = Field(0, ge=0, le=500, description="Hueco al llegar a los extremos (para no tapar los nodos)")

    _t = field_validator("label")(lambda cls, v: v if v is None else _clean(v))


class Dot(Obj):
    """Viajero (paquete, mensaje, clave…) que recorre un camino de puntos/objetos."""

    type: Literal["dot"] = "dot"
    path: list[Ref] = Field(min_length=2, max_length=24)
    travel: float = Field(2.0, gt=0.05, le=120, description="Segundos que tarda en recorrer TODO el camino")
    shape: Literal["dot", "packet", "mail", "key", "lock", "check"] = "dot"
    color: HexColor = "#34E3FF"
    colors: list[HexColor] = Field(default_factory=list, max_length=12, description="Colores por copia (rota)")
    size: float = Field(16, ge=3, le=200)
    label: str | None = Field(None, max_length=30)
    label_numbered: bool = Field(False, description="Etiqueta «#1», «#2»… en cada copia")
    trail: int = Field(18, ge=0, le=60)
    glow: float = Field(0.6, ge=0, le=1)
    ease: Literal["segment", "linear", "whole"] = "segment"
    count: int = Field(1, ge=1, le=40)
    stagger: float = Field(0.3, ge=0, le=20)
    on_arrive: Literal["none", "burst", "ring", "both"] = "burst"
    persist: bool = Field(False, description="Se queda en el destino al llegar")
    halo: bool = Field(False, description="Anillo discontinuo alrededor (protagonista)")
    curve: float = Field(0, ge=-1, le=1)

    _t = field_validator("label")(lambda cls, v: v if v is None else _clean(v))


class Ring(Obj):
    type: Literal["ring"] = "ring"
    where: Ref = [800.0, 450.0]
    r0: float = Field(10, ge=0, le=2000)
    r1: float = Field(120, ge=1, le=3000)
    color: HexColor = "#34E3FF"
    width: float = Field(3, ge=0.5, le=40)
    repeat: int = Field(1, ge=1, le=30)
    period: float = Field(1.0, ge=0.1, le=20)


class Burst(Obj):
    type: Literal["burst"] = "burst"
    where: Ref = [800.0, 450.0]
    n: int = Field(24, ge=1, le=120)
    color: HexColor = "#37F5A3"
    speed: float = Field(260, ge=10, le=2000)
    life: float = Field(0.9, ge=0.1, le=5)
    size: float = Field(5, ge=1, le=40)
    seed: int = Field(1, ge=0, le=100000)


class Meter(Obj):
    """Barra de progreso/valor que se llena."""

    type: Literal["meter"] = "meter"
    x: float = Field(800, ge=-5000, le=5000)
    y: float = Field(450, ge=-5000, le=5000)
    w: float = Field(400, ge=20, le=4000)
    h: float = Field(18, ge=4, le=200)
    v0: float = Field(0, ge=0, le=1)
    v1: float = Field(1, ge=0, le=1)
    fill_dur: float = Field(1.5, ge=0.1, le=60)
    color: HexColor = "#37F5A3"
    label: str | None = Field(None, max_length=40)

    _t = field_validator("label")(lambda cls, v: v if v is None else _clean(v))


SceneObj = Annotated[Node | Text | Card | Link | Dot | Ring | Burst | Meter, Field(discriminator="type")]


class World(Strict):
    w: int = Field(1600, ge=200, le=4000)
    h: int = Field(900, ge=200, le=4000)


class Background(Strict):
    style: Literal["space", "grid", "solid", "gradient", "transparent"] = "space"
    color: HexColor = "#060B18"
    color2: HexColor = "#02050C"
    accent: HexColor = "#34E3FF"
    stars: int = Field(60, ge=0, le=300)
    vignette: float = Field(0.5, ge=0, le=1)
    opacity: float = Field(1, ge=0, le=1)
    radius: float = Field(0, ge=0, le=0.5, description="Esquinas redondeadas (fracción del lado corto)")
    border: HexColor | None = None


class CamKey(Strict):
    """Posición de cámara en el instante `t`. `follow` = id de un objeto en movimiento (la cámara lo sigue)."""

    t: float = Field(0, ge=0)
    x: float | None = Field(None, ge=-5000, le=5000)
    y: float | None = Field(None, ge=-5000, le=5000)
    zoom: float = Field(1, ge=0.2, le=8)
    follow: ObjId | None = None
    easing: Easing = "ease_in_out"
    look: float = Field(0, ge=0, le=400, description="Con follow: cuánto se adelanta hacia donde va")


class Scene(Strict):
    world: World = Field(default_factory=World)
    background: Background = Field(default_factory=Background)
    camera: list[CamKey] = Field(default_factory=list, max_length=60)
    handheld: float = Field(0.4, ge=0, le=3, description="Temblor suave de cámara (0 = cámara fija)")
    objects: list[SceneObj] = Field(default_factory=list, max_length=MAX_OBJECTS)

    @model_validator(mode="after")
    def _refs(self):
        ids = [o.id for o in self.objects if o.id]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"ids de objeto repetidos en la escena: {sorted(dup)}")
        known = set(ids)

        def check(ref: Any, who: str) -> None:
            if isinstance(ref, str) and ref not in known:
                near = ", ".join(sorted(known)[:12]) or "(ninguno: pon `id` a los objetos que quieras referenciar)"
                raise ValueError(f"{who} apunta al objeto '{ref}', que no existe en la escena. Ids disponibles: {near}")

        for o in self.objects:
            who = f"{o.type}{f' {o.id}' if o.id else ''}"
            if isinstance(o, Link):
                check(o.a, who), check(o.b, who)
            elif isinstance(o, Dot):
                for p in o.path:
                    check(p, who)
            elif isinstance(o, Ring):
                check(o.where, who)
            elif isinstance(o, Burst):
                check(o.where, who)
        for k in self.camera:
            if k.follow:
                check(k.follow, "camera")
        return self
