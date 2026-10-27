"""Títulos cinéticos: una escena `code` transparente generada a partir de unos pocos parámetros.

La IA no escribe HTML: elige texto, estilo y entrada por línea y el servidor monta la capa con `kit/kinetic.html`
(probado), así el resultado es consistente y barato de iterar. Para algo a medida, `kinetic.html` también es un punto
de partida copiable (ver `GET /scenes/code-kit`).
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from cutly.schema.project import Box, FontName, HexColor, SceneLayer

KIT = Path(__file__).parent / "kit" / "kinetic.html"

Entry = Literal["blur_in", "rise", "pop", "tracking", "letters", "words", "mask"]
LineStyle = Literal["title", "kicker", "statement", "impact", "ghost"]

# Valores por defecto de cada estilo; los campos que pase la IA los pisan.
STYLES: dict[str, dict] = {
    # Titular grande, degradado blanco→gris, apretado, entra desenfocado y creciendo (como «11 Skills»).
    "title": {"font": "Inter ExtraBold", "size": 150, "gradient": "#ffffff #aeb4c0", "tracking": -0.025, "in": "blur_in", "dur": 0.75, "gap": 0.0, "shadow": 0.55},
    # Línea corta y fina con letras muy separadas que se abren (como «a la vez»).
    "kicker": {"font": "Inter SemiBold", "size": 52, "color": "#ffffff", "tracking": 0.42, "tracking_from": 0.05, "in": "tracking", "dur": 0.9, "gap": 0.45, "opacity": 0.92, "shadow": 0.35},
    # Frase de dos o tres líneas que aparece palabra a palabra con rebote (como «te genera miniaturas y títulos»).
    "statement": {"font": "Inter ExtraBold", "size": 104, "color": "#ffffff", "tracking": -0.015, "in": "words", "dur": 0.8, "gap": 0.0, "shadow": 0.55, "mark_color": "#ffd400"},
    # Palabra de impacto en mayúsculas, condensada, que salta (Anton).
    "impact": {"font": "Anton", "size": 210, "color": "#ffffff", "tracking": 0.01, "in": "pop", "dur": 0.5, "gap": 0.0, "shadow": 0.7, "case": "upper", "mark_color": "#ffd400"},
    # Palabra enorme y semitransparente de fondo (como «YouTube» grande y gris detrás de la persona).
    "ghost": {"font": "Inter ExtraBold", "size": 230, "color": "#e6e8ee", "tracking": -0.03, "in": "mask", "dur": 0.7, "gap": 0.0, "opacity": 0.62, "shadow": 0.2},
}


class TitleLine(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    text: str = Field(min_length=1, max_length=120)
    style: LineStyle = "title"
    font: FontName | None = None
    weight: int | None = Field(None, ge=300, le=900)
    size: float | None = Field(None, ge=34, le=400, description="px a 1080 de ancho (se reduce sola si no cabe)")
    color: HexColor | None = None
    gradient: Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6} #[0-9a-fA-F]{6}$")] | None = Field(
        None, description='«#arriba #abajo»: degradado vertical del relleno'
    )
    tracking: float | None = Field(None, ge=-0.1, le=1.5, description="espaciado entre letras en em")
    tracking_from: float | None = Field(None, ge=-0.1, le=1.5, description="solo `in: tracking`: espaciado inicial")
    opacity: float | None = Field(None, ge=0, le=1)
    entry: Entry | None = Field(None, alias="in")
    at: float | None = Field(None, ge=0, description="s desde el inicio de la capa; por defecto escalonado 0,35 s por línea")
    say: str | None = Field(None, max_length=40, description="palabra hablada que dispara la entrada (usa la transcripción)")
    dur: float | None = Field(None, ge=0.15, le=3)
    mark: str | None = Field(None, max_length=80, description="palabras (separadas por espacio) que van en `mark_color`")
    mark_color: HexColor | None = None
    case: Literal["none", "upper"] | None = None
    gap: float | None = Field(None, ge=-0.3, le=2, description="separación sobre esta línea, en múltiplos de su tamaño")
    shadow: float | None = Field(None, ge=0, le=1)


class TitleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    lines: list[TitleLine] = Field(min_length=1, max_length=4)
    y: float = Field(0.42, ge=0.1, le=0.85, description="centro vertical del bloque (fracción del alto)")
    out: Literal["fade", "rise", "blur", "none"] = "fade"
    out_dur: float = Field(0.35, ge=0.1, le=1.5)
    scrim: float = Field(0, ge=0, le=0.8, description="velo oscuro suave tras el texto para legibilidad sobre fondos claros")
    z: int = Field(20, ge=-100, le=1000)
    name: str | None = Field(None, max_length=60)


def build_title_layer(spec: TitleSpec) -> SceneLayer:
    """Capa `scene` (código transparente) con los parámetros resueltos; no toca el proyecto."""
    lines = []
    for ln in spec.lines:
        d = dict(STYLES[ln.style])
        for k, v in ln.model_dump(by_alias=False, exclude={"style"}).items():
            if v is not None:
                d["in" if k == "entry" else k] = v
        if "color" in d and "gradient" in ln.model_fields_set and ln.gradient:
            d.pop("color", None)
        lines.append(d)
    params = {"lines": lines, "y": spec.y, "out": spec.out, "out_dur": spec.out_dur, "scrim": spec.scrim,
              "duration": round(spec.end - spec.start, 3)}  # fmt: skip
    return SceneLayer(
        name=spec.name or f"Título: {spec.lines[0].text[:40]}",
        start=spec.start, end=spec.end, z=spec.z,
        box=Box(x=0.5, y=0.5, w=1.0, h=1.0), fit="cover",
        code=KIT.read_text(), params=params, transparent=True, fps=30,
    )  # fmt: skip
