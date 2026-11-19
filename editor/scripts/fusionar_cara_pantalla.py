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


def main():
    plan = json.load(open(sys.argv[1], encoding="utf-8"))
    padtop, cara_alto, cara_y = plan["padtop"], plan["cara_alto"], plan.get("cara_y", 0)
    bajo = H - padtop
    tramos = plan["tramos"]
    fil = []
    for i, t in enumerate(tramos):
        a0, a1 = q(t["a0"]), q(t["a1"])
        d = a1 - a0
        t["_d"] = d
        nfr = round(d * FPS)
        fil.append(f"[0:v]trim=start={a0:.6f}:end={a1:.6f},setpts=PTS-STARTPTS,crop={W}:{padtop}:0:{cara_y}[f{i}]")
        if t["abajo"] == "pant":
            p0, p1 = q(t["p0"]), q(t["p1"])
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
    fil.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[outv][outa]")
    cmd = [FFMPEG, "-v", "error", "-y", "-i", plan["cara"], "-i", plan["pantalla"],
           "-filter_complex", ";".join(fil), "-map", "[outv]", "-map", "[outa]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", plan["salida"]]
    os.makedirs(os.path.dirname(plan["salida"]), exist_ok=True)
    subprocess.run(cmd, check=True)
    tot = 0
    for i, t in enumerate(tramos):
        abajo = (f"pantalla {t['p0']:.2f}-{t['p1']:.2f}s x{t['_vel']:.2f}" if t["abajo"] == "pant"
                 else "parte inferior de cara.mp4")
        print(f"tramo {i+1:2d}: final {tot:6.2f}-{tot + t['_d']:6.2f}s | voz/cara {t['a0']:.2f}-{t['a1']:.2f}s | {abajo}"
              f" | {t.get('nota', '')}")
        tot += t["_d"]
    print(f"duración esperada: {tot:.3f}s")


if __name__ == "__main__":
    main()
