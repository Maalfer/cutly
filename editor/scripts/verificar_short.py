#!/usr/bin/env python3
"""
verificar_short.py — Comprueba un Short FINAL contra la especificación del Short ideal aprobado por el usuario
(editor/SHORT-IDEAL.md). Cada comprobación mide algo que puede fallar; no hay nada "a ojo".

    python verificar_short.py VIDEO.mp4          # imprime OK/FALLA por punto; código de salida 1 si algo falla

Referencia: short_Entrar-Por-SSH-Sin-Saber-La-Contrasena_editado.mp4 (2026-11-19), que pasa todo.
"""
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_desde_toma import FFMPEG, FFPROBE  # noqa: E402

PADTOP = 648


def probe(v):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate,sample_rate:format=duration", "-of", "json", v],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    v = sys.argv[1]
    res = []

    def chk(ok, nombre, detalle):
        res.append(ok)
        print(f"[{'OK   ' if ok else 'FALLA'}] {nombre}: {detalle}")

    p = probe(v)
    vs = [s for s in p["streams"] if s["codec_type"] == "video"][0]
    aus = [s for s in p["streams"] if s["codec_type"] == "audio"]
    dur = float(p["format"]["duration"])
    chk(vs["width"] == 1080 and vs["height"] == 1920 and vs["r_frame_rate"] == "60/1", "formato",
        f"{vs['width']}x{vs['height']} @ {vs['r_frame_rate']} (debe ser 1080x1920 @ 60/1)")
    chk(bool(aus), "audio", "presente (voz del usuario)" if aus else "SIN audio")
    chk(dur <= 90, "duración", f"{dur:.1f} s (referencia 73 s; un Short al grano no debería pasar de ~90 s)")

    # banda de la cara: las filas 0-647 tienen imagen (cara) en todos los fotogramas
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", v, "-vf", f"fps=5,crop=1080:{PADTOP}:0:0,scale=108:{PADTOP},"
                          "format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, PADTOP, 108)
    cuerpo = f[:-3]  # los últimos fotogramas son el fundido a negro
    negras = (cuerpo.max(axis=2) < 24)
    malos = int(negras[:, PADTOP - 10:].any(axis=1).sum())
    chk(malos == 0, "banda de la cara", f"{len(cuerpo)} fotogramas; con fila negra en {PADTOP - 10}-{PADTOP - 1}: {malos} "
        f"(la cara debe llenar exactamente 0-{PADTOP - 1})")

    # fundido final
    raw = subprocess.run([FFMPEG, "-v", "error", "-sseof", "-1", "-i", v, "-vf", "scale=54:96,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    b = np.frombuffer(raw, np.uint8).reshape(-1, 96 * 54).mean(axis=1)
    chk(b[-1] < 0.15 * b[: len(b) // 2].mean(), "fundido final",
        f"brillo último fotograma {b[-1]:.0f} frente a {b[: len(b) // 2].mean():.0f} (debe acabar en negro, ~0,25 s)")

    # audio: silencio inicial, pausas, cola final
    if aus:
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", v, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        n = len(a) // 160
        fr = a[: n * 160].reshape(n, 160)
        rms = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
        hf = 20 * np.log10(np.sqrt((np.diff(fr, axis=1) ** 2).mean(1)) + 1e-9)
        # umbral relativo al nivel de la voz (el vídeo ya está normalizado a -14 LUFS)
        thr = np.percentile(rms, 90) - 22
        voz = (rms > thr) | (hf > np.percentile(hf, 90) - 20)
        ini = int(np.argmax(voz)) * 10
        fin = (n - int(np.argmax(voz[::-1]))) * 10
        chk(ini <= 120, "arranque", f"primera voz a {ini} ms (el gancho empieza en la primera sílaba, ≤ 120 ms)")
        pausas, s = [], None
        for i, x in enumerate(voz):
            if not x and s is None:
                s = i
            if x and s is not None:
                pausas.append((s / 100, (i - s) * 10))
                s = None
        largas = [q for q in pausas if q[1] > 400]
        mx = max((q[1] for q in pausas), default=0)
        chk(not largas, "pausas", f"máx {mx} ms; > 400 ms: " +
            (", ".join(f"{t:.1f}s ({d} ms)" for t, d in largas[:8]) if largas else "ninguna") +
            " (estilo del usuario: sin pausas de respiro ni dramáticas)")
        cola = n * 10 - fin
        chk(cola <= 450, "final", f"{cola} ms entre la última palabra y el final (corte justo + fundido)")
        med = subprocess.run([FFMPEG, "-v", "info", "-i", v, "-vn", "-af", "loudnorm=print_format=json", "-f", "null",
                              "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        m = json.loads(med[med.rindex("{"):med.rindex("}") + 1])
        li, tp = float(m["input_i"]), float(m["input_tp"])
        chk(-15.0 <= li <= -13.0 and tp <= -0.5, "volumen",
            f"{li:.1f} LUFS, pico {tp:.1f} dBTP (objetivo -14 LUFS, pico ≤ -1 dBTP; se tolera -0,5 por el AAC)")

    print("\nRESULTADO:", "cumple la especificación del Short ideal" if all(res) else
          f"{res.count(False)} punto(s) por corregir (ver editor/SHORT-IDEAL.md)")
    sys.exit(0 if all(res) else 1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
