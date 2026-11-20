"""La TOMA: registro de pasos + mapa de edición (la grabación es vm/grabacion.py). Deja en editor/crudo/ lo que
espera la Fase 2 (contrato: nucleo/toma.py): <toma>.mp4 (lo trae rec_stop), <toma>.steps.jsonl y <toma>.mapa.md."""
import os

from nucleo import toma as contrato
from nucleo.rutas import CRUDO

from .grabacion import rec_stop
from .registro import _log, _save_state, _state


def take_start(name):
    os.makedirs(CRUDO, exist_ok=True)
    log = contrato.ruta(name, "steps.jsonl")
    open(log, "w", encoding="utf-8").close()
    _save_state({"name": name, "log": log})
    _log(op="take_start", name=name)
    print("registro:", log)


def take_end():
    st = _state()
    if st.get("rec_t0"):
        rec_stop()
    if st.get("log"):
        _log(op="take_end")
        print("mapa:", build_map(st["name"]))
    _save_state({})


def build_map(name):
    """Mapa de edición (doc 04 §Fase 4) generado desde el registro: un bloque por 'mark' con su rango en el vídeo."""
    ev = contrato.cargar_eventos(contrato.ruta(name, "steps.jsonl"))
    t_of = lambda e: e.get("t_video", e["t_wall"] - ev[0]["t_wall"])
    marks = [e for e in ev if e["op"] == "mark"]
    # el último evento suele ser take_end, que no tiene t_video (es DESPUÉS de copiar el vídeo ya parado): si se
    # usara su t_wall caería el tiempo de copia dentro del último acto, alargándolo de más (medido: ~30s de más
    # en sudo-nopasswd-20261120-1219). El final real del vídeo es el del último evento que SÍ tiene t_video.
    con_video = [e for e in ev if "t_video" in e]
    end = t_of(con_video[-1]) if con_video else t_of(ev[-1])
    rows = ["| # | Momento | Desde (s) | Hasta (s) | Dura | Pasos |", "|---|---|---|---|---|---|"]
    for i, m in enumerate(marks):
        a = t_of(m)
        b = t_of(marks[i + 1]) if i + 1 < len(marks) else end
        n = sum(1 for e in ev if e["op"] not in ("mark", "take_start", "take_end", "rec_start", "rec_stop") and a <= t_of(e) < b)
        rows.append(f"| {i + 1} | {m['label']} | {a:.1f} | {b:.1f} | {b - a:.1f} s | {n} |")
    fails = [e for e in ev if e.get("ok") is False]
    out = f"# Mapa de edición — {name}\n\n" + "\n".join(rows) + "\n"
    if fails:
        out += "\n## Pasos fallidos (rehacer)\n" + "\n".join(f"- t={t_of(e):.1f}s `{e['op']}` {e.get('error', '')}" for e in fails) + "\n"
    out += "\nTiempos en segundos desde el inicio del vídeo (±0,3 s). El Short se construye con editor/shorts/short_desde_toma.py.\n"
    path = contrato.ruta(name, "mapa.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path
