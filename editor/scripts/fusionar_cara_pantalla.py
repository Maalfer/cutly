#!/usr/bin/env python3
"""
fusionar_cara_pantalla.py — Mete la cara (con su voz) del usuario en la banda negra superior de un Short ya
construido (pantalla.mp4, de short_desde_toma.py) y sincroniza la pantalla con la narración.

    python fusionar_cara_pantalla.py plan.json

La narración manda: el audio y la cara se cortan por tramos (para quitar tomas repetidas y silencios muertos) y,
para cada tramo, se elige qué se ve abajo:
  - "pant": un rango [p0,p1] de pantalla.mp4, re-temporizado (acelerado/ralentizado) para durar lo mismo que el tramo
            de voz. Así cada frase cae sobre el momento de pantalla del que habla.
  - "cara": la parte inferior de la propia grabación de cara (p. ej. cuando el usuario enseña su PowerShell).

plan.json:
{
  "cara": "editor/crudo/cara.mp4", "pantalla": "editor/crudo/pantalla.mp4",
  "salida": "editor/videos-editados/short_X_editado.mp4",
  "padtop": 648, "cara_alto": 758, "cara_y": 20,
  "tramos": [ {"a0":0, "a1":7, "abajo":"pant", "p0":0, "p1":22.5}, {"a0":69.15,"a1":75.13,"abajo":"cara"}, ... ]
}
Estilo del usuario aplicado por defecto (medido comparando con su re-edición, METODOLOGIA-FUSION-CARA.md):
  "apretar": quita toda pausa > 0,25 s (margen 40 ms antes / 60 ms después de la voz) y los tramos sin voz;
  "lufs": -14 (normalización lineal, techo -1 dBTP); "fundido_final": 0.25 s a negro.
Todos los tiempos se redondean a fotogramas de 1/60 s, así audio y vídeo de cada tramo duran EXACTAMENTE lo mismo
(48000/60 = 800 muestras por fotograma) y no hay deriva al concatenar.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_desde_toma import FFMPEG  # localiza ffmpeg igual que el resto de scripts (Windows/macOS/Linux)

FPS = 60
W, H = 1080, 1920


def q(t):
    return round(t * FPS) / FPS


def mascara_voz(cara):
    """Voz cada 10 ms en el audio de la cara: rms > -38 dB, o energía de alta frecuencia > -42 dB (sibilantes
    finales como la 's' de 'pass', que tienen poco rms). Ignora chasquidos sueltos de < 60 ms."""
    import numpy as np
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", cara, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = len(a) // 160
    fr = a[:n * 160].reshape(n, 160)
    rms = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    hf = 20 * np.log10(np.sqrt((np.diff(fr, axis=1) ** 2).mean(1)) + 1e-9)
    v = (rms > -38) | (hf > -42)
    i = 0
    while i < n:  # quita rachas de voz de menos de 60 ms (chasquidos, golpes)
        if v[i]:
            j = i
            while j < n and v[j]:
                j += 1
            if j - i < 6:
                v[i:j] = False
            i = j
        else:
            i += 1
    return v


def apretar(tramos, voz, pausa_max, m_antes, m_despues):
    """Estilo del usuario (medido comparando con su re-edición): fuera TODA pausa entre frases de más de
    `pausa_max`; se deja `m_antes` antes de cada arranque y `m_despues` tras cada final. Un tramo sin voz
    (p. ej. una espera dramática) desaparece. La pantalla de cada trozo sale del mismo mapeo lineal del tramo,
    así que la sincronía se mantiene."""
    out = []
    for t in tramos:
        a0, a1 = t["a0"], t["a1"]
        idx = [k for k in range(int(a0 * 100), int(a1 * 100)) if k < len(voz) and voz[k]]
        if not idx:
            print(f"  (tramo sin voz eliminado: {a0:.2f}-{a1:.2f}s {t.get('nota', '')})")
            continue
        grupos, ini, prev = [], idx[0], idx[0]
        for k in idx[1:]:
            if (k - prev) / 100 > pausa_max:
                grupos.append((ini, prev))
                ini = k
            prev = k
        grupos.append((ini, prev))
        for g0, g1 in grupos:
            s = max(a0, g0 / 100 - m_antes)
            e = min(a1, (g1 + 1) / 100 + m_despues)
            if e - s < 2 / FPS:
                continue
            piece = dict(t, a0=s, a1=e)
            if t["abajo"] == "pant":
                vel = (t["p1"] - t["p0"]) / (a1 - a0)
                piece["p0"] = t["p0"] + (s - a0) * vel
                piece["p1"] = t["p0"] + (e - a0) * vel
            out.append(piece)
    return out


def main():
    plan = json.load(open(sys.argv[1], encoding="utf-8"))
    padtop, cara_alto, cara_y = plan["padtop"], plan["cara_alto"], plan.get("cara_y", 0)
    bajo = H - padtop
    ap = plan.get("apretar", {"pausa_max": 0.25, "margen_antes": 0.04, "margen_despues": 0.06})
    tramos = plan["tramos"]
    if ap:
        tramos = apretar(tramos, mascara_voz(plan["cara"]), ap["pausa_max"], ap["margen_antes"], ap["margen_despues"])
    fil = []
    for i, t in enumerate(tramos):
        a0, a1 = q(t["a0"]), q(t["a1"])
        d = a1 - a0
        t["_d"] = d
        nfr = round(d * FPS)
        fil.append(f"[0:v]trim=start={a0:.6f}:end={a1:.6f},setpts=PTS-STARTPTS,crop={W}:{padtop}:0:{cara_y}[f{i}]")
        if t["abajo"] == "pant":
            p0, p1 = q(t["p0"]), q(t["p1"])
            if p1 <= p0:  # trozo de pantalla de menos de un fotograma: congela ese fotograma
                p1 = p0 + 1 / FPS
            k = d / (p1 - p0)
            t["_vel"] = 1 / k
            fil.append(f"[1:v]trim=start={p0:.6f}:end={p1:.6f},setpts=PTS-STARTPTS,setpts=PTS*{k:.6f},fps={FPS},"
                       f"crop={W}:{bajo}:0:{padtop},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={nfr},"
                       f"setpts=PTS-STARTPTS[b{i}]")
        else:
            alto = H - cara_alto
            fil.append(f"[0:v]trim=start={a0:.6f}:end={a1:.6f},setpts=PTS-STARTPTS,crop={W}:{alto}:0:{cara_alto},"
                       f"pad={W}:{bajo}:0:0:black[b{i}]")
        fil.append(f"[f{i}][b{i}]vstack=2,fps={FPS},trim=end_frame={nfr},setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
        # micro-fade de 15 ms solo donde el audio se interrumpe (evita chasquidos en los empalmes)
        cont_prev = i > 0 and abs(q(tramos[i - 1]["a1"]) - a0) < 1e-6
        cont_next = i + 1 < len(tramos) and abs(q(tramos[i + 1]["a0"]) - a1) < 1e-6
        af = f"[0:a]atrim=start={a0:.6f}:end={a1:.6f},asetpts=PTS-STARTPTS"
        if not cont_prev:
            af += ",afade=t=in:d=0.015"
        if not cont_next:
            af += f",afade=t=out:st={d - 0.015:.6f}:d=0.015"
        fil.append(af + f",apad,atrim=end_sample={round(d * 48000)}[a{i}]")
    n = len(tramos)
    total = sum(t["_d"] for t in tramos)
    fundido = plan.get("fundido_final", 0.25)
    fil.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca]")
    if fundido:
        fil.append(f"[cv]fade=t=out:st={total - fundido:.6f}:d={fundido}[outv]")
        fil.append(f"[ca]afade=t=out:st={total - fundido:.6f}:d={fundido}[outa]")
    else:
        fil.append("[cv]null[outv]")
        fil.append("[ca]anull[outa]")
    os.makedirs(os.path.dirname(plan["salida"]), exist_ok=True)
    lufs = plan.get("lufs", -14)
    # con normalización: primero un intermedio con audio PCM (sin pérdida) y luego el AAC final ya normalizado
    tmp = os.path.splitext(plan["salida"])[0] + ".tmp.mov" if lufs else plan["salida"]
    cmd = [FFMPEG, "-v", "error", "-y", "-i", plan["cara"], "-i", plan["pantalla"],
           "-filter_complex", ";".join(fil), "-map", "[outv]", "-map", "[outa]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-c:a", "pcm_s16le" if lufs else "aac", "-ar", "48000"]
    if not lufs:
        cmd += ["-b:a", "192k", "-movflags", "+faststart"]
    subprocess.run(cmd + [tmp], check=True)
    if lufs:
        # volumen del usuario: ~-14 LUFS (lo subió +5 dB a mano). Normalización LINEAL en dos pasadas (misma
        # ganancia en todo el vídeo, sin compresión) con techo de -1 dBTP para no saturar como el ajuste a mano.
        src = tmp
        med = subprocess.run([FFMPEG, "-v", "info", "-i", src, "-vn", "-af",
                              f"loudnorm=I={lufs}:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        m = json.loads(med[med.rindex("{"):med.rindex("}") + 1])
        an = (f"loudnorm=I={lufs}:TP=-1:LRA=11:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-c:v", "copy", "-af", an, "-ar", "48000",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", plan["salida"]], check=True)
        os.remove(src)
        print(f"volumen: {m['input_i']} LUFS -> {lufs} LUFS (techo -1 dBTP)")
    tot = 0
    for i, t in enumerate(tramos):
        abajo = (f"pantalla {t['p0']:.2f}-{t['p1']:.2f}s x{t['_vel']:.2f}" if t["abajo"] == "pant"
                 else "parte inferior de cara.mp4")
        print(f"trozo {i+1:2d}: final {tot:6.2f}-{tot + t['_d']:6.2f}s | voz/cara {t['a0']:.2f}-{t['a1']:.2f}s | {abajo}"
              f" | {t.get('nota', '')}")
        tot += t["_d"]
    print(f"duración esperada: {tot:.3f}s")


if __name__ == "__main__":
    main()
