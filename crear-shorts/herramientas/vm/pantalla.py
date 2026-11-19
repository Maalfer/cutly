"""VER: capturas del invitado (VBoxManage, sin SSH), OCR (Tesseract o Vision) y esperas por texto o por quietud."""
import hashlib
import os
import subprocess
import time

import ocr_buscar

from .anfitrion import find_tesseract, vbox
from .config import IS_WIN, TMP, VM, die
from .registro import focus, logged


def shot(path=None):
    path = path or os.path.join(TMP, "vm.png")
    vbox("controlvm", VM, "screenshotpng", path)
    return path


def _tess_tsv(tess, png, scale=1.0, ox=0, oy=0):
    r = subprocess.run([tess, png, "-", "--psm", "11", "tsv"], capture_output=True, text=True, encoding="utf-8")
    out = []
    for ln in r.stdout.splitlines()[1:]:
        c = ln.split("\t")
        if len(c) >= 12 and c[0] == "5" and c[11].strip() and float(c[10]) >= 0:
            x, y, w, h = (int(float(c[i]) / scale) for i in (6, 7, 8, 9))
            out.append((c[11].strip(), x + ox, y + oy, w, h))
    return out


def _ocr_words(png, region=None, thorough=False):
    r"""Salida común: '<palabra>\t[x,y WxH]' en píxeles del invitado.
    region=(x,y,w,h) acelera (requiere Pillow). thorough=True añade una segunda pasada con la imagen
    ampliada x2 y en canal mínimo RGB, que lee el texto claro sobre botones de color ("Next", "I Accept") que la pasada
    normal no ve (medido: Tesseract no encontraba 'Next' blanco sobre naranja en Burp)."""
    ox = oy = 0
    rs = 1.0                       # factor de ampliación de la pasada normal (solo con región: Tesseract falla en franjas pequeñas)
    if region:
        try:
            from PIL import Image
            im = Image.open(png)
            ox, oy = int(region[0]), int(region[1])
            png = os.path.join(TMP, "_vmreg.png")
            cr = im.crop((ox, oy, ox + int(region[2]), oy + int(region[3])))
            rs = 3.0
            cr.resize((int(cr.width * rs), int(cr.height * rs)), Image.LANCZOS).save(png)
        except ImportError:
            ox = oy = 0
    ctrl = os.path.expanduser("~/Desktop/ctrl-kit/ocr")
    if os.environ.get("VM_OCR") != "tesseract" and not IS_WIN and os.access(ctrl, os.X_OK):
        return subprocess.run([ctrl, "--words", png], capture_output=True, text=True).stdout
    tess = find_tesseract()
    if not tess:
        die("falta Tesseract (Windows: winget install UB-Mannheim.TesseractOCR; ver PORTABILIDAD.md)")
    words = _tess_tsv(tess, png, rs, ox, oy)
    if thorough:
        try:
            from PIL import Image, ImageChops
            # Canal MÍNIMO de R,G,B: el blanco (255,255,255) se queda en 255 y un naranja/azul cae a su canal más
            # bajo, así el texto claro sobre botón de color gana contraste. (Probado: gris/invertido NO lo lee.)
            r, g, b = Image.open(png).convert("RGB").split()
            im = ImageChops.darker(ImageChops.darker(r, g), b)
            im = im.resize((int(im.width * 2 / rs), int(im.height * 2 / rs)), Image.LANCZOS)   # (png ya viene ×rs)
            alt = os.path.join(TMP, "_vminv.png")
            im.save(alt)
            for w in _tess_tsv(tess, alt, 2.0, ox, oy):
                if not any(w[0].lower() == o[0].lower() and abs(w[1] - o[1]) < 10 and abs(w[2] - o[2]) < 10 for o in words):
                    words.append(w)
        except ImportError:
            pass
    return "\n".join(f"{t}\t[{x},{y} {w}x{h}]" for t, x, y, w, h in words) + "\n"


def _words_text(png=None, region=None, thorough=False):
    return " ".join(l.split("\t")[0] for l in _ocr_words(png or shot(), region, thorough).splitlines() if "\t" in l).lower()


@logged("waitfor")
def waitfor(text, seg=20, region=None):
    t0 = time.time()
    want = text.lower()
    first = ocr_buscar.norm(want.split()[0]) if want.split() else ""
    while time.time() - t0 < seg:
        png = shot()
        for thorough in (False, True):
            lines = _ocr_words(png, region, thorough).splitlines(True)
            joined = " ".join(l.split("	")[0] for l in lines if "	" in l).lower()
            if want in joined:
                # dónde se vio el texto -> foco para el encuadre del Short
                for modo in ("exacta", "contiene"):
                    r = ocr_buscar.buscar(lines, first, 1, 1.0, region, "", modo) if len(first) >= 3 else None
                    if r:
                        x, y = (int(v) for v in r.split(","))
                        focus(x, y, f"waitfor:{text[:30]}")
                        break
                return True
        time.sleep(0.4)
    return False


def waitstill(seg=10, every=0.5, tol=0.002, top=40):
    """Espera a que la pantalla deje de cambiar. Compara dos capturas seguidas por FRACCIÓN de píxeles distintos
    (< tol) e ignora la franja superior (`top` px): el panel de Kali tiene un gráfico de CPU animado y el cursor de
    texto parpadea, y con una comparación exacta nunca se estabilizaba (medido). Sin Pillow/numpy cae a hash exacto."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        np = None
    t0, prev = time.time(), None
    while time.time() - t0 < seg:
        png = shot(os.path.join(TMP, "_still.png"))
        if np:
            cur = np.asarray(Image.open(png).convert("L"))[top:]
            if prev is not None and prev.shape == cur.shape and float((np.abs(cur.astype(int) - prev) > 24).mean()) < tol:
                return True
            prev = cur.astype(int)
        else:
            with open(png, "rb") as fh:
                h = hashlib.md5(fh.read()).hexdigest()
            if h == prev:
                return True
            prev = h
        time.sleep(every)
    return False


def waitgone(text, seg=6):
    t0 = time.time()
    while time.time() - t0 < seg:
        if text.lower() not in _words_text():
            return True
        time.sleep(0.5)
    return False
