#!/usr/bin/env python3
"""
aplicar_zoom.py — Zoom estratégico a cámara sobre un clip 16:9 YA CONSTRUIDO (editor/directos/construir_clip.sh),
según la metodología "Zoom estratégico a cámara" de editor/directos/CLAUDE.md.

    python editor/directos/aplicar_zoom.py <clip_entrada> <clip_salida> --camara X,Y,W,H \
        --zoom INICIO,FIN [--zoom INICIO,FIN ...] [--titulo Titulo-Del-Clip] [-b BITRATE]

Entrada: un clip 16:9 ya cortado (plano completo del directo, cámara+pantalla ya mezcladas por OBS). El vídeo
pasa la mayor parte del tiempo en plano completo; en los tramos --zoom se recorta la región de la cámara
(X,Y,W,H, medida a ojo con un fotograma del PROPIO clip — la posición puede cambiar de un directo a otro según
la escena de OBS de ese día, no asumas la de uno anterior) y se escala de vuelta al tamaño del lienzo. Corte
seco entre plano completo y zoom (sin transición animada), igual que el resto de la edición de este repo.

El AUDIO nunca se toca: se mapea con -c:a copy, intacto, sin micro-fundidos ni recortes — el zoom es un cambio
de encuadre, no un corte de contenido.

Los tiempos de --zoom son relativos al CLIP DE ENTRADA (su propio timeline, el que ya ha pasado por
construir_clip.sh), no al directo original. Acepta segundos (123.4) o HH:MM:SS(.ms).
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import cortes, medios  # noqa: E402
from nucleo.ffmpeg import FFMPEG, requerir, salida_atomica  # noqa: E402


def a_segundos(t):
    """'HH:MM:SS(.ms)' o un número ya en segundos -> float segundos."""
    if ":" in t:
        s = 0.0
        for p in t.split(":"):
            s = s * 60 + float(p)
        return s
    return float(t)


def escalar(valor, factor):
    """'5M'*1.1 -> '5.5M' (conserva la unidad, como el `escala` de construir_clip.sh)."""
    unidad = valor[-1] if valor[-1].isalpha() else ""
    numero = float(valor[:-1]) if unidad else float(valor)
    return f"{numero * factor:g}{unidad}"


def bitrate_nativo(path):
    """Bitrate de vídeo del propio clip de entrada (kbps), con fallback al del contenedor si el stream no lo trae."""
    for entries in ("stream=bit_rate", "format=bit_rate"):
        sel = ["-select_streams", "v:0"] if entries.startswith("stream") else []
        out = subprocess.run([requerir("ffprobe"), "-v", "error", *sel, "-show_entries", entries, "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout.strip()
        if out and out != "N/A":
            return f"{max(500, round(int(out) / 1000))}k"
    sys.exit(f"no se pudo medir el bitrate nativo de {path}: pasa -b a mano")


def tramos_zoom(zooms, dur):
    """Lista cronológica de (inicio, fin, es_zoom) cubriendo [0, dur] entero, a partir de los tramos --zoom
    (ya validados sin solapes). Los huecos entre zooms (y antes/después) quedan a plano completo."""
    tramos, cursor = [], 0.0
    for zs, ze in zooms:
        if zs > cursor:
            tramos.append((cursor, zs, False))
        tramos.append((zs, ze, True))
        cursor = ze
    if cursor < dur:
        tramos.append((cursor, dur, False))
    return [(s, e, z) for s, e, z in tramos if e - s > 0.01]   # descarta tramos degenerados (redondeo)


def construir(entrada, salida, camara, zooms, bitrate, abitrate):
    ancho, alto, dur = medios.probe_video(entrada)
    cx, cy, cw, ch = camara
    if cx < 0 or cy < 0 or cw <= 0 or ch <= 0 or cx + cw > ancho or cy + ch > alto:
        sys.exit(f"rectángulo de cámara ({cx},{cy},{cw},{ch}) se sale del frame {ancho}x{alto}")

    zooms = sorted(zooms)
    cursor = 0.0
    for zs, ze in zooms:
        if not (0 <= zs < ze <= dur + 0.05):
            sys.exit(f"zoom {zs:.2f}-{ze:.2f}s fuera de rango (el clip dura {dur:.2f}s)")
        if zs < cursor:
            sys.exit(f"zoom {zs:.2f}-{ze:.2f}s se solapa con el tramo de zoom anterior (termina en {cursor:.2f}s)")
        cursor = ze

    tramos = tramos_zoom(zooms, dur)
    partes = []
    for i, (s, e, es_zoom) in enumerate(tramos):
        base = f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS"
        if es_zoom:
            partes.append(f"{base},crop=w={cw}:h={ch}:x={cx}:y={cy},scale={ancho}:{alto}:flags=lanczos,setsar=1,format=yuv420p[v{i}]")
        else:
            partes.append(f"{base},scale={ancho}:{alto}:flags=lanczos,setsar=1,format=yuv420p[v{i}]")
        print(f"tramo {i + 1}: {s:.2f}-{e:.2f}s  {'ZOOM CAMARA' if es_zoom else 'PLANO COMPLETO'}", file=sys.stderr)
    concat = "".join(f"[v{i}]" for i in range(len(tramos))) + f"concat=n={len(tramos)}:v=1:a=0[outv]"
    filtro = ";".join(partes + [concat])

    vbit = bitrate or bitrate_nativo(entrada)
    maxrate, bufsize = escalar(vbit, 1.1), escalar(vbit, 2)

    cmd = [FFMPEG, "-v", "error", "-y", "-i", entrada, "-filter_complex", filtro,
           "-map", "[outv]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium",
           "-b:v", vbit, "-maxrate", maxrate, "-bufsize", bufsize,
           "-c:a", abitrate and "aac" or "copy"]
    if abitrate:
        cmd += ["-b:a", abitrate]
    cmd += ["-shortest"]
    r = salida_atomica(cmd, salida, capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg falló:\n" + r.stderr[-1500:])
    return tramos, dur


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada")
    ap.add_argument("salida")
    ap.add_argument("--camara", required=True, metavar="X,Y,W,H",
                    help="rectángulo de la cámara en el frame del CLIP de entrada (medido a ojo con un fotograma)")
    ap.add_argument("--zoom", action="append", required=True, metavar="INICIO,FIN", dest="zooms",
                    help="tramo (tiempos del clip de entrada) en el que se hace zoom a la cámara; repite --zoom para varios")
    ap.add_argument("--titulo", help="para la entrada del _cortes.log (por defecto, el nombre del archivo de salida)")
    ap.add_argument("-b", "--bitrate", help="bitrate de vídeo (ej. 1.5M); por defecto, el nativo del propio clip de entrada")
    ap.add_argument("-a", "--abitrate", help="si se da, reencodea el audio a este bitrate (ej. 192k) en vez de copiarlo intacto")
    a = ap.parse_args()

    if not os.path.exists(a.entrada):
        sys.exit(f"no existe {a.entrada}")
    cx, cy, cw, ch = (int(v) for v in a.camara.split(","))
    zooms = []
    for z in a.zooms:
        zs, ze = z.split(",")
        zooms.append((a_segundos(zs), a_segundos(ze)))

    tramos, dur = construir(a.entrada, a.salida, (cx, cy, cw, ch), zooms, a.bitrate, a.abitrate)

    # --- verificación obligatoria: la duración de salida debe coincidir con la de entrada (el zoom nunca corta nada)
    _, _, dsal = medios.probe_video(a.salida)
    ok_dur = abs(dsal - dur) < 0.6
    print(f"clip con zoom: {a.salida}")
    print(f"duración {dsal:.1f}s (esperada {dur:.1f}s) {'OK' if ok_dur else 'REVISAR'} | tramos: {len(tramos)} "
          f"({sum(1 for *_, z in tramos if z)} con zoom)")

    titulo = a.titulo or os.path.splitext(os.path.basename(a.salida))[0]
    entrada_log = f"\n[{datetime.now():%Y-%m-%d %H:%M}] {os.path.basename(a.salida)}  (zoom aplicado sobre '{os.path.basename(a.entrada)}', camara x={cx} y={cy} w={cw} h={ch})\n"
    for i, (s, e, es_zoom) in enumerate(tramos):
        entrada_log += f"  tramo {i + 1}: {s:.2f}-{e:.2f}s  {'ZOOM CAMARA' if es_zoom else 'PLANO COMPLETO'}\n"
    cortes.anotar(entrada_log)  # APPEND, nunca reescribir

    if not ok_dur:
        sys.exit(1)


if __name__ == "__main__":
    main()
