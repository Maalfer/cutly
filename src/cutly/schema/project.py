"""Esquema declarativo del proyecto de edición (JSON, única fuente de verdad).

Convenciones:
- Los tiempos de `timeline` (source_in/out) son segundos del vídeo ORIGINAL.
- Los tiempos de las layers (start/end) son segundos del clip RESULTANTE (línea de tiempo de salida).
- Las posiciones y tamaños son fracciones 0-1 del fotograma de salida (independientes de la resolución).
- Todo lo que pueda acabar en un filtergraph de FFmpeg o en un fichero ASS está restringido aquí
  (colores hex, ids de asset, texto sin caracteres de control) y se vuelve a sanear al renderizar.
"""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from cutly.schema.scene import Scene

CURRENT_VERSION = 1

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")]
AssetId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_\-]+(/[a-z0-9_\-.]+)+$", max_length=120)]
SafeId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_\-]{1,40}$")]
FontName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9 _\-]{1,60}$")]
EffectName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _clean_text(v: str, allow_newline: bool = True) -> str:
    bad = [c for c in v if ord(c) < 32 and not (allow_newline and c == "\n")]
    if bad or "\x7f" in v:
        raise ValueError("el texto contiene caracteres de control no permitidos")
    return v


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Geometría y animación -------------------------------------------------------------------------


