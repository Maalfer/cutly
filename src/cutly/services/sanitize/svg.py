"""Saneado de SVG (los subidos por usuarios y los del repositorio pasan por aquí).

Lista blanca de elementos y atributos: sin scripts, sin eventos, sin referencias externas,
sin <image>/<use>/<style>/<foreignObject>, sin entidades XML (defusedxml).
"""

import re
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as DET
from defusedxml.common import DefusedXmlException

MAX_BYTES = 200_000
MAX_NODES = 2000
NS = "http://www.w3.org/2000/svg"

ELEMENTS = {
    "svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon",
    "defs", "linearGradient", "radialGradient", "stop", "clipPath",
}  # fmt: skip
ATTRS = {
    "id", "d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "width", "height", "points",
    "transform", "viewBox", "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-linecap",
    "stroke-linejoin", "stroke-miterlimit", "stroke-opacity", "stroke-dasharray", "opacity", "offset",
    "stop-color", "stop-opacity", "gradientUnits", "gradientTransform", "clip-path", "clip-rule",
    "preserveAspectRatio", "version", "fx", "fy",
}  # fmt: skip
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9#%.,\s()\-+_:/]*$")  # sin comillas, ; < > \ ni '&'


class SvgError(ValueError):
    pass


def _check_value(name: str, value: str) -> None:
    if not _SAFE_VALUE.match(value):
        raise SvgError(f"Valor no permitido en el atributo '{name}'")
    low = value.lower()
    if "javascript" in low or "data:" in low:
        raise SvgError(f"Valor no permitido en el atributo '{name}'")
    for m in re.finditer(r"url\(([^)]*)\)", low):
        if not m.group(1).strip().startswith("#"):
            raise SvgError("Solo se permiten referencias internas url(#id)")


def sanitize_svg(data: bytes | str) -> str:
    """Devuelve el SVG saneado o lanza SvgError con el motivo."""
    raw = data.encode() if isinstance(data, str) else data
    if len(raw) > MAX_BYTES:
        raise SvgError(f"El SVG supera {MAX_BYTES // 1000} KB")
    try:
        root = DET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ET.ParseError, DefusedXmlException) as e:
        raise SvgError(f"SVG inválido o con construcciones no permitidas (DTD/entidades): {e}") from e
    count = 0

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def walk(el: ET.Element) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES:
            raise SvgError("El SVG tiene demasiados elementos")
        name = local(el.tag)
        if name not in ELEMENTS:
            raise SvgError(f"Elemento <{name}> no permitido (solo formas y degradados básicos)")
        for attr in list(el.attrib):
            a = local(attr)
            val = el.attrib.pop(attr)
            if a.startswith("on") or a not in ATTRS or "}" in attr and not attr.startswith("{" + NS + "}"):
                if a in ("xmlns",) or attr.startswith("{http://www.w3.org/2000/xmlns/}"):
                    continue
                raise SvgError(f"Atributo '{a}' no permitido en <{name}>")
            _check_value(a, val)
            el.attrib[a] = val
        if el.text and el.text.strip():
            raise SvgError("El SVG no puede contener texto (convierte los textos a trazados)")
        for child in el:
            walk(child)

    if local(root.tag) != "svg":
        raise SvgError("El elemento raíz debe ser <svg>")
    walk(root)

    def qualify(el: ET.Element) -> None:
        el.tag = "{" + NS + "}" + local(el.tag)
        for c in el:
            qualify(c)

    qualify(root)
    ET.register_namespace("", NS)
    return ET.tostring(root, encoding="unicode")
