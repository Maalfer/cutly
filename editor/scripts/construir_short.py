#!/usr/bin/env python3
"""
construir_short.py — Monta un SHORT vertical 1080x1920@60 con hueco para la cara.

Implementa la metodologia de 'editor/METODOLOGIA-SHORTS.md':
  - Banda negra superior CONSTANTE (padtop) en todos los planos = donde va la cara.
  - Cada plano = recorte de una fuente escalado a 1080 de ancho y pegado bajo la banda.
  - Paneo horizontal opcional por plano (para mostrar contenido ancho a tamano completo).
  - Soporta varias fuentes de video + imagenes fijas, todo en UNA pasada de ffmpeg.
  - Pista de audio MUDA (el usuario graba la voz en off despues).

NO es un CLI con mil flags: es una PLANTILLA. Edita las dos zonas marcadas (CONFIG y SEGS)
y ejecutalo:  python3 construir_short.py

Requiere: ffmpeg, ffprobe, python3.
"""

import subprocess, os, sys

# ======================= CONFIG (editar) =======================
OUT = os.path.expanduser("~/Desktop/cutly/editor/videos-editados/short_EJEMPLO_editado.mp4")

# Fuentes: etiqueta -> ruta. La etiqueta se usa en SEGS.
SOURCES = {
    "intro": os.path.expanduser("~/Desktop/cutly/editor/crudo/intro.mkv"),
    "main":  os.path.expanduser("~/Desktop/cutly/editor/crudo/editar.mkv"),
    "img":   os.path.expanduser("~/Desktop/cutly/editor/crudo/imagen.jpg"),
}

PADTOP   = 648     # altura de la banda negra superior (la cara). CONSTANTE. 648/1920 = tercio sup.
CANVAS_W = 1080
CANVAS_H = 1920
FPS      = 60
VBITRATE = "8M"    # ajustar a ~1.5-2x el bitrate nativo de la fuente (ver ffprobe)
ABITRATE = "128k"

# ======================= SEGS (editar) =======================
# Cada segmento es un dict. Tipos:
#   video normal:  {"src","start","end","cx","cy","cw","ch"}
#       recorte cw x ch en (cx,cy) de la fuente, escalado a 1080 de ancho.
#       Para "llenar el marco" usa proporcion cw:ch = 816:961 (como 1080:1272).
#       Para "letterbox" (contenido ancho) usa cw mas grande; quedara negro debajo.
#   paneo:         igual + {"panx": CX_FINAL}  -> cx se desplaza de cx a panx en el tiempo.
#   imagen fija:   {"src","img_dur","cw","ch"}  (cw,ch = tamano real de la imagen)
#
# La banda superior (PADTOP) es la misma SIEMPRE: aqui no se toca.
SEGS = [
    # VALORES DE EJEMPLO (de un Short antiguo): sustitúyelos por los de tu vídeo.
    # --- INTRO ---
    {"src": "intro", "start": 2.5,  "end": 10.8, "cx": 190, "cy": 40, "cw": 816, "ch": 961},            # busqueda (desde que se teclea)
    {"src": "intro", "start": 12.8, "end": 18.0, "cx": 90,  "cy": 40, "cw": 816, "ch": 961},            # resultados
    {"src": "intro", "start": 35.8, "end": 40.3, "cx": 40,  "cy": 20, "cw": 816, "ch": 961, "panx": 330},  # comando: PANEO a tamano completo
    {"src": "img",   "img_dur": 4.5, "cw": 450, "ch": 353},                                             # imagen fija (letterbox, banda arriba constante)
    # --- EJERCICIO ---
    {"src": "main",  "start": 230.0, "end": 236.0, "cx": 552, "cy": 8,   "cw": 816, "ch": 961},
    {"src": "main",  "start": 258.0, "end": 265.0, "cx": 552, "cy": 8,   "cw": 816, "ch": 961},
    {"src": "main",  "start": 327.5, "end": 333.0, "cx": 135, "cy": 2,   "cw": 816, "ch": 961},
    {"src": "main",  "start": 334.6, "end": 341.0, "cx": 968, "cy": 2,   "cw": 816, "ch": 961},
    {"src": "main",  "start": 340.5, "end": 344.5, "cx": 968, "cy": 636, "cw": 816, "ch": 444},         # plano bajo (letterbox) para subir una barra pegada al fondo
    {"src": "main",  "start": 390.0, "end": 405.5, "cx": 135, "cy": 2,   "cw": 816, "ch": 961},
]
# =============================================================


def main():
    # mapear etiquetas de fuente a indices de -i, imagenes aparte (se cargan con -loop)
    vid_labels = [s for s in SOURCES]  # orden de inputs
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

    cmd = ["ffmpeg", "-v", "error", "-y"]
    for args, _ in inputs:
        cmd += args
    cmd += ["-f", "lavfi", "-t", str(tot), "-i", "anullsrc=r=48000:cl=stereo"]
    audio_idx = len(inputs)
    cmd += ["-filter_complex", F, "-map", "[outv]", "-map", f"{audio_idx}:a",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "slow",
            "-b:v", VBITRATE, "-maxrate", f"{float(VBITRATE[:-1])*1.1:.1f}M", "-bufsize", f"{float(VBITRATE[:-1])*2:.0f}M",
            "-c:a", "aac", "-b:a", ABITRATE, "-movflags", "+faststart", "-shortest", OUT]

    print(f"[construir_short] {len(SEGS)} segmentos, duracion esperada {tot}s -> {OUT}", file=sys.stderr)
    subprocess.run(cmd, check=True)
    d = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nw=1:nk=1", OUT]).decode().strip()
    print(f"[construir_short] LISTO. Duracion real: {d}s", file=sys.stderr)
    print("[construir_short] VERIFICA: banda superior constante, uniones y paneos con fotogramas.", file=sys.stderr)


if __name__ == "__main__":
    main()