class Rect(Strict):
    """Región del fotograma ORIGINAL, normalizada 0-1."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _inside(self):
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:
            raise ValueError("la región se sale del fotograma (x+w e y+h deben ser <= 1)")
        return self


class Box(Strict):
    """Caja de una layer sobre el fotograma de SALIDA (fracciones 0-1)."""

    x: float = Field(0.5, ge=-0.5, le=1.5)
    y: float = Field(0.5, ge=-0.5, le=1.5)
    w: float = Field(0.3, gt=0, le=2)
    h: float | None = Field(None, gt=0, le=2)  # None = mantener proporción
    anchor: Literal["center", "top_left", "top_center", "top_right", "bottom_left", "bottom_center", "bottom_right"] = (
        "center"
    )
    rotation: float = Field(0, ge=-360, le=360)


AnimName = Literal[
    "fade",
    "pop",
    "zoom",
    "zoom_in",
    "zoom_out",
    "slide_up",
    "slide_down",
    "slide_left",
    "slide_right",
    "slide_up_big",
    "slide_down_big",
    "slide_left_big",
    "slide_right_big",
    "from_top",
    "from_bottom",
    "from_left",
    "from_right",
    "bounce",
    "spin",
    "spin_in",
    "rotate",
    "flip",
    "fade_scale",
    "scale_up",
    "scale_down",
    "blur_fade",
    "drop",
]
Easing = Literal["linear", "ease_in", "ease_out", "ease_in_out", "ease_out_back", "ease_out_bounce", "ease_out_elastic"]
LoopName = Literal[
    "pulse",
    "breathing",
    "wiggle",
    "float",
    "hover",
    "blink",
    "shake",
    "tremble",
    "swing",
    "zoom_pulse",
    "bounce_loop",
    "spin_loop",
]


class Anim(Strict):
    name: AnimName
    dur: float = Field(0.3, ge=0.05, le=3)


class Keyframe(Strict):
    t: float = Field(ge=0)  # segundos desde el inicio de la layer
    x: float | None = Field(None, ge=-0.5, le=1.5)
    y: float | None = Field(None, ge=-0.5, le=1.5)
    scale: float | None = Field(None, gt=0, le=10)
    opacity: float | None = Field(None, ge=0, le=1)
    rotation: float | None = Field(None, ge=-360, le=360)
    easing: Easing = "ease_out"


class Loop(Strict):
    """Movimiento continuo durante toda la vida de la layer."""

    name: LoopName
    period: float = Field(1.0, ge=0.2, le=10)  # segundos por ciclo
    amount: float = Field(0.08, ge=0, le=1)  # intensidad relativa


class Animations(Strict):
    enter: Anim | None = None
    exit: Anim | None = None  # simétrica a enter: el mismo nombre en sentido inverso
    loop: Loop | None = None
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=50)


# --- Estilos -----------------------------------------------------------------------------------------


class TextStyle(Strict):
    font: FontName = "default"
    size: float = Field(0.045, ge=0.01, le=0.3)  # fracción del alto de salida
    color: HexColor = "#FFFFFF"
    outline_color: HexColor = "#000000"
    outline_width: float = Field(0.004, ge=0, le=0.03)
    bg_color: HexColor | None = None
    bold: bool = True
    italic: bool = False
    align: Literal["left", "center", "right"] = "center"
    uppercase: bool = False


class SubtitleStyle(Strict):
    font: FontName = "default"
    size: float = Field(0.05, ge=0.015, le=0.2)
    color: HexColor = "#FFFFFF"
    outline_color: HexColor = "#000000"
    outline_width: float = Field(0.006, ge=0, le=0.03)
    highlight_color: HexColor | None = "#FFD400"  # palabra activa (karaoke)
    bg_color: HexColor | None = None
    bold: bool = True
    uppercase: bool = False
    position_y: float = Field(0.72, ge=0.05, le=0.95)  # centro vertical de los subtítulos
    max_words_per_cue: int = Field(4, ge=1, le=12)
    max_lines: int = Field(2, ge=1, le=3)
    animation: Literal["karaoke", "pop", "none"] = "karaoke"


class SubtitleCue(Strict):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=200)

    _t = field_validator("text")(lambda cls, v: _clean_text(v))

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("end debe ser mayor que start")
        return self


# --- Layers --------------------------------------------------------------------------------------------


class LayerBase(Strict):
    id: SafeId = Field(default_factory=lambda: _new_id("l"))
    name: str | None = Field(None, max_length=60)
    start: float = Field(0, ge=0)
    end: float = Field(gt=0)
    z: int = Field(10, ge=-100, le=1000)
    visible: bool = True
    opacity: float = Field(1, ge=0, le=1)
    animations: Animations = Field(default_factory=Animations)

    @model_validator(mode="after")
    def _times(self):
        if self.end <= self.start:
            raise ValueError("end debe ser mayor que start (tiempos del clip resultante, en segundos)")
        return self


class TextLayer(LayerBase):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=500)
    style: TextStyle = Field(default_factory=TextStyle)
    box: Box = Field(default_factory=lambda: Box(y=0.2, w=0.8))

    _t = field_validator("text")(lambda cls, v: _clean_text(v))


class IconLayer(LayerBase):
    type: Literal["icon"] = "icon"
    asset: AssetId  # p. ej. "icons/arrow-right"
    tint: HexColor | None = None
    box: Box = Field(default_factory=lambda: Box(w=0.15))


class ImageLayer(LayerBase):
    type: Literal["image"] = "image"
    asset: AssetId  # p. ej. "overlays/marco"
    box: Box = Field(default_factory=lambda: Box(w=0.5))


class ShapeLayer(LayerBase):
    type: Literal["shape"] = "shape"
    shape: Literal["rect", "ellipse"] = "rect"
    fill: HexColor | None = "#FF3B30"
    stroke: HexColor | None = None
    stroke_width: float = Field(0.004, ge=0, le=0.05)
    box: Box = Field(default_factory=lambda: Box(w=0.3, h=0.1))


class SubtitleLayer(LayerBase):
    type: Literal["subtitle"] = "subtitle"
    end: float = Field(gt=0)
    source: Literal["transcript", "custom"] = "transcript"
    cues: list[SubtitleCue] = Field(default_factory=list, max_length=2000)  # solo si source="custom"
    style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    z: int = Field(50, ge=-100, le=1000)

    @model_validator(mode="after")
    def _cues(self):
        if self.source == "custom" and not self.cues:
            raise ValueError('source="custom" requiere al menos un cue en `cues`')
        return self


def validate_params(v: dict[str, Any], max_str: int = 200, newlines: bool = False) -> dict[str, Any]:
    """Valida el diccionario `params` (efectos y plantillas): tipos simples, profundidad y tamaño acotados."""

    def check(x: Any, depth: int) -> None:
        if depth > 3:
            raise ValueError("params demasiado anidado (máx. 3 niveles)")
        if isinstance(x, dict):
            if len(x) > 30:
                raise ValueError("params tiene demasiadas claves (máx. 30)")
            for k, val in x.items():
                if not isinstance(k, str) or len(k) > 40:
                    raise ValueError("claves de params: texto de hasta 40 caracteres")
                check(val, depth + 1)
        elif isinstance(x, list):
            if len(x) > 50:
                raise ValueError("listas en params: máx. 50 elementos")
            for val in x:
                check(val, depth + 1)
        elif isinstance(x, str):
            if len(x) > max_str:
                raise ValueError(f"textos en params: máx. {max_str} caracteres")
            _clean_text(x, allow_newline=newlines)
        elif x is not None and not isinstance(x, bool | int | float):
            raise ValueError("params solo admite texto, números, booleanos, listas y objetos")

    check(v, 0)
    return v


class EffectLayer(LayerBase):
    type: Literal["effect"] = "effect"
    z: int = Field(
        0, ge=-100, le=1000
    )  # por defecto bajo textos e iconos: el efecto afecta al metraje, no a los rótulos
    region: Rect | None = None  # si se indica, el efecto solo afecta a esa zona del fotograma de SALIDA (0-1)
    effect: EffectName  # nombre registrado en effects/<nombre>/ (se valida contra el registro al renderizar)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("params")
    @classmethod
    def _params(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_params(v)


class SceneLayer(LayerBase):
    """Animación/infografía 2D generada por el motor de escenas (ver `schema/scene.py` y `GET /scenes/templates`).

    O bien `template` + `params` (la escena se regenera sola y se ajusta a la duración de la capa), o bien `scene`
    escrita a mano. Se compone como una secuencia de fotogramas RGBA sobre el vídeo.
    """

    type: Literal["scene"] = "scene"
    z: int = Field(20, ge=-100, le=1000)
    box: Box = Field(default_factory=lambda: Box(x=0.5, y=0.5, w=1.0))
    fit: Literal["contain", "cover"] = "contain"
    template: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    scene: Scene | None = None

    @field_validator("params")
    @classmethod
    def _params(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_params(v, max_str=400, newlines=True)

    @model_validator(mode="after")
    def _source(self):
        if self.template is None and self.scene is None:
            raise ValueError("una capa `scene` necesita `template` (+ `params`) o una `scene` completa")
        return self


Layer = Annotated[
    TextLayer | IconLayer | ImageLayer | ShapeLayer | SubtitleLayer | EffectLayer | SceneLayer,
    Field(discriminator="type"),
]


# --- Proyecto ----------------------------------------------------------------------------------------------


TransitionName = Literal[
    "fade", "dissolve", "fadeblack", "fadewhite", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown", "circleopen", "circleclose", "zoomin",
    "pixelize", "radial", "smoothleft", "smoothright",
]  # fmt: skip


class Transition(Strict):
    """Transición entre este clip y el anterior: los dos se solapan `dur` segundos (la duración total se acorta)."""

    name: TransitionName = "fade"
    dur: float = Field(0.4, ge=0.1, le=1.5)


class TimelineClip(Strict):
    id: SafeId = Field(default_factory=lambda: _new_id("c"))
    source_in: float = Field(ge=0)
    source_out: float = Field(gt=0)
    speed: float = Field(1.0, ge=0.25, le=4)
    transition_in: Transition | None = None
    start_at: float | None = Field(
        None,
        ge=0,
        description="Posición absoluta en la línea de tiempo. Si se indica, permite huecos (espacios negros).",
    )

    @model_validator(mode="after")
    def _order(self):
        if self.source_out - self.source_in < 0.1:
            raise ValueError("el clip debe durar al menos 0,1 s (source_out > source_in)")
        return self

    @property
    def duration(self) -> float:
        return (self.source_out - self.source_in) / self.speed


class Output(Strict):
    width: int = Field(1080, ge=240, le=3840)
    height: int = Field(1920, ge=240, le=3840)
    fps: int = Field(30, ge=10, le=60)

    @model_validator(mode="after")
    def _even(self):
        if self.width % 2 or self.height % 2:
            raise ValueError("width y height deben ser pares (requisito de H.264)")
        return self


class Reframe(Strict):
    """Cómo se convierte el vídeo horizontal en vertical.

    center: recorte vertical centrado en `center_x`. facecam / game: solo esa región. stack: facecam
    arriba (`stack_split` del alto) y juego debajo. custom: usa `game` como región libre.
    """

    mode: Literal["center", "facecam", "game", "stack", "custom"] = "center"
    center_x: float = Field(0.5, ge=0, le=1)
    facecam: Rect | None = None
    game: Rect | None = None
    stack_split: float = Field(0.42, ge=0.1, le=0.9)
    game_fit: Literal["cover", "contain"] = "cover"

    @model_validator(mode="after")
    def _needs(self):
        need = {"facecam": ["facecam"], "game": ["game"], "stack": ["facecam", "game"], "custom": ["game"]}
        for f in need.get(self.mode, []):
            if getattr(self, f) is None:
                raise ValueError(f'reframe.mode="{self.mode}" requiere definir `{f}` (región x,y,w,h entre 0 y 1)')
        return self


class Audio(Strict):
    normalize: bool = True
    target_lufs: float = Field(-14, ge=-30, le=-6)
    true_peak: float = Field(-1.0, ge=-9, le=0)
    gain_db: float = Field(0, ge=-30, le=30)
    denoise: bool = False


class Color(Strict):
    brightness: float = Field(0, ge=-1, le=1)
    contrast: float = Field(1, ge=0, le=3)
    saturation: float = Field(1, ge=0, le=3)
    gamma: float = Field(1, ge=0.1, le=3)


class ProjectDoc(Strict):
    schema_version: int = CURRENT_VERSION
    media_id: str
    output: Output = Field(default_factory=Output)
    timeline: list[TimelineClip] = Field(default_factory=list, max_length=200)
    reframe: Reframe = Field(default_factory=Reframe)
    audio: Audio = Field(default_factory=Audio)
    color: Color = Field(default_factory=Color)
    layers: list[Layer] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def _unique_ids(self):
        for label, items in (("timeline", self.timeline), ("layers", self.layers)):
            ids = [i.id for i in items]
            dup = {i for i in ids if ids.count(i) > 1}
            if dup:
                raise ValueError(f"ids repetidos en {label}: {sorted(dup)}")
        return self

    @model_validator(mode="after")
    def _transitions(self):
        for i, c in enumerate(self.timeline):
            if c.transition_in is None:
                continue
            if i == 0:
                raise ValueError(
                    "el primer clip no puede tener transición de entrada (une dos clips; quítala o añade un clip antes)"
                )
            limit = min(self.timeline[i - 1].duration, c.duration) / 2
            if c.transition_in.dur > limit + 1e-6:
                raise ValueError(
                    f"la transición del clip '{c.id}' dura {c.transition_in.dur:g} s pero no puede superar la mitad "
                    f"del clip más corto de los dos ({limit:.2f} s)"
                )
        return self

    @property
    def duration(self) -> float:
        return timeline_duration(self.timeline)


def timeline_starts(timeline: list[TimelineClip]) -> list[float]:
    """Instante de salida en que empieza cada clip (con transición, empieza `dur` antes de que acabe el anterior)."""
    starts, t = [], 0.0
    for i, c in enumerate(timeline):
        if c.start_at is not None:
            s = c.start_at
            if i and c.transition_in:
                s -= c.transition_in.dur
            starts.append(s)
            t = s + c.duration
            continue
        if i and c.transition_in:
            t -= c.transition_in.dur
        starts.append(t)
        t += c.duration
    return starts


def timeline_duration(timeline: list[TimelineClip]) -> float:
    if not timeline:
        return 0.0
    starts = timeline_starts(timeline)
    end = 0.0
    for s, c in zip(starts, timeline, strict=True):
        end = max(end, s + c.duration)
    return round(end, 3)
