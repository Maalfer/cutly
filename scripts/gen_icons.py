"""Genera los iconos SVG incluidos (assets/icons) y assets/manifest.json. Creación propia, CC0.

Uso: uv run python scripts/gen_icons.py
Solo se usan elementos que admite el saneador (path, circle, rect, ellipse, polygon, polyline, line, g).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "assets"
Y, K, W, R, B, G = "#FFD400", "#111111", "#FFFFFF", "#FF3B30", "#0A84FF", "#34C759"


def svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>\n'


def poly(d, fill=Y, stroke=K, w=1.4):
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{w}" stroke-linejoin="round"/>'


def stroke2(d, color=Y, outline=K, w=2.6, ow=2.6):
    """Trazo con contorno oscuro: dos pasadas del mismo camino."""
    return (f'<path d="{d}" fill="none" stroke="{outline}" stroke-width="{w + ow}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')


def disc(fill, cx=12, cy=12, r=10.5, stroke=W, w=1.6):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{w}"/>'


def face(extra: str, fill="#FFCC00"):
    return svg(disc(fill, stroke=K, w=1.3) + extra)


E = {}  # nombre -> (svg, etiquetas, descripción)
E["arrow-left"] = (svg(poly("M21 9.5H11V4L2 12l9 8v-5.5h10z")), ["flecha", "izquierda", "arrow", "left", "señalar"], "Flecha gruesa amarilla hacia la izquierda")
E["arrow-up"] = (svg(poly("M9.5 21V11H4l8-9 8 9h-5.5v10z")), ["flecha", "arriba", "arrow", "up", "subir"], "Flecha gruesa amarilla hacia arriba")
E["arrow-down"] = (svg(poly("M9.5 3v10H4l8 9 8-9h-5.5V3z")), ["flecha", "abajo", "arrow", "down", "bajar", "comentar"], "Flecha gruesa amarilla hacia abajo")
E["arrow-curved"] = (svg(stroke2("M4 19c-.5-8 5-13 13-12") + poly("M13.5 2.5l6 4.7-6.3 3.6z", w=1.2)), ["flecha", "curva", "arrow", "curved", "señalar"], "Flecha curva hecha a mano")
E["chevrons"] = (svg(stroke2("M5 4l8 8-8 8M12 4l8 8-8 8", w=2.8, ow=2.4)), ["flecha", "siguiente", "chevron", "avanzar", "doble"], "Doble chevron hacia la derecha")
E["cross"] = (svg(disc(R) + f'<path d="M8 8l8 8M16 8l-8 8" stroke="{W}" stroke-width="2.6" stroke-linecap="round"/>'), ["x", "error", "no", "cross", "mal", "incorrecto"], "Aspa blanca sobre círculo rojo")
E["question"] = (svg(disc(B) + f'<path d="M9 9.2a3 3 0 1 1 4.6 2.5c-1 .7-1.6 1.2-1.6 2.6" fill="none" stroke="{W}" stroke-width="2.2" stroke-linecap="round"/><circle cx="12" cy="17.6" r="1.4" fill="{W}"/>'), ["pregunta", "duda", "question", "qué", "interrogación"], "Interrogación blanca sobre círculo azul")
E["plus"] = (svg(disc(G) + f'<path d="M12 6.5v11M6.5 12h11" stroke="{W}" stroke-width="2.8" stroke-linecap="round"/>'), ["más", "añadir", "plus", "suma"], "Signo más blanco sobre círculo verde")
E["warning"] = (svg(poly("M12 2.2L22.5 20.5H1.5z", fill=Y, w=1.6) + f'<rect x="10.8" y="8.2" width="2.4" height="6.4" rx="1.2" fill="{K}"/><circle cx="12" cy="17.4" r="1.4" fill="{K}"/>'), ["aviso", "cuidado", "warning", "peligro", "atención"], "Triángulo de advertencia amarillo")
E["info"] = (svg(disc(B) + f'<circle cx="12" cy="7.4" r="1.5" fill="{W}"/><rect x="10.8" y="10" width="2.4" height="7.6" rx="1.2" fill="{W}"/>'), ["info", "información", "dato", "nota"], "Letra i blanca sobre círculo azul")
E["heart"] = (svg(poly("M12 21s-8-5.3-8-11a4.6 4.6 0 0 1 8-3 4.6 4.6 0 0 1 8 3c0 5.7-8 11-8 11z", fill="#FF2D55", stroke=W, w=1.3)), ["corazón", "me gusta", "heart", "amor", "like"], "Corazón rojo")
E["fire"] = (svg(poly("M12 1.8c1 4 5.4 6 5.4 11.4a5.4 5.4 0 0 1-10.8 0c0-2.2 1-3.8 2.2-5.4.3 1.8 1 2.6 2 2.8C10.6 8.2 10.4 5 12 1.8z", fill="#FF9500", stroke="#C23A00", w=1.2) + '<path d="M12 14c1.1 1.3 2.2 2.2 2.2 3.7a2.2 2.2 0 0 1-4.4 0c0-1.5 1.1-2.4 2.2-3.7z" fill="#FFD400"/>'), ["fuego", "fire", "caliente", "trending", "viral", "top"], "Llama naranja")
E["lightning"] = (svg(poly("M13.5 1.8L4 14h7l-1.2 8.2L20 9h-6.8z")), ["rayo", "lightning", "rápido", "energía", "velocidad", "bolt"], "Rayo amarillo")
E["play"] = (svg(disc(R) + f'<path d="M10 8l7 4-7 4z" fill="{W}"/>'), ["play", "reproducir", "vídeo", "video"], "Botón de reproducir")
E["eye"] = (svg(f'<path d="M1.5 12S6 5 12 5s10.5 7 10.5 7-4.5 7-10.5 7S1.5 12 1.5 12z" fill="{W}" stroke="{K}" stroke-width="1.4"/><circle cx="12" cy="12" r="3.8" fill="{B}"/><circle cx="12" cy="12" r="1.7" fill="{K}"/>'), ["ojo", "mirar", "eye", "atento", "ver"], "Ojo abierto")
E["lock"] = (svg(stroke2("M7.5 10V7.5a4.5 4.5 0 0 1 9 0V10", color="#C7CBD1", w=2, ow=2.2) + f'<rect x="4.5" y="10" width="15" height="11" rx="2.5" fill="{Y}" stroke="{K}" stroke-width="1.4"/><circle cx="12" cy="14.6" r="1.6" fill="{K}"/><rect x="11.2" y="15" width="1.6" height="3.4" rx=".8" fill="{K}"/>'), ["candado", "seguridad", "lock", "privado", "cifrado", "ciberseguridad"], "Candado cerrado")
E["key"] = (svg(f'<circle cx="7.5" cy="12" r="5" fill="{Y}" stroke="{K}" stroke-width="1.4"/><circle cx="7.5" cy="12" r="1.8" fill="{K}"/><path d="M12 12h10v3.5M17.5 12v3" fill="none" stroke="{K}" stroke-width="4.4" stroke-linecap="round"/><path d="M12 12h10v3.5M17.5 12v3" fill="none" stroke="{Y}" stroke-width="2.2" stroke-linecap="round"/>'), ["llave", "clave", "key", "contraseña", "acceso"], "Llave dorada")
E["gear"] = (svg('<g fill="#9AA0A6" stroke="#111111" stroke-width="1.1">' + "".join(f'<rect x="10" y="1.5" width="4" height="5" rx="1" transform="rotate({a} 12 12)"/>' for a in range(0, 360, 45)) + '</g><circle cx="12" cy="12" r="6.6" fill="#9AA0A6" stroke="#111111" stroke-width="1.1"/><circle cx="12" cy="12" r="2.8" fill="#1C1C1E"/>'), ["engranaje", "ajustes", "gear", "configuración", "sistema"], "Engranaje gris")
E["bug"] = (svg(f'<g stroke="{K}" stroke-width="1.6" stroke-linecap="round"><path d="M3 9l4 2M3 15l4-2M21 9l-4 2M21 15l-4-2M8 4l2.5 2M16 4l-2.5 2"/></g><ellipse cx="12" cy="14" rx="6" ry="7.4" fill="{G}" stroke="{K}" stroke-width="1.4"/><circle cx="12" cy="6.4" r="3" fill="{G}" stroke="{K}" stroke-width="1.4"/><path d="M12 8v13" stroke="{K}" stroke-width="1.2"/><circle cx="9.4" cy="13" r="1.1" fill="{K}"/><circle cx="14.6" cy="13" r="1.1" fill="{K}"/><circle cx="9.6" cy="17.4" r="1.1" fill="{K}"/><circle cx="14.4" cy="17.4" r="1.1" fill="{K}"/>'), ["bug", "insecto", "error", "fallo", "hacking", "vulnerabilidad"], "Bicho verde (bug)")
E["shield"] = (svg(poly("M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z", fill=B, stroke=W, w=1.4) + f'<path d="M8 12l3 3 5-6" fill="none" stroke="{W}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'), ["escudo", "seguridad", "shield", "protección", "ciberseguridad", "defensa"], "Escudo azul con check")
E["magnifier"] = (svg(f'<path d="M15 15l6.5 6.5" stroke="{K}" stroke-width="5.4" stroke-linecap="round"/><path d="M15 15l6.5 6.5" stroke="{Y}" stroke-width="3" stroke-linecap="round"/><circle cx="10" cy="10" r="6.6" fill="#CFE9FF" fill-opacity=".55" stroke="{K}" stroke-width="3.8"/><circle cx="10" cy="10" r="6.6" fill="none" stroke="{Y}" stroke-width="1.8"/>'), ["lupa", "buscar", "magnifier", "ver de cerca", "detalle", "zoom"], "Lupa")
E["speech-bubble"] = (svg(poly("M4 3.5h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-5 4v-4H4a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2z", fill=W, w=1.4) + f'<circle cx="8" cy="10" r="1.4" fill="{K}"/><circle cx="12" cy="10" r="1.4" fill="{K}"/><circle cx="16" cy="10" r="1.4" fill="{K}"/>'), ["comentario", "comentar", "bocadillo", "speech", "chat", "mensaje"], "Bocadillo de diálogo")
E["light-bulb"] = (svg(f'<path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" fill="{Y}" stroke="{K}" stroke-width="1.4"/><rect x="8.5" y="17" width="7" height="2.2" rx="1" fill="#C7CBD1" stroke="{K}" stroke-width="1.1"/><rect x="9.5" y="19.4" width="5" height="2.2" rx="1" fill="#C7CBD1" stroke="{K}" stroke-width="1.1"/>'), ["idea", "bombilla", "light bulb", "truco", "consejo", "tip"], "Bombilla encendida")
E["clock"] = (svg(disc(W, stroke=K, w=1.6) + f'<path d="M12 6v6l4 2.4" fill="none" stroke="{K}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'), ["reloj", "tiempo", "clock", "hora", "rápido", "minutos"], "Reloj")
E["rocket"] = (svg(poly("M12 1.5c3.4 2.4 4.8 6 4.2 11l-2 2.6h-4.4l-2-2.6c-.6-5 .8-8.6 4.2-11z", fill=W, w=1.3) + poly("M7.8 12.2L4 15v3.5l4-1.4zM16.2 12.2L20 15v3.5l-4-1.4z", fill=R, w=1.2) + f'<circle cx="12" cy="8.2" r="1.9" fill="{B}" stroke="{K}" stroke-width="1"/>' + poly("M10.2 15.6h3.6L12 22z", fill="#FF9500", stroke="#C23A00", w=1)), ["cohete", "rocket", "lanzar", "crecer", "rápido", "despegar"], "Cohete")
E["trophy"] = (svg(poly("M7 3h10v5a5 5 0 0 1-10 0z", fill=Y, w=1.4) + f'<path d="M7 5H3.5c0 3 1.6 4.8 4 5M17 5h3.5c0 3-1.6 4.8-4 5" fill="none" stroke="{K}" stroke-width="1.4" stroke-linecap="round"/><path d="M12 13v4" stroke="{K}" stroke-width="3" stroke-linecap="round"/><path d="M12 13v4" stroke="{Y}" stroke-width="1.4"/><rect x="7.5" y="17" width="9" height="3.4" rx="1.2" fill="{Y}" stroke="{K}" stroke-width="1.4"/>'), ["trofeo", "campeón", "trophy", "ganar", "premio", "logro"], "Trofeo dorado")
E["terminal"] = (svg(f'<rect x="1.5" y="3.5" width="21" height="17" rx="2.6" fill="#1C1C1E" stroke="{W}" stroke-width="1.4"/><path d="M5.5 9l4 3-4 3" fill="none" stroke="{G}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M11.5 15.5h6" stroke="{G}" stroke-width="2" stroke-linecap="round"/>'), ["terminal", "consola", "comando", "linux", "shell", "cli", "bash"], "Ventana de terminal con prompt verde")
E["download"] = (svg(disc(B) + f'<path d="M12 6.5v8M8.2 11.2l3.8 3.8 3.8-3.8M7 18h10" fill="none" stroke="{W}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'), ["descargar", "download", "instalar", "bajar", "obtener"], "Descargar")
E["cloud"] = (svg(poly("M7 19a4.6 4.6 0 0 1-.7-9.1A6 6 0 0 1 17.8 8.6 5.2 5.2 0 0 1 17.5 19z", fill="#CFE9FF", stroke=B, w=1.6)), ["nube", "cloud", "servidor", "internet", "almacenamiento"], "Nube")
E["wifi"] = (svg(stroke2("M2.5 9a14 14 0 0 1 19 0M5.8 12.6a9.4 9.4 0 0 1 12.4 0M9 16.1a4.8 4.8 0 0 1 6 0", color=B, outline=W, w=2.2, ow=1.6) + f'<circle cx="12" cy="19.4" r="1.9" fill="{B}" stroke="{W}" stroke-width="1"/>'), ["wifi", "red", "conexión", "internet", "inalámbrico"], "Símbolo wifi azul")
E["smile"] = (face(f'<circle cx="8.4" cy="9.4" r="1.4" fill="{K}"/><circle cx="15.6" cy="9.4" r="1.4" fill="{K}"/><path d="M7 14c1.2 2.6 3 3.6 5 3.6s3.8-1 5-3.6" fill="none" stroke="{K}" stroke-width="1.8" stroke-linecap="round"/>'), ["emoji", "sonrisa", "smile", "feliz", "cara", "contento"], "Cara sonriente")
E["laugh"] = (face(f'<path d="M6.6 9.8l3-1.4M17.4 9.8l-3-1.4" stroke="{K}" stroke-width="1.8" stroke-linecap="round"/><path d="M6.4 13h11.2c0 3.6-2.4 6-5.6 6s-5.6-2.4-5.6-6z" fill="{K}"/><path d="M8.4 16.4c1-.8 2.2-1.2 3.6-1.2s2.6.4 3.6 1.2c-.8 1.2-2 1.8-3.6 1.8s-2.8-.6-3.6-1.8z" fill="#FF6B6B"/>'), ["emoji", "risa", "laugh", "gracioso", "jaja", "humor"], "Cara riéndose")
E["wow"] = (face(f'<circle cx="8.4" cy="9.2" r="1.7" fill="{K}"/><circle cx="15.6" cy="9.2" r="1.7" fill="{K}"/><ellipse cx="12" cy="16.4" rx="2.6" ry="3.2" fill="{K}"/><path d="M6 5.4l3-.8M18 5.4l-3-.8" stroke="{K}" stroke-width="1.6" stroke-linecap="round"/>'), ["emoji", "sorpresa", "wow", "increíble", "impacto", "guau"], "Cara de sorpresa")
E["cool"] = (face(f'<path d="M3.6 8.6h16.8l-1.2 4.6a3 3 0 0 1-3 2.2h-2.6a3 3 0 0 1-2.8-2l-.4-1-.4 1a3 3 0 0 1-2.8 2H7.8a3 3 0 0 1-3-2.2z" fill="{K}"/><path d="M8 18c1.2 1.4 2.6 2 4 2s2.8-.6 4-2" fill="none" stroke="{K}" stroke-width="1.8" stroke-linecap="round"/>'), ["emoji", "guay", "cool", "gafas", "genial", "chulo"], "Cara con gafas de sol")
E["thinking"] = (face(f'<circle cx="8.4" cy="10.4" r="1.3" fill="{K}"/><circle cx="15.6" cy="10.4" r="1.3" fill="{K}"/><path d="M6.6 8l3.6-.4" stroke="{K}" stroke-width="1.6" stroke-linecap="round"/><path d="M13.6 7.4q2.2-2.2 4.4-.2" fill="none" stroke="{K}" stroke-width="1.6" stroke-linecap="round"/><path d="M9 16.6l5.6-1.2" stroke="{K}" stroke-width="1.8" stroke-linecap="round"/>'), ["emoji", "pensar", "thinking", "duda", "hmm", "reflexión"], "Cara pensativa (una ceja levantada)")
E["skull"] = (svg(poly("M12 2.2c-5 0-8 3.2-8 7.6 0 2.8 1.2 4.4 3 5.6V19h10v-3.6c1.8-1.2 3-2.8 3-5.6 0-4.4-3-7.6-8-7.6z", fill=W, w=1.4) + f'<circle cx="8.6" cy="10.6" r="2.2" fill="{K}"/><circle cx="15.4" cy="10.6" r="2.2" fill="{K}"/><path d="M12 13.4l-1.2 2.4h2.4z" fill="{K}"/><path d="M9.5 19v2.4M12 19v2.4M14.5 19v2.4" stroke="{K}" stroke-width="1.3"/>'), ["calavera", "skull", "hacker", "muerte", "peligro", "pirata"], "Calavera")
E["sparkles"] = (svg(poly("M10 3l1.9 5.4L17 10.4l-5.1 1.9L10 17.8l-1.9-5.5L3 10.4l5.1-2z", w=1.2) + poly("M18.4 14.2l.9 2.5 2.5.9-2.5.9-.9 2.5-.9-2.5-2.5-.9 2.5-.9z", fill=W, w=1) + poly("M18.6 2.6l.6 1.7 1.7.6-1.7.6-.6 1.7-.6-1.7-1.7-.6 1.7-.6z", fill=W, w=.9)), ["destellos", "sparkles", "magia", "brillo", "nuevo", "especial"], "Destellos")
E["burst"] = (svg('<g transform="translate(12 12) scale(0.9) translate(-12 -12)">' + poly("M12 1.2l2.3 4.4 4.7-1.7.5 5 4.8 1.7-3 3.9 3 3.9-4.8 1.7-.5 5-4.7-1.7L12 22.8l-2.3-4.4-4.7 1.7-.5-5-4.8-1.7 3-3.9-3-3.9 4.8-1.7.5-5 4.7 1.7z", fill=R, stroke=Y, w=1.6) + "</g>"), ["explosión", "burst", "énfasis", "novedad", "oferta", "destacar"], "Estallido rojo para destacar")
E["squiggle"] = (svg(stroke2("M2 13c2-3 3.4-3 5 0s3 3 5 0 3.4-3 5 0 3 3 5 0", color=R, outline=W, w=2.4, ow=1.6)), ["subrayado", "onda", "squiggle", "underline", "resaltar", "énfasis"], "Subrayado ondulado rojo")
E["corners"] = (svg(f'<path d="M2 8V3.5A1.5 1.5 0 0 1 3.5 2H8M16 2h4.5A1.5 1.5 0 0 1 22 3.5V8M22 16v4.5a1.5 1.5 0 0 1-1.5 1.5H16M8 22H3.5A1.5 1.5 0 0 1 2 20.5V16" fill="none" stroke="{K}" stroke-width="4.2" stroke-linecap="round"/><path d="M2 8V3.5A1.5 1.5 0 0 1 3.5 2H8M16 2h4.5A1.5 1.5 0 0 1 22 3.5V8M22 16v4.5a1.5 1.5 0 0 1-1.5 1.5H16M8 22H3.5A1.5 1.5 0 0 1 2 20.5V16" fill="none" stroke="{Y}" stroke-width="2.2" stroke-linecap="round"/>'), ["marco", "esquinas", "corners", "enfocar", "visor", "selección"], "Esquinas de enfoque")

LIC = "CC0 (creación propia)"
manifest = []
icons_dir = ROOT / "icons"
icons_dir.mkdir(parents=True, exist_ok=True)
# los 5 originales (se conservan) + los nuevos
base = {
    "arrow-right": (["flecha", "derecha", "arrow", "right", "señalar"], "Flecha gruesa amarilla hacia la derecha"),
    "circle-emphasis": (["círculo", "énfasis", "circle", "resaltar", "marcar"], "Elipse roja hecha a mano para rodear algo"),
    "star": (["estrella", "star", "favorito", "destacado", "calidad"], "Estrella amarilla"),
    "exclamation": (["exclamación", "alerta", "exclamation", "importante", "cuidado"], "Exclamación blanca sobre círculo rojo"),
    "check": (["check", "correcto", "ok", "hecho", "verificado", "instalado"], "Check blanco sobre círculo verde"),
}
for name, (tags, desc) in base.items():
    manifest.append({"id": f"icons/{name}", "kind": "icon", "tags": tags, "description": desc, "license": LIC})
for name, (content, tags, desc) in E.items():
    (icons_dir / f"{name}.svg").write_text(content, encoding="utf-8")
    manifest.append({"id": f"icons/{name}", "kind": "icon", "tags": tags, "description": desc, "license": LIC})

fonts = [
    ("fonts/Poppins-Bold", "Poppins", ["moderna", "limpia", "redondeada", "subtítulos", "texto"], "Sans geométrica redonda; la mejor opción para subtítulos (usa style.bold=true)"),
    ("fonts/Poppins-ExtraBold", "Poppins ExtraBold", ["moderna", "gruesa", "rótulos", "títulos", "chips"], "Poppins extragruesa para rótulos y etiquetas (usa style.bold=false)"),
    ("fonts/Anton-Regular", "Anton", ["condensada", "impacto", "titular", "alta", "cartel"], "Condensada de impacto, ideal en MAYÚSCULAS para titulares (style.bold=false)"),
    ("fonts/BebasNeue-Regular", "Bebas Neue", ["condensada", "elegante", "mayúsculas", "titular"], "Condensada de mayúsculas, aire editorial (style.bold=false)"),
    ("fonts/Bangers-Regular", "Bangers", ["cómic", "divertida", "gracioso", "gamer"], "Estilo cómic, para contenido divertido o gamer (style.bold=false)"),
]
for fid, family, tags, desc in fonts:
    manifest.append({"id": fid, "kind": "font", "family": family, "tags": tags, "description": desc, "license": "SIL OFL 1.1"})
(ROOT / "manifest.json").write_text(json.dumps({"assets": manifest}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(manifest), "assets en el manifiesto;", len(list(icons_dir.glob("*.svg"))), "iconos")
