#!/usr/bin/env python3
"""
subtitular.py — Subtítulos quemados estilo "karaoke" en un Short final, copiando el estilo del ideal del usuario
(editor/SHORT-IDEAL.md §6 Subtítulos, medido sobre su ideal.mp4).

Dos pasos, con una revisión del texto en medio (Whisper se equivoca en términos técnicos; un subtítulo mal escrito
queda quemado para siempre):

    python subtitular.py preparar VIDEO.mp4 [--trans VIDEO_transcripcion.json]
        -> transcribe en modo --subtitulos (texto puntuado; si no le das --trans), aplica editor/glosario.json, agrupa en bloques y escribe
           VIDEO.subtitulos.json + lo imprime. REVÍSALO: corrige el "texto" de cada bloque si hace falta.
    python subtitular.py quemar VIDEO.mp4 [--salida OTRO.mp4]
        -> quema los subtítulos de VIDEO.subtitulos.json y escribe VIDEO_subtitulado.mp4 (por defecto).

Estilo (medido píxel a píxel en el ideal):
  - caja negra opaca de 107 px de alto, esquinas de radio 16, margen lateral de 20 px, centrada en x=540;
    vertical de 619 a 725 (centro 672), justo sobre la unión entre la cara (0-647) y la pantalla;
  - Inter Bold 52 px; palabra ya dicha en BLANCO (255), palabra por decir en GRIS (80);
  - bloques de 1-5 palabras y como mucho ~24 caracteres; se corta tras . ? ! ; cada bloque ~1 s en pantalla;
  - cada palabra se pone blanca cuando empieza a decirse; el bloque aparece con su primera palabra y sigue hasta
    que empieza el siguiente.
Se dibuja con Pillow (no con drawtext/libass de ffmpeg: en el build de Windows se cuelgan por fontconfig).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_desde_toma import FFMPEG, FFPROBE  # noqa: E402

EDITOR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FUENTE = os.path.join(EDITOR, "fuentes", "Inter.ttf")
GLOSARIO = os.path.join(EDITOR, "glosario.json")

W = 1080
ESTILO = {
    "tam": 52, "peso": 700, "caja_y0": 619, "caja_alto": 107, "radio": 16, "margen": 20,
    "blanco": (255, 255, 255, 255), "gris": (80, 80, 80, 255), "caja": (0, 0, 0, 255),
    "max_chars": 24, "max_palabras": 5, "max_dur": 1.6, "hueco_corte": 0.45, "fps": 60,
}
FIN_FRASE = re.compile(r"[.!?…]$")


# ---------- texto ----------
def palabras_de(trans):
    segs = trans["segmentos"] if isinstance(trans, dict) else trans
    out = []
    for s in segs:
        for w in s["words"]:
            t = w[2].strip()
            if t:
                out.append([float(w[0]), float(w[1]), t])
    return out


def aplicar_glosario(ws):
    """Reemplazos por frase sobre la secuencia de palabras, conservando tiempos (si cambia el número de palabras,
    se reparte el tiempo del tramo en proporción a la longitud)."""
    if not os.path.exists(GLOSARIO):
        return ws
    reglas = json.load(open(GLOSARIO, encoding="utf-8"))["reemplazos"]
    for patron, nuevo in reglas:
        rx = re.compile(patron, re.IGNORECASE)
        cambiado = True
        while cambiado:
            cambiado = False
            texto, pos = "", []
            for i, w in enumerate(ws):
                if texto:
                    texto += " "
                pos.append((len(texto), len(texto) + len(w[2])))
                texto += w[2]
            for m in rx.finditer(texto):
                if m.group(0) == nuevo:
                    continue
                i0 = next(i for i, (a, b) in enumerate(pos) if b > m.start())
                i1 = next(i for i, (a, b) in enumerate(pos) if b >= m.end())
                pre = ws[i0][2][: m.start() - pos[i0][0]]
                suf = ws[i1][2][m.end() - pos[i1][0]:]
                nuevas = nuevo.split()
                nuevas[0] = pre + nuevas[0]
                nuevas[-1] = nuevas[-1] + suf
                t0, t1 = ws[i0][0], ws[i1][1]
                tot = sum(len(x) for x in nuevas)
                rep, t = [], t0
                for x in nuevas:
                    d = (t1 - t0) * len(x) / tot
                    rep.append([t, t + d, x])
                    t += d
                ws = ws[:i0] + rep + ws[i1 + 1:]
                cambiado = True
                break
    # mayúscula tras fin de frase y al principio
    for i, w in enumerate(ws):
        if i == 0 or FIN_FRASE.search(ws[i - 1][2]):
            w[2] = w[2][:1].upper() + w[2][1:]
    return ws


def agrupar(ws, e=ESTILO):
    bloques, cur = [], []
    for i, w in enumerate(ws):
        if cur:
            texto = " ".join(x[2] for x in cur + [w])
            if (len(texto) > e["max_chars"] or len(cur) >= e["max_palabras"]
                    or w[1] - cur[0][0] > e["max_dur"] or w[0] - cur[-1][1] > e["hueco_corte"]):
                bloques.append(cur)
                cur = []
        cur.append(w)
        if FIN_FRASE.search(w[2]):
            bloques.append(cur)
            cur = []
    if cur:
        bloques.append(cur)
    # evita huérfanas: una palabra suelta que cabe en el bloque anterior (misma frase) se une a él
    out = []
    for b in bloques:
        if (len(b) == 1 and out and not FIN_FRASE.search(out[-1][-1][2])
                and len(" ".join(x[2] for x in out[-1] + b)) <= e["max_chars"] + 4 and b[0][0] - out[-1][-1][1] < 0.3):
            out[-1] = out[-1] + b
        else:
            out.append(b)
    return out


def preparar(a):
    base = os.path.splitext(a.video)[0]
    trans = a.trans
    if not trans:
        trans = base + "_transcripcion.json"
        if not os.path.exists(trans):
            subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(__file__), "transcribir.py"), a.video,
                            "--subtitulos", "--salida", base + "_transcripcion"], check=True)
    ws = aplicar_glosario(palabras_de(json.load(open(trans, encoding="utf-8"))))
    bloques = agrupar(ws)
    data = {"video": os.path.basename(a.video), "estilo": "ideal-2026-11-19",
            "_instrucciones": "Revisa 'texto' de cada bloque. Si cambias el número de palabras, los tiempos se reparten "
                              "solos dentro del bloque. No toques 'ini'/'fin' salvo que un bloque esté desfasado.",
            "bloques": [{"ini": round(b[0][0], 3), "fin": round(b[-1][1], 3), "texto": " ".join(w[2] for w in b),
                         "palabras": [[round(w[0], 3), round(w[1], 3), w[2]] for w in b]} for b in bloques]}
    out = base + ".subtitulos.json"
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for i, b in enumerate(data["bloques"], 1):
        print(f"{i:3d} {b['ini']:6.2f}-{b['fin']:6.2f}  {b['texto']}")
    print(f"\n{len(bloques)} bloques -> {out}\nREVISA el texto antes de quemar (términos técnicos, nombres, tildes).")


# ---------- render ----------
def fuente(e):
    from PIL import ImageFont
    f = ImageFont.truetype(FUENTE, e["tam"])
    try:
        f.set_variation_by_axes([32, e["peso"]])  # Inter variable: (opsz, wght)
    except Exception:
        pass
    return f


def estado_png(palabras, n_blancas, f, e, ruta):
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
    data = json.load(open(base + ".subtitulos.json", encoding="utf-8"))
    dur = float(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", a.video], capture_output=True, text=True, check=True).stdout)
    f = fuente(e)
    tmp = tempfile.mkdtemp(prefix="subs_")
    vacio = os.path.join(tmp, "vacio.png")
    Image.new("RGBA", (W, e["caja_alto"]), (0, 0, 0, 0)).save(vacio)
    # línea de tiempo de estados: (inicio, png)
    estados = [(0.0, vacio)]
    bl = data["bloques"]
    for bi, b in enumerate(bl):
        ws = b["palabras"]
        textos = b["texto"].split()
        if len(textos) != len(ws):  # texto corregido con otro número de palabras: reparte los tiempos del bloque
            t0, t1 = ws[0][0], ws[-1][1]
            tot = sum(len(x) for x in textos)
            ws, t = [], t0
            for x in textos:
                dd = (t1 - t0) * len(x) / tot
                ws.append([t, t + dd, x])
                t += dd
        for k in range(len(ws) + 1):
            if k == 0:
                t = ws[0][0] - 0.03
            else:
                t = ws[k - 1][0]
            if k == 0 and estados and t <= estados[-1][0] + 1e-3:
                continue
            ruta = os.path.join(tmp, f"b{bi:03d}_{k:02d}.png")
            estado_png(textos, k, f, e, ruta)
            estados.append((max(0.0, t), ruta))
        fin = bl[bi + 1]["palabras"][0][0] - 0.03 if bi + 1 < len(bl) else b["palabras"][-1][1] + 0.25
        if bi + 1 < len(bl) and bl[bi + 1]["palabras"][0][0] - b["palabras"][-1][1] > 0.8:
            fin = b["palabras"][-1][1] + 0.25  # pausa larga: el subtítulo no se queda colgado
        estados.append((min(fin, dur), vacio))
    # ffconcat con duraciones redondeadas a fotogramas
    estados.sort(key=lambda x: x[0])
    q = lambda t: round(t * e["fps"]) / e["fps"]
    lista = os.path.join(tmp, "lista.txt")
    with open(lista, "w", encoding="utf-8") as fh:
        fh.write("ffconcat version 1.0\n")
        for i, (t, png) in enumerate(estados):
            t1 = estados[i + 1][0] if i + 1 < len(estados) else dur
            d = q(t1) - q(t)
            if d <= 0:
                continue
            fh.write(f"file '{png.replace(os.sep, '/')}'\nduration {d:.6f}\n")
        fh.write(f"file '{vacio.replace(os.sep, '/')}'\n")
    salida = a.salida or base + "_subtitulado.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", a.video, "-f", "concat", "-safe", "0", "-i", lista,
                    "-filter_complex", f"[1:v]fps={e['fps']},format=rgba[s];[0:v][s]overlay=0:{e['caja_y0']}:"
                    f"eof_action=pass:format=auto,format=yuv420p[v]", "-map", "[v]", "-map", "0:a", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "16", "-c:a", "copy", "-movflags", "+faststart", salida], check=True)
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
