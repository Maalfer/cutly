#!/usr/bin/env python3
"""
analizar_fusion.py — Mide todo lo necesario para fusionar CARA (cara + voz del usuario) con PANTALLA (Short ya
construido) antes de decidir un solo corte. Metodología: editor/METODOLOGIA-FUSION-CARA.md.

    python analizar_fusion.py informe CARA.mp4 PANTALLA.mp4 [--trans CARA_transcripcion.json] [--salida informe.md]
    python analizar_fusion.py energia CARA.mp4 T0 T1        # energía a 10 ms para afinar un corte entre palabras

`informe` mide, sin mirar nada a ojo:
  1. CARA: alto real de la banda de la cara (filas con imagen antes del negro) y tramos donde la parte de abajo de
     la grabación de cara NO está en negro (el usuario enseña su propia pantalla: se conserva en el montaje).
  2. PANTALLA: alto de la banda negra superior (padtop, debe ser 648) y eventos: cambios grandes (Enter, salida
     de un comando, cambio de plano) y tramos quietos (> 2 s).
  3. VOZ: bloques de voz por energía (la verdad física: Whisper inventa texto en silencios y se salta frases).
  4. Con --trans (de transcribir.py): el texto de cada bloque y AVISOS de tomas repetidas (dos bloques que empiezan
     igual) y de voz sin texto (posible falso arranque que Whisper se tragó).

`energia` imprime, cada 10 ms, el nivel (rms) y la energía de alta frecuencia (hf): una sibilante final ("pass")
tiene rms bajo pero hf alto, así que el final real de la palabra es donde cae el hf, no donde cae el rms.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_desde_toma import FFMPEG, FFPROBE  # noqa: E402

NEGRO = 24  # valor de gris por debajo del cual una fila cuenta como negra


def dur(path):
    return float(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True, check=True).stdout.strip())


def frames_gray(path, fps, crop, scale):
    """Devuelve (n, h, w) uint8 de un recorte escalado, a `fps` fotogramas por segundo."""
    cw, ch, cx, cy = crop
    w, h = scale
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vf",
                          f"fps={fps},crop={cw}:{ch}:{cx}:{cy},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w)


def audio16k(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def tramos(mask, paso, minimo=0.0):
    """Convierte una máscara booleana muestreada cada `paso` s en lista de (inicio, fin)."""
    out, ini = [], None
    for i, v in enumerate(mask):
        if v and ini is None:
            ini = i
        if not v and ini is not None:
            if (i - ini) * paso >= minimo:
                out.append((ini * paso, i * paso))
            ini = None
    if ini is not None and (len(mask) - ini) * paso >= minimo:
        out.append((ini * paso, len(mask) * paso))
    return out


def banda_superior(path, n=12):
    """Alto de la banda superior: en CARA, filas con imagen; en PANTALLA, filas negras. Usa n instantes."""
    d = dur(path)
    res = []
    for k in range(n):
        t = d * (k + 0.5) / n
        raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf",
                              "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        img = np.frombuffer(raw, dtype=np.uint8).reshape(1920, 1080)
        negra = img.max(axis=1) < NEGRO
        res.append((t, negra))
    return res


def informe(a):
    L = []
    p = L.append
    # 1. CARA
    bandas = banda_superior(a.cara)
    altos, con_abajo = [], 0
    for t, negra in bandas:
        if negra[0]:
            continue
        primera_negra = int(np.argmax(negra)) if negra.any() else 1920
        if negra[primera_negra:].all():
            altos.append(primera_negra)
        else:
            con_abajo += 1
    alto_cara = int(np.median(altos)) if altos else None
    p(f"# Análisis de fusión\n\n- CARA: `{a.cara}` ({dur(a.cara):.2f} s)\n- PANTALLA: `{a.pantalla}` ({dur(a.pantalla):.2f} s)\n")
    p(f"## 1. Cara\n- Banda de la cara: filas 0-{alto_cara - 1 if alto_cara else '?'} → **alto {alto_cara} px** "
      f"(medido en {len(altos)} instantes; {con_abajo} instantes con contenido debajo).")
    if alto_cara:
        f = frames_gray(a.cara, 10, (1080, 1920 - alto_cara - 40, 0, alto_cara + 40), (54, 50))
        abajo = tramos([fr.max() >= NEGRO for fr in f], 0.1, minimo=0.5)
        if abajo:
            p("- **Tramos con contenido DEBAJO de la cara** (el usuario enseña su pantalla: se mantienen en el montaje):")
            for s, e in abajo:
                p(f"  - {s:.2f} → {e:.2f} s")
        else:
            p("- Debajo de la cara siempre negro.")
    # 2. PANTALLA
    pb = banda_superior(a.pantalla)
    pads = [int(np.argmin(negra)) for _, negra in pb if negra[0]]
    padtop = min(pads) if pads else None
    p(f"\n## 2. Pantalla\n- Primera fila con imagen: **{padtop} px** (mínimo de {len(pads)} instantes). Debe ser ≥ 648: "
      "la banda de short_desde_toma es 648 y el borde oscuro de la ventana puede sumar unos px. Si sale < 648, "
      "la cara taparía contenido: no sigas sin revisarlo.")
    if padtop and padtop >= 648:
        padtop = 648
    if padtop:
        f = frames_gray(a.pantalla, 10, (1080, 1920 - padtop, 0, padtop), (216, 254)).astype(np.int16)
        cambio = (np.abs(np.diff(f, axis=0)) > 40).sum(axis=(1, 2))
        grandes = tramos(cambio > 300, 0.1)
        quietos = tramos(cambio == 0, 0.1, minimo=2.0)
        p("- Cambios grandes (Enter, salida de comando, cambio de plano): " +
          ", ".join(f"{s + 0.1:.1f}" + (f"-{e + 0.1:.1f}" if e - s > 0.15 else "") for s, e in grandes))
        p("- Tramos quietos ≥ 2 s: " + ", ".join(f"{s + 0.1:.1f}-{e + 0.1:.1f}" for s, e in quietos))
        p("- Para saber QUÉ pasa en cada tramo: hoja de contacto cada 1-3 s (sin drawtext, ver PORTABILIDAD.md):\n"
          "  `ffmpeg -ss T -t 30 -i PANTALLA -vf \"fps=1,crop=1080:700:0:648,scale=270:-1,tile=6x5\" -frames:v 1 hoja.png`")
    # 3. VOZ
    au = audio16k(a.cara)
    paso = 0.1
    n = len(au) // int(16000 * paso)
    niveles = np.array([db(au[i * 1600:(i + 1) * 1600]) for i in range(n)])
    suelo = float(np.percentile(niveles, 20))
    umbral = max(suelo + 12, -38.0)
    bloques = []
    for s, e in tramos(niveles > umbral, paso, minimo=0.2):
        if bloques and s - bloques[-1][1] < 0.45:
            bloques[-1] = (bloques[-1][0], e)
        else:
            bloques.append((s, e))
    p(f"\n## 3. Voz (por energía)\n- Suelo de ruido ≈ {suelo:.0f} dB; umbral de voz {umbral:.0f} dB. "
      "Lo que esté por debajo es ruido de fondo aunque Whisper le ponga texto (\"Gracias\").")
    words = []
    if a.trans:
        tj = json.load(open(a.trans, encoding="utf-8"))
        segs = tj["segmentos"] if isinstance(tj, dict) else tj
        for s in segs:
            words += [(w[0], w[1], w[2]) for w in s["words"]]
    p("\n| # | Voz (s) | Dur | Texto |\n|---|---|---|---|")
    textos = []
    for i, (s, e) in enumerate(bloques, 1):
        txt = " ".join(w[2].strip() for w in words if s - 0.3 <= (w[0] + w[1]) / 2 <= e + 0.3)
        textos.append(txt)
        p(f"| {i} | {s:.1f}–{e:.1f} | {e - s:.1f} | {txt or ('**(sin texto)**' if words else '')} |")
    if words:
        avisos = []

        def norm(t):
            t = unicodedata.normalize("NFD", t.lower())
            t = "".join(c for c in t if unicodedata.category(c) != "Mn")
            return re.sub(r"[^a-z0-9 ]", " ", t).split()

        vistos = set()
        for i, ti in enumerate(textos):
            s_, e_ = bloques[i]
            if not ti:
                if e_ - s_ < 0.35:
                    avisos.append(f"- Bloque {i + 1} ({s_:.1f} s): ruido corto sin texto (chasquido, respiración, golpe): "
                                  f"deja el corte fuera de él.")
                else:
                    avisos.append(f"- Bloque {i + 1} ({s_:.1f} s): voz SIN texto → posible falso arranque tragado por "
                                  f"Whisper. Revísalo con `energia` y mira si el segmento siguiente empieza antes que su "
                                  f"primera palabra.")
                continue
            a3 = norm(ti)[:3]
            grupo = [j for j in range(i, len(textos)) if a3 and norm(textos[j])[:3] == a3]
            if len(grupo) > 1 and i not in vistos:
                vistos.update(grupo)
                avisos.append(f"- Bloques {', '.join(str(j + 1) for j in grupo)} empiezan igual (\"{' '.join(a3)}…\") → "
                              f"**tomas repetidas**: normalmente vale la ÚLTIMA (bloque {grupo[-1] + 1}); comprueba que "
                              f"las anteriores no tengan una parte que la última no repite.")
            # una frase cuyo final reaparece al principio del bloque siguiente = repitió solo la segunda mitad
            if i + 1 < len(textos) and textos[i + 1] and i + 1 not in vistos:
                b = norm(textos[i + 1])[:4]
                ni = norm(ti)
                for k in range(1, len(ni) - 3):
                    if ni[k:k + 4] == b:
                        avisos.append(f"- Bloque {i + 2} repite el final del bloque {i + 1} (desde \"{' '.join(b)}…\") → "
                                      f"usa el bloque {i + 1} hasta justo antes de esa frase y empalma con el {i + 2}.")
                        break
        p("\n## 4. Avisos de edición\n" + ("\n".join(avisos) if avisos else "- Ninguno detectado automáticamente "
                                            "(revisa igualmente la tabla: una toma repetida puede no empezar igual)."))
    p("\n## Siguiente paso\nEscribe el plan (`fusion_plan.json`) emparejando cada bloque de voz bueno con su momento de "
      "pantalla, afina cada corte con `analizar_fusion.py energia` y construye con `fusionar_cara_pantalla.py`.")
    out = "\n".join(L) + "\n"
    salida = a.salida or os.path.splitext(a.cara)[0] + ".fusion.md"
    open(salida, "w", encoding="utf-8").write(out)
    print(out)
    print(f"(informe guardado en {salida})")


def energia(a):
    au = audio16k(a.cara)
    i0, i1 = int(a.t0 * 100), int(a.t1 * 100)
    for i in range(i0, i1):
        seg = au[i * 160:(i + 1) * 160]
        if len(seg) < 2:
            break
        r = db(seg)
        hf = 20 * np.log10(np.sqrt(np.mean(np.diff(seg) ** 2)) + 1e-9)
        barra = "#" * max(0, int(r + 70) // 2)
        print(f"{i / 100:8.2f}  rms {r:5.0f}  hf {hf:5.0f}  {barra}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("informe")
    i.add_argument("cara")
    i.add_argument("pantalla")
    i.add_argument("--trans", help="JSON de transcribir.py sobre CARA")
    i.add_argument("--salida")
    e = sub.add_parser("energia")
    e.add_argument("cara")
    e.add_argument("t0", type=float)
    e.add_argument("t1", type=float)
    a = ap.parse_args()
    (informe if a.cmd == "informe" else energia)(a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
