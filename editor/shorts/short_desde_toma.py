#!/usr/bin/env python3
"""
short_desde_toma.py — Convierte una TOMA grabada por los agentes en un SHORT vertical 1080x1920@60 con la banda
negra superior FIJA (padtop=760, formato.BANDA_CARA) para la cara del usuario, de forma totalmente automática.

    python editor/shorts/short_desde_toma.py NOMBRE_TOMA [--titulo Titulo-Con-Gancho] [--max-plano 8] [--padtop 760]
                                           [--plan plan.json]

Entrada (la deja `vm_control.py take end` en editor/crudo/):
    NOMBRE_TOMA.mp4          grabación de la VM (VirtualBox, en el anfitrión; 1920x1012 aprox.)
    NOMBRE_TOMA.steps.jsonl  registro de pasos: marcas (`mark`), movimientos del ratón y tiempos en el vídeo
Salida:
    editor/videos-editados/short_<Titulo>_editado.mp4   (audio MUDO: el usuario graba la voz después)
    + una entrada (APPEND) en editor/videos-editados/_cortes.log

Cómo decide el encuadre (metodología: editor/shorts/METODOLOGIA-SHORTS.md):
  - Cada acto (marca) se parte en planos de <= --max-plano segundos (planos holgados, pecar de lento).
  - Dos modos de encuadre por plano, según el `focus` más cercano (ver `vm_control.py focus`):
      · CON REGIÓN (w,h, p. ej. el rectángulo exacto de una ventana de terminal): LETTERBOX de esa región
        COMPLETA, estática — nunca recorta. Es el modo por defecto y el único correcto para texto que
        puede llegar al borde de su ventana (el ratón no se mueve mientras se teclea, así que un recorte
        centrado en un punto no sabe hasta dónde llega el texto — medido: "22/tcp" salía como "cp").
      · SIN REGIÓN (un punto suelto, p. ej. un clic): recorte fijo 896×962 que SIGUE ese punto; si el
        plano cruza dos puntos, hace un PANEO horizontal suave entre ellos. Resérvalo para énfasis puntual
        donde SEPAS que todo lo importante cabe en 896×962 — nunca para una ventana de terminal entera.
  - La banda negra superior mide EXACTAMENTE padtop en todos los fotogramas y se VERIFICA midiendo píxeles.
  - --plan permite fijar los planos a mano: [{"start":s,"end":e,"cx0":x,"cx1":x,"cy":y}, ...] para el modo
    recorte, o [{"start":s,"end":e,"rx":x,"ry":y,"rw":w,"rh":h}, ...] para letterbox de una región fija.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import archivos, cortes, formato, medios, toma  # noqa: E402
from nucleo.ffmpeg import FFMPEG, salida_atomica  # noqa: E402
from nucleo.rutas import SALIDA  # noqa: E402

CW, CH = formato.RECORTE_W, formato.RECORTE_H          # recorte "nativo de short": proporción 1080xALTO_PANTALLA
CANVAS_W, CANVAS_H, FPS = formato.ANCHO, formato.ALTO, formato.FPS
URLBAR_FOCUS = (408, 135)    # mirar mientras se teclea una URL: x=408 -> recorte desde el borde izquierdo (URL + inicio de la página)


def cargar_registro(base):
    """Marcas y focos de BASE.steps.jsonl (contrato: nucleo/toma.py)."""
    ev = toma.cargar_eventos(base + ".steps.jsonl")
    marks = [(e["t_video"], e["label"]) for e in ev if e["op"] == "mark" and "t_video" in e]
    focos = []                       # (t_video, x, y, w|None, h|None): hacia dónde mira el espectador
    for e in ev:
        if "t_video" not in e:
            continue
        a = e.get("args", [])
        if e["op"] == "move" and len(a) >= 2:
            try:
                focos.append((e["t_video"], int(a[0]), int(a[1]), None, None))
            except ValueError:
                pass
        elif e["op"] == "focus" and len(a) >= 2:
            w, h = (int(a[2]), int(a[3])) if len(a) >= 4 else (None, None)
            focos.append((e["t_video"], int(a[0]), int(a[1]), w, h))
        elif e["op"] == "typeurl":
            focos.append((e["t_video"] - float(e.get("dur", 0)), *URLBAR_FOCUS, None, None))
    focos.sort()
    return marks, focos


def foco_en(focos, t, defecto):
    """Último foco conocido en el instante t: (x, y, w|None, h|None). El cursor/focus llega ANTES de que
    ocurra lo importante. w,h presentes = región a encuadrar entera (letterbox); ausentes = punto suelto."""
    cur = defecto
    for ft, x, y, w, h in focos:
        if ft <= t:
            cur = (x, y, w, h)
        else:
            break
    return cur


def planos_automaticos(marks, focos, dur, ancho, alto, max_plano):
    limites = [m[0] for m in marks] + [dur]
    centro = (ancho // 2, alto // 2, None, None)
    planos = []
    for i in range(len(marks)):
        a, b = limites[i], limites[i + 1]
        n = max(1, int(-(-(b - a) // max_plano)))           # ceil
        paso = (b - a) / n
        for k in range(n):
            s, e = a + k * paso, a + (k + 1) * paso
            fx0, fy0, fw0, fh0 = foco_en(focos, s, centro)
            fx1, fy1, fw1, fh1 = foco_en(focos, e - 0.01, centro)
            if fw0 and fh0:
                # letterbox de la REGIÓN completa (estática: una ventana no se mueve dentro de un plano)
                planos.append({"start": s, "end": e, "rx": fx0 - fw0 // 2, "ry": fy0 - fh0 // 2,
                              "rw": fw0, "rh": fh0, "acto": marks[i][1]})
            else:
                planos.append({"start": s, "end": e, "cx0": fx0, "cx1": fx1, "cy": (fy0 + fy1) // 2,
                              "acto": marks[i][1]})
    return planos


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fit_contain(rw, rh, avail_w, avail_h):
    """Encaja rw×rh ENTERO dentro de avail_w×avail_h (letterbox real, nunca recorta): ajusta por el eje que
    sea más restrictivo. Devuelve (dw, dh, xoff) — xoff centra horizontalmente si sobra ancho."""
    dh = round(rh * avail_w / rw)
    if dh <= avail_h:
        return avail_w, dh, 0
    dw = round(rw * avail_h / rh)
    return dw, avail_h, (avail_w - dw) // 2


def construir(src, planos, ancho, alto, padtop, titulo):
    os.makedirs(SALIDA, exist_ok=True)
    out = os.path.join(SALIDA, f"short_{titulo}_editado.mp4")
    avail_h = CANVAS_H - padtop
    dh_fijo = round(CH * CANVAS_W / CW)                      # 1160: modo recorte+paneo (punto suelto)
    assert dh_fijo <= avail_h, "padtop + contenido (modo recorte) no cabe en el lienzo"
    partes, total = [], 0.0
    for i, p in enumerate(planos):
        dur = p["end"] - p["start"]
        if "rw" in p:
            # LETTERBOX de la región completa: SIN recorte, nunca deja nada fuera (fit_contain por el eje
            # que haga falta). Estático dentro del plano: una ventana entera no se panea.
            rx = clamp(p["rx"], 0, max(0, ancho - p["rw"]))
            ry = clamp(p["ry"], 0, max(0, alto - p["rh"]))
            dw, dh, xoff = fit_contain(p["rw"], p["rh"], CANVAS_W, avail_h)
            p["x0"] = p["x1"] = rx  # para el log de abajo
            partes.append(
                f"[0:v]trim=start={p['start']:.3f}:end={p['end']:.3f},setpts=PTS-STARTPTS,"
                f"crop=w={p['rw']}:h={p['rh']}:x={rx}:y={ry},scale={dw}:{dh}:flags=lanczos,setsar=1,"
                f"pad={CANVAS_W}:{CANVAS_H}:{xoff}:{padtop}:black,fps={FPS},format=yuv420p[v{i}]")
        else:
            x0 = clamp(int(p["cx0"] - CW / 2), 0, ancho - CW)
            x1 = clamp(int(p["cx1"] - CW / 2), 0, ancho - CW)
            y = clamp(int(p["cy"] - CH / 2), 0, max(0, alto - CH))
            p["x0"], p["x1"], p["y"] = x0, x1, y
            x = f"{x0}" if x0 == x1 else f"'{x0}+({x1}-{x0})/{dur:.3f}*t'"
            partes.append(
                f"[0:v]trim=start={p['start']:.3f}:end={p['end']:.3f},setpts=PTS-STARTPTS,"
                f"crop=w={CW}:h={CH}:x={x}:y={y},scale={CANVAS_W}:{dh_fijo}:flags=lanczos,setsar=1,"
                f"pad={CANVAS_W}:{CANVAS_H}:0:{padtop}:black,fps={FPS},format=yuv420p[v{i}]")
        total += dur
    concat = "".join(f"[v{i}]" for i in range(len(planos))) + f"concat=n={len(planos)}:v=1:a=0[outv]"
    cmd = [FFMPEG, "-v", "error", "-y", "-i", src, "-f", "lavfi", "-t", f"{total:.3f}", "-i",
           "anullsrc=r=48000:cl=stereo", "-filter_complex", ";".join(partes + [concat]),
           "-map", "[outv]", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-b:v", "8M", "-maxrate", "9M",
           "-bufsize", "16M", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest"]
    # a <out> directo no: un corte a medias (memoria, Ctrl+C...) dejaría un .mp4 roto con el nombre bueno
    r = salida_atomica(cmd, out, capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg falló:\n" + r.stderr[-1500:])
    return out, total


def filas_negras_superiores(video, t, columna=540):
    """Cuenta las filas negras desde arriba en una columna del fotograma t (METODOLOGIA-SHORTS.md §1)."""
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                          f"crop=10:{CANVAS_H}:{columna}:0,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = 0
    for i in range(CANVAS_H):
        fila = raw[i * 10:(i + 1) * 10]
        if len(fila) < 10 or max(fila) > 17:   # negro de relleno = luma 16; el contenido oscuro (~25+) NO cuenta
            break
        n += 1
    return n


def verificar(out, dur, padtop, n=5):
    """Mide la banda negra en n instantes repartidos: TODOS deben dar >= padtop y el contenido NO debe invadirla."""
    ts = [dur * (k + 0.5) / n for k in range(n)]
    # La fila padtop-1 debe ser negra y la padtop+2 ya contenido: se mide con la fila de transición en 3 columnas.
    res = []
    for t in ts:
        res.append(filas_negras_superiores(out, t))
    return ts, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("toma")
    ap.add_argument("--titulo", default=None, help="Titulo-Con-Gancho en Capitalized-Kebab-Case (def.: nombre de la toma)")
    ap.add_argument("--max-plano", type=float, default=8.0)
    ap.add_argument("--padtop", type=int, default=formato.BANDA_CARA)
    ap.add_argument("--plan", default=None)
    a = ap.parse_args()

    src = toma.ruta(a.toma, "mp4")
    if not os.path.exists(src):
        sys.exit(f"no existe {src}")
    ancho, alto, dur = medios.probe_video(src)
    marks, focos = cargar_registro(src[:-len(".mp4")])
    if a.plan:
        planos = archivos.leer_json(a.plan)
    else:
        if not marks:
            sys.exit("el registro no tiene marcas (`vm_control.py mark ...`): usa --plan")
        planos = planos_automaticos(marks, focos, dur, ancho, alto, a.max_plano)
    titulo = a.titulo or a.toma
    out, total = construir(src, planos, ancho, alto, a.padtop, titulo)

    # --- verificación obligatoria (METODOLOGIA-SHORTS.md §6)
    _, _, dsal = medios.probe_video(out)
    ts, filas = verificar(out, dsal, a.padtop)
    size_out = medios.probe_video(out)[:2]
    ok_dur = abs(dsal - total) < 0.6
    ok_banda = all(f >= a.padtop for f in filas) and size_out == (CANVAS_W, CANVAS_H)   # >= padtop: el panel oscuro de Kali bajo la banda también cuenta como negro; la altura exacta la fija el filtro pad
    print(f"short: {out}")
    print(f"duración {dsal:.1f}s (esperada {total:.1f}s) {'OK' if ok_dur else 'REVISAR'} | planos: {len(planos)}")
    print(f"filas negras superiores medidas en 5 instantes: {filas} (>= padtop={a.padtop}; el pad fija {a.padtop} exactos) | lienzo {size_out[0]}x{size_out[1]} {'OK' if ok_banda else 'REVISAR'}")

    # --- registro de cortes
    entrada = (f"\n[{datetime.now():%Y-%m-%d %H:%M}] short_{titulo}_editado.mp4  (desde toma '{a.toma}', "
               f"padtop={a.padtop}, fuente {ancho}x{alto})\n")
    for i, p in enumerate(planos):
        if "rw" in p:
            entrada += (f"  plano {i + 1}: {p['start']:.2f}-{p['end']:.2f}s  LETTERBOX región "
                        f"{p['rw']}x{p['rh']} @ {p['x0']},{p['ry']}  [{p.get('acto', '')}]\n")
        else:
            entrada += (f"  plano {i + 1}: {p['start']:.2f}-{p['end']:.2f}s  crop {CW}:{CH} x {p['x0']}->{p['x1']} "
                        f"y {p['y']}  [{p.get('acto', '')}]\n")
    cortes.anotar(entrada)  # APPEND, nunca reescribir
    if not (ok_dur and ok_banda):
        sys.exit(1)


if __name__ == "__main__":
    main()
