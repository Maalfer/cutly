#!/usr/bin/env python3
"""
construir_short.py — Monta un SHORT vertical 1080x1920@60 con hueco para la cara desde GRABACIONES SUELTAS (sin
registro de pasos; si la toma viene de crear-shorts, usa short_desde_toma.py), según un PLAN JSON:

    python editor/shorts/construir_short.py editor/crudo/short_plan.json

Plan (plantilla con todos los campos: editor/shorts/plantillas/short_manual.ejemplo.json):
    {"salida": ..., "fuentes": {etiqueta: archivo}, "segmentos": [...], "vbitrate": "8M", "abitrate": "128k"}
    segmento de vídeo: src, start, end, cx, cy, cw, ch (+ panx para un paneo); imagen fija: src, img_dur, cw, ch.

Implementa la metodologia de 'editor/shorts/METODOLOGIA-SHORTS.md':
  - Banda negra superior CONSTANTE (padtop) en todos los planos = donde va la cara.
  - Cada plano = recorte de una fuente escalado a 1080 de ancho y pegado bajo la banda.
  - Paneo horizontal opcional por plano (para mostrar contenido ancho a tamano completo).
  - Varias fuentes de video + imagenes fijas, todo en UNA pasada de ffmpeg.
  - Pista de audio MUDA (el usuario graba la voz en off despues).
Ya no se edita este script por cada vídeo: cada vídeo tiene su plan (local, en editor/crudo/).
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import archivos, formato  # noqa: E402
from nucleo.ffmpeg import FFMPEG, FFPROBE, salida_atomica  # noqa: E402
from nucleo.rutas import REPO  # noqa: E402

PADTOP = formato.BANDA_CARA      # banda negra superior (la cara): 648. CONSTANTE en todos los planos.
CANVAS_W = formato.ANCHO
CANVAS_H = formato.ALTO
FPS = formato.FPS


def construir(plan):
    """Monta el Short del plan; devuelve la ruta de salida."""
    SOURCES = {k: _abs(v) for k, v in plan["fuentes"].items()}
    SEGS = plan["segmentos"]
    OUT = _abs(plan["salida"])
    VBITRATE = plan.get("vbitrate", "8M")   # ajustar a ~1.5-2x el bitrate nativo de la fuente (ver ffprobe)
    ABITRATE = plan.get("abitrate", "128k")
    faltan = [p for p in SOURCES.values() if not os.path.exists(p)]
    if faltan:
        sys.exit("no existen: " + ", ".join(faltan))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # mapear etiquetas de fuente a indices de -i, imagenes aparte (se cargan con -loop)
    # separar: para imagenes usamos -loop 1; se anaden como inputs propios en orden de uso
    inputs = []          # lista de (args_de_input, label_para_ffmpeg)
    label_to_idx = {}
    idx = 0
    # primero las fuentes de video (un input cada una)
    for lab, path in SOURCES.items():
        if any(seg["src"] == lab and "img_dur" not in seg for seg in SEGS):
            inputs.append((["-i", path], lab))
            label_to_idx[lab] = idx; idx += 1
    # imagenes: un input -loop por CADA segmento de imagen (duracion propia)
    img_seg_input = {}
    for n, seg in enumerate(SEGS):
        if "img_dur" in seg:
            path = SOURCES[seg["src"]]
            inputs.append((["-loop", "1", "-framerate", str(FPS), "-t", str(seg["img_dur"]), "-i", path], f"img{n}"))
            img_seg_input[n] = idx; idx += 1

    F = ""; concat = ""; tot = 0.0
    for n, seg in enumerate(SEGS):
        cw, ch = seg["cw"], seg["ch"]
        dw = CANVAS_W
        dh = round(ch * dw / cw)               # alto escalado manteniendo proporcion
        if dh > CANVAS_H - PADTOP:
            sys.exit(f"segmento {n}: {cw}x{ch} escalado a 1080 mide {dh} px de alto y no cabe bajo la banda "
                     f"({CANVAS_H - PADTOP} px): usa una proporcion cw:ch >= 816:961")
        pad = f"pad={CANVAS_W}:{CANVAS_H}:0:{PADTOP}:black"
        if "img_dur" in seg:
            si = f"[{img_seg_input[n]}:v]"
            chain = (f"{si}trim=start=0:end={seg['img_dur']},setpts=PTS-STARTPTS,"
                     f"scale={dw}:{dh}:flags=lanczos,setsar=1,{pad},fps={FPS},format=yuv420p[v{n}];")
            tot += seg["img_dur"]
        else:
            s, e = seg["start"], seg["end"]
            si = f"[{label_to_idx[seg['src']]}:v]"
            if "panx" in seg:                  # PANEO: x se mueve de cx a panx a lo largo del segmento
                dur = e - s
                slope = (seg["panx"] - seg["cx"]) / dur
                crop = f"crop=w={cw}:h={ch}:x='{seg['cx']}+{slope:.4f}*t':y={seg['cy']}"
            else:
                crop = f"crop={cw}:{ch}:{seg['cx']}:{seg['cy']}"
            chain = (f"{si}trim=start={s}:end={e},setpts=PTS-STARTPTS,{crop},"
                     f"scale={dw}:{dh}:flags=lanczos,setsar=1,{pad},fps={FPS},format=yuv420p[v{n}];")
            tot += e - s
        F += chain; concat += f"[v{n}]"
    F += f"{concat}concat=n={len(SEGS)}:v=1:a=0[outv]"
    tot = round(tot, 3)

    cmd = [FFMPEG, "-v", "error", "-y"]
    for args, _ in inputs:
        cmd += args
    cmd += ["-f", "lavfi", "-t", str(tot), "-i", "anullsrc=r=48000:cl=stereo"]
    audio_idx = len(inputs)
    cmd += ["-filter_complex", F, "-map", "[outv]", "-map", f"{audio_idx}:a",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "slow",
            "-b:v", VBITRATE, "-maxrate", f"{float(VBITRATE[:-1])*1.1:.1f}M", "-bufsize", f"{float(VBITRATE[:-1])*2:.0f}M",
            "-c:a", "aac", "-b:a", ABITRATE, "-movflags", "+faststart", "-shortest"]

    print(f"[construir_short] {len(SEGS)} segmentos, duracion esperada {tot}s -> {OUT}", file=sys.stderr)
    # a OUT directo no: un corte a medias (memoria, Ctrl+C...) dejaría un .mp4 roto con el nombre bueno
    salida_atomica(cmd, OUT, check=True)
    d = subprocess.check_output([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nw=1:nk=1", OUT]).decode().strip()
    print(f"[construir_short] LISTO. Duracion real: {d}s", file=sys.stderr)
    print("[construir_short] VERIFICA: banda superior constante, uniones y paneos con fotogramas.", file=sys.stderr)
    return OUT


def _abs(ruta):
    return ruta if os.path.isabs(ruta) else os.path.join(REPO, ruta)


def main():
    ap = argparse.ArgumentParser(description="Short mudo 1080x1920 con banda para la cara, desde grabaciones sueltas "
                                             "(sin registro de pasos), según un plan JSON.")
    ap.add_argument("plan", help="plan JSON (plantilla: editor/shorts/plantillas/short_manual.ejemplo.json)")
    construir(archivos.leer_json(ap.parse_args().plan))


if __name__ == "__main__":
    main()
