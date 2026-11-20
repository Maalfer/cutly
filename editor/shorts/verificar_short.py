#!/usr/bin/env python3
"""
verificar_short.py — Comprueba un Short FINAL contra la especificación del Short ideal aprobado por el usuario
(editor/shorts/SHORT-IDEAL.md). Cada comprobación mide algo que puede fallar; no hay nada "a ojo".

    python editor/shorts/verificar_short.py VIDEO.mp4 [--sin-subtitulos]   # OK/FALLA por punto; código de salida 1 si algo falla

--sin-subtitulos: para un paso intermedio (el Short montado, antes de subtitular.py quemar).

Referencia: short_Entrar-Por-SSH-Sin-Saber-La-Contrasena_editado.mp4 (2026-11-19), que pasa todo.
"""
import argparse
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import audio, formato, medios, series  # noqa: E402
from nucleo.ffmpeg import FFMPEG, temporales_de  # noqa: E402

PADTOP = formato.BANDA_CARA


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--sin-subtitulos", action="store_true")
    args = ap.parse_args()
    v = args.video
    res = []

    def chk(ok, nombre, detalle):
        res.append(ok)
        print(f"[{'OK   ' if ok else 'FALLA'}] {nombre}: {detalle}")

    # ¿es de verdad el vídeo recién montado? Con un temporal al lado, se está rehaciendo o el último montaje falló
    # (pasó: se verificó el Short VIEJO porque el nuevo no pudo reemplazarlo y el error se perdió en un "| grep").
    import time
    hace = time.time() - os.path.getmtime(v)
    print(f"vídeo: {v} (escrito a las {time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(v)))}, "
          f"hace {hace / 60:.0f} min)")
    tmp = temporales_de(v)
    chk(not tmp, "montaje terminado", "sin temporales al lado" if not tmp else
        f"hay {', '.join(os.path.basename(t) for t in tmp)}: se está rehaciendo o el último montaje FALLÓ, así que "
        f"esto mediría la versión anterior. Mira el error del montaje y repítelo")

    p = medios.info(v)
    vs = [s for s in p["streams"] if s["codec_type"] == "video"][0]
    aus = [s for s in p["streams"] if s["codec_type"] == "audio"]
    dur = float(p["format"]["duration"])
    chk(vs["width"] == 1080 and vs["height"] == 1920 and vs["r_frame_rate"] == "60/1", "formato",
        f"{vs['width']}x{vs['height']} @ {vs['r_frame_rate']} (debe ser 1080x1920 @ 60/1)")
    chk(bool(aus), "audio", "presente (voz del usuario)" if aus else "SIN audio")
    chk(dur <= 90, "duración", f"{dur:.1f} s (referencia 73 s; un Short al grano no debería pasar de ~90 s)")

    # banda de la cara: las filas 0-647 tienen imagen (cara) en todos los fotogramas
    f = medios.fotogramas_gris(v, 5, (formato.ANCHO, PADTOP, 0, 0), (108, PADTOP))
    cuerpo = f[:-3]  # los últimos fotogramas son el fundido a negro
    negras = (cuerpo.max(axis=2) < 24)
    malos = int(negras[:, PADTOP - 10:].any(axis=1).sum())
    chk(malos == 0, "banda de la cara", f"{len(cuerpo)} fotogramas; con fila negra en {PADTOP - 10}-{PADTOP - 1}: {malos} "
        f"(la cara debe llenar exactamente 0-{PADTOP - 1})")

    # subtítulos: la caja negra (filas 619-725, centrada) presente mientras se habla. Se mira la franja 621-646, que
    # es caja sin letras (las letras van de ~652 a ~700): sin subtítulos ahí se ve la cara, nunca negro puro.
    if not args.sin_subtitulos:
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", v, "-vf", "fps=5,crop=40:26:520:621", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        s = np.frombuffer(raw, np.uint8).reshape(-1, 26 * 40 * 3)
        con = float((s[:-3].max(axis=1) <= 10).mean())
        chk(con >= 0.85, "subtítulos", f"caja de subtítulo en el {con * 100:.0f} % de los fotogramas (≥ 85 %; "
            f"generarlos: editor/shorts/subtitular.py; si es un paso intermedio, usa --sin-subtitulos)")

    # fundido final
    raw = subprocess.run([FFMPEG, "-v", "error", "-sseof", "-1", "-i", v, "-vf", "scale=54:96,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    b = np.frombuffer(raw, np.uint8).reshape(-1, 96 * 54).mean(axis=1)
    chk(b[-1] < 0.15 * b[: len(b) // 2].mean(), "fundido final",
        f"brillo último fotograma {b[-1]:.0f} frente a {b[: len(b) // 2].mean():.0f} (debe acabar en negro, ~0,25 s)")

    # audio: silencio inicial, pausas, cola final
    if aus:
        rms, hf = audio.energia(medios.audio_mono(v))       # ventanas de 10 ms
        n = len(rms)
        # umbral relativo al nivel de la voz (el vídeo ya está normalizado a -14 LUFS)
        thr = np.percentile(rms, 90) - 22
        voz = (rms > thr) | (hf > np.percentile(hf, 90) - 20)
        ini = int(np.argmax(voz)) * 10
        fin = (n - int(np.argmax(voz[::-1]))) * 10
        chk(ini <= 120, "arranque", f"primera voz a {ini} ms (el gancho empieza en la primera sílaba, ≤ 120 ms)")
        # pausas = silencios ENTRE voz (el silencio tras la última palabra es la cola, se mide aparte)
        pausas = [(i0 / 100, (i1 - i0) * 10) for i0, i1 in series.rachas(~voz, 1) if i1 < n]
        largas = [q for q in pausas if q[1] > 400]
        mx = max((q[1] for q in pausas), default=0)
        chk(not largas, "pausas", f"máx {mx} ms; > 400 ms: " +
            (", ".join(f"{t:.1f}s ({d} ms)" for t, d in largas[:8]) if largas else "ninguna") +
            " (estilo del usuario: sin pausas de respiro ni dramáticas)")
        cola = n * 10 - fin
        chk(cola <= 450, "final", f"{cola} ms entre la última palabra y el final (corte justo + fundido)")
        m = audio.medir_sonoridad(v)
        li, tp = float(m["input_i"]), float(m["input_tp"])
        chk(-15.0 <= li <= -13.0 and tp <= -0.5, "volumen",
            f"{li:.1f} LUFS, pico {tp:.1f} dBTP (objetivo -14 LUFS, pico ≤ -1 dBTP; se tolera -0,5 por el AAC)")

    print("\nRESULTADO:", "cumple la especificación del Short ideal" if all(res) else
          f"{res.count(False)} punto(s) por corregir (ver editor/shorts/SHORT-IDEAL.md)")
    sys.exit(0 if all(res) else 1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
