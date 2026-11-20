#!/usr/bin/env python3
"""
subtitular.py — Subtítulos quemados estilo "karaoke" en un Short final, copiando el estilo del ideal del usuario
(editor/shorts/SHORT-IDEAL.md §6 Subtítulos, medido sobre su ideal.mp4).

Dos pasos, con una revisión del texto en medio (Whisper se equivoca en términos técnicos; un subtítulo mal escrito
queda quemado para siempre):

    python editor/shorts/subtitular.py preparar VIDEO.mp4 [--trans VIDEO_transcripcion.json]
        -> transcribe en modo --subtitulos (texto puntuado; si no le das --trans), aplica editor/comun/glosario.json,
           agrupa en bloques y escribe VIDEO.subtitulos.json + lo imprime. REVÍSALO: corrige el "texto" de cada bloque.
    python editor/shorts/subtitular.py quemar VIDEO.mp4 [--salida OTRO.mp4]
        -> quema los subtítulos de VIDEO.subtitulos.json y escribe VIDEO_subtitulado.mp4 (por defecto).

Aquí solo está lo propio del Short: el ESTILO visual y el dibujo. El texto (glosario, bloques) y los tiempos (cuándo
entra cada bloque y cada palabra) son nucleo/subtitulos.py.

Estilo (medido píxel a píxel en el ideal):
  - caja negra opaca de 107 px de alto, esquinas de radio 16, margen lateral de 20 px, centrada en x=540;
    vertical de 619 a 725 (centro 672), justo sobre la unión entre la cara (0-647) y la pantalla;
  - Inter Bold 52 px; palabra ya dicha en BLANCO (255), palabra por decir en GRIS (80);
  - bloques de 1-5 palabras y como mucho ~24 caracteres; se corta tras . ? ! ; cada bloque ~1 s en pantalla.
Se dibuja con Pillow (no con drawtext/libass de ffmpeg: en el build de Windows se cuelgan por fontconfig).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, REPO)
from nucleo import archivos, formato, medios, subtitulos, transcripcion  # noqa: E402
from nucleo.ffmpeg import FFMPEG, salida_atomica  # noqa: E402
from nucleo.rutas import COMUN, FUENTES  # noqa: E402

FUENTE = os.path.join(FUENTES, "Inter.ttf")
W = formato.ANCHO
ESTILO = {
    "tam": 52, "peso": 700, "caja_y0": 619, "caja_alto": 107, "radio": 16, "margen": 20,
    "blanco": (255, 255, 255, 255), "gris": (80, 80, 80, 255), "caja": (0, 0, 0, 255),
    "max_chars": 24, "max_palabras": 5, "max_dur": 1.6, "hueco_corte": 0.45, "fps": formato.FPS,
}


# ---------- preparar: texto revisable ----------
def preparar(a):
    base = os.path.splitext(a.video)[0]
    trans = a.trans
    if not trans:
        trans = base + "_transcripcion.json"
        if not os.path.exists(trans):
            subprocess.run([sys.executable, "-I", os.path.join(COMUN, "transcribir.py"), a.video,
                            "--subtitulos", "--salida", base + "_transcripcion"], check=True)
    e = ESTILO
    ws = subtitulos.aplicar_glosario(transcripcion.palabras(transcripcion.cargar_segmentos(trans)))
    bloques = subtitulos.agrupar(ws, e["max_chars"], e["max_palabras"], e["max_dur"], e["hueco_corte"])
    data = {"video": os.path.basename(a.video), "estilo": "ideal-2026-11-19",
            "_instrucciones": "Revisa 'texto' de cada bloque. Si cambias el número de palabras, los tiempos se reparten "
                              "solos dentro del bloque. No toques 'ini'/'fin' salvo que un bloque esté desfasado.",
            "bloques": subtitulos.a_json(bloques)}
    out = base + ".subtitulos.json"
    archivos.escribir_json(out, data)
    for i, b in enumerate(data["bloques"], 1):
        print(f"{i:3d} {b['ini']:6.2f}-{b['fin']:6.2f}  {b['texto']}")
    print(f"\n{len(bloques)} bloques -> {out}\nREVISA el texto antes de quemar (términos técnicos, nombres, tildes).")


# ---------- quemar: dibujo ----------
def fuente(e):
    from PIL import ImageFont
    f = ImageFont.truetype(FUENTE, e["tam"])
    try:
        f.set_variation_by_axes([32, e["peso"]])  # Inter variable: (opsz, wght)
    except Exception:
        pass
    return f


def estado_png(palabras, n_blancas, f, e, ruta):
    """La caja de un bloque con sus primeras `n_blancas` palabras en blanco y el resto en gris."""
    from PIL import Image, ImageDraw
    texto = " ".join(palabras)
    ancho = int(f.getlength(texto)) + 2 * e["margen"]
    im = Image.new("RGBA", (W, e["caja_alto"]), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0 = (W - ancho) // 2
    d.rounded_rectangle([x0, 0, x0 + ancho - 1, e["caja_alto"] - 1], radius=e["radio"], fill=e["caja"])
    x, ymid = x0 + e["margen"], e["caja_alto"] // 2
    for i, p in enumerate(palabras):
        d.text((x, ymid), p, font=f, fill=e["blanco"] if i < n_blancas else e["gris"], anchor="lm")
        x += f.getlength(p + " ")
    im.save(ruta)


def quemar(a):
    from PIL import Image
    e = ESTILO
    base = os.path.splitext(a.video)[0]
    bl = archivos.leer_json(base + ".subtitulos.json")["bloques"]
    dur = medios.duracion(a.video)
    f = fuente(e)
    tmp = tempfile.mkdtemp(prefix="subs_")
    vacio = os.path.join(tmp, "vacio.png")
    Image.new("RGBA", (W, e["caja_alto"]), (0, 0, 0, 0)).save(vacio)
    estados = []
    for t, est in subtitulos.linea_de_tiempo(bl, dur):
        if est is None:
            estados.append((t, vacio))
            continue
        bi, textos, k = est
        ruta = os.path.join(tmp, f"b{bi:03d}_{k:02d}.png")
        estado_png(textos, k, f, e, ruta)
        estados.append((t, ruta))
    # ffconcat con duraciones redondeadas a fotogramas
    lista = os.path.join(tmp, "lista.txt")
    with open(lista, "w", encoding="utf-8") as fh:
        fh.write("ffconcat version 1.0\n")
        for i, (t, png) in enumerate(estados):
            t1 = estados[i + 1][0] if i + 1 < len(estados) else dur
            d = formato.cuantizar(t1, e["fps"]) - formato.cuantizar(t, e["fps"])
            if d <= 0:
                continue
            fh.write(f"file '{png.replace(os.sep, '/')}'\nduration {d:.6f}\n")
        fh.write(f"file '{vacio.replace(os.sep, '/')}'\n")
    salida = a.salida or base + "_subtitulado.mp4"
    # a `salida` directo no: un corte a medias (memoria, Ctrl+C...) dejaría un .mp4 roto con el nombre bueno
    salida_atomica([FFMPEG, "-v", "error", "-y", "-i", a.video, "-f", "concat", "-safe", "0", "-i", lista,
                    "-filter_complex", f"[1:v]fps={e['fps']},format=rgba[s];[0:v][s]overlay=0:{e['caja_y0']}:"
                    f"eof_action=pass:format=auto,format=yuv420p[v]", "-map", "[v]", "-map", "0:a", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "16", "-c:a", "copy", "-movflags", "+faststart"], salida, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(bl)} bloques, {len(estados)} estados -> {salida}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("video")
    p.add_argument("--trans")
    q = sub.add_parser("quemar")
    q.add_argument("video")
    q.add_argument("--salida")
    a = ap.parse_args()
    (preparar if a.cmd == "preparar" else quemar)(a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
