#!/usr/bin/env python3
"""
analizar_fusion.py — Mide todo lo necesario para fusionar CARA (cara + voz del usuario) con PANTALLA (Short ya
construido) antes de decidir un solo corte. Metodología: editor/shorts/METODOLOGIA-FUSION-CARA.md.

    python editor/shorts/analizar_fusion.py informe CARA.mp4 PANTALLA.mp4 [--trans CARA_transcripcion.json] [--salida informe.md]
    python editor/shorts/analizar_fusion.py hojas PANTALLA.mp4 [--desde S --hasta S --cada 1]   # mapa de la pantalla
    python editor/shorts/analizar_fusion.py comprobar fusion_plan.json       # ¿falta alguna palabra del plan?
    python editor/shorts/analizar_fusion.py fotogramas SHORT.mp4 IP 80 cat 61s  # fotograma cuando se dice cada cosa

Para afinar después cada corte a 10 ms: python editor/comun/energia.py CARA.mp4 T0 T1 (común a todas las líneas).

`informe` mide, sin mirar nada a ojo:
  1. CARA: alto real de la banda de la cara (filas con imagen antes del negro) y tramos donde la parte de abajo de
     la grabación de cara NO está en negro (el usuario enseña su propia pantalla: se conserva en el montaje).
  2. PANTALLA: alto de la banda negra superior (padtop: la banda, 760; las pantallas antiguas traen 648 -> pantalla_y) y eventos: cambios grandes (Enter, salida
     de un comando, cambio de plano) y tramos quietos (> 2 s).
  3. VOZ: bloques de voz por energía (la verdad física: Whisper inventa texto en silencios y se salta frases).
  4. Con --trans (de transcribir.py): el texto de cada bloque y AVISOS de tomas repetidas (dos bloques que empiezan
     igual) y de voz sin texto (posible falso arranque que Whisper se tragó).
"""
import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
from nucleo import archivos, audio, formato, medios, series, subtitulos, transcripcion  # noqa: E402
from nucleo.ffmpeg import FFMPEG  # noqa: E402
from nucleo.rutas import COMUN, CRUDO  # noqa: E402

NEGRO = 24  # valor de gris por debajo del cual una fila cuenta como negra


def banda_superior(path, n=12):
    """Alto de la banda superior: en CARA, filas con imagen; en PANTALLA, filas negras. Usa n instantes."""
    d = medios.duracion(path)
    res = []
    for k in range(n):
        t = d * (k + 0.5) / n
        negra = medios.fotograma_gris(path, t).max(axis=1) < NEGRO
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
        primera_negra = int(np.argmax(negra)) if negra.any() else formato.ALTO
        if negra[primera_negra:].all():
            altos.append(primera_negra)
        else:
            con_abajo += 1
    alto_cara = int(np.median(altos)) if altos else None
    p(f"# Análisis de fusión\n\n- CARA: `{a.cara}` ({medios.duracion(a.cara):.2f} s)\n- PANTALLA: `{a.pantalla}` ({medios.duracion(a.pantalla):.2f} s)\n")
    p(f"## 1. Cara\n- Banda de la cara: filas 0-{alto_cara - 1 if alto_cara else '?'} → **alto {alto_cara} px** "
      f"(medido en {len(altos)} instantes; {con_abajo} instantes con contenido debajo).")
    if alto_cara:
        f = medios.fotogramas_gris(a.cara, 10, (formato.ANCHO, formato.ALTO - alto_cara - 40, 0, alto_cara + 40), (54, 50))
        abajo = series.rachas([fr.max() >= NEGRO for fr in f], 0.1, minimo=0.5)
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
    banda = formato.BANDA_CARA
    p(f"\n## 2. Pantalla\n- Primera fila con imagen: **{padtop} px** (mínimo de {len(pads)} instantes). La banda de la "
      f"cara mide {banda} (short_desde_toma la deja así; el borde oscuro de la ventana puede sumar unos px).")
    if padtop and padtop >= banda - 4:
        padtop = min(padtop, banda)
        p(f"- En el plan: `\"padtop\": {banda}` (sin `pantalla_y`).")
    elif padtop:
        # Pantalla hecha con una banda más baja (la antigua era 648): se baja hasta la banda y se recorta por abajo.
        corte = banda - padtop
        fondo = medios.fotogramas_gris(a.pantalla, 2, (formato.ANCHO, corte, 0, formato.ALTO - corte), (54, corte))
        lleno = float((fondo > 60).mean(axis=(1, 2)).max()) if len(fondo) else 0.0
        p(f"- Pantalla con banda ANTIGUA ({padtop} < {banda}): en el plan `\"padtop\": {banda}, \"pantalla_y\": {padtop}`. "
          f"La pantalla baja {corte} px y se pierden sus {corte} filas de abajo: como mucho un {lleno * 100:.1f} % de "
          f"píxeles con contenido en ellas{' (vacías: no se pierde nada)' if lleno < 0.01 else ' → REVISA qué se corta'}.")
    if padtop:
        f = medios.fotogramas_gris(a.pantalla, 10, (formato.ANCHO, formato.ALTO - padtop, 0, padtop), (216, 254)).astype(np.int16)
        cambio = (np.abs(np.diff(f, axis=0)) > 40).sum(axis=(1, 2))
        grandes = series.rachas(cambio > 300, 0.1)
        quietos = series.rachas(cambio == 0, 0.1, minimo=2.0)
        p("- Cambios grandes (Enter, salida de comando, cambio de plano): " +
          ", ".join(f"{s + 0.1:.1f}" + (f"-{e + 0.1:.1f}" if e - s > 0.15 else "") for s, e in grandes))
        p("- Tramos quietos ≥ 2 s: " + ", ".join(f"{s + 0.1:.1f}-{e + 0.1:.1f}" for s, e in quietos))
        p("- Para saber QUÉ pasa en cada tramo: hoja de contacto cada 1-3 s (sin drawtext, ver PORTABILIDAD.md):\n"
          "  `ffmpeg -ss T -t 30 -i PANTALLA -vf \"fps=1,crop=1080:700:0:760,scale=270:-1,tile=6x5\" -frames:v 1 hoja.png`")
    # 3. VOZ
    au = medios.audio_mono(a.cara)
    paso = 0.1
    niveles = audio.energia(au, muestras=1600)[0]          # nivel cada 100 ms
    suelo = float(np.percentile(niveles, 20))
    umbral = max(suelo + 12, -38.0)
    bloques = []
    for s, e in series.rachas(niveles > umbral, paso, minimo=0.2):
        if bloques and s - bloques[-1][1] < 0.45:
            bloques[-1] = (bloques[-1][0], e)
        else:
            bloques.append((s, e))
    p(f"\n## 3. Voz (por energía)\n- Suelo de ruido ≈ {suelo:.0f} dB; umbral de voz {umbral:.0f} dB. "
      "Lo que esté por debajo es ruido de fondo aunque Whisper le ponga texto (\"Gracias\").")
    words = []
    if a.trans:
        for s in transcripcion.cargar_segmentos(a.trans):
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
                                  f"Whisper. Revísalo con `editor/comun/energia.py` y mira si el segmento siguiente empieza antes que su "
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
      "pantalla, afina cada corte con `editor/comun/energia.py` y construye con `fusionar_cara_pantalla.py`.")
    out = "\n".join(L) + "\n"
    salida = a.salida or os.path.splitext(a.cara)[0] + ".fusion.md"
    archivos.escribir_texto(salida, out)
    print(out)
    print(f"(informe guardado en {salida})")


def _norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9ñ]", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def _transcribir_resultado(video):
    """Transcripción NORMAL del Short montado en <video>_verificacion.json. No en _transcripcion: ese nombre lo
    reutiliza subtitular.py y debe estar en modo subtítulos. Se rehace si el vídeo es más nuevo."""
    base = os.path.splitext(video)[0] + "_verificacion"
    if not (os.path.exists(base + ".json") and os.path.getmtime(base + ".json") > os.path.getmtime(video)):
        subprocess.run([sys.executable, "-I", os.path.join(COMUN, "transcribir.py"), video, "--salida", base],
                       check=True, stdout=subprocess.DEVNULL)
    return base + ".json"


def comprobar(a):
    """Palabra a palabra: el texto de la grabación de cara dentro de los tramos del plan frente a la transcripción
    del Short montado. Sale con error si falta alguna palabra del plan (un corte se la ha comido)."""
    plan = archivos.leer_json(a.plan)
    src = transcripcion.palabras(transcripcion.cargar_segmentos(
        a.trans or transcripcion.ruta_por_defecto(plan["cara"]) + ".json"))
    esperado = [w[2] for t in plan["tramos"] for w in src if t["a0"] <= (w[0] + w[1]) / 2 < t["a1"]]
    obtenido = transcripcion.palabras(transcripcion.cargar_segmentos(
        a.resultado or _transcribir_resultado(plan["salida"])))
    e, o = [_norm(w) for w in esperado], [_norm(w[2]) for w in obtenido]
    sm = difflib.SequenceMatcher(None, e, o, autojunk=False)
    faltan, variantes, extra = [], [], []
    for op, i0, i1, j0, j1 in sm.get_opcodes():
        if op == "equal":
            continue
        pe, po = " ".join(esperado[i0:i1]), " ".join(w[2] for w in obtenido[j0:j1])
        donde = f"{obtenido[min(j0, len(obtenido) - 1)][0]:.2f} s"
        if op == "insert":
            extra.append(f"{donde}: «{po}»")
        elif op == "replace" and difflib.SequenceMatcher(None, "".join(e[i0:i1]), "".join(o[j0:j1])).ratio() >= 0.6:
            variantes.append(f"{donde}: «{pe}» ≈ «{po}»")
        else:
            faltan.append(f"hacia {donde}: plan «{pe}» → resultado «{po}»")
    print(f"coincidencia {sm.ratio() * 100:.1f} % ({len(esperado)} palabras en el plan, {len(obtenido)} en el Short)")
    for x in variantes:
        print(f"  variante de Whisper (ok): {x}")
    for x in extra:
        print(f"  de más en el Short (Whisper no la escribió en la original; escúchala si dudas): {x}")
    for x in faltan:
        print(f"  [FALTA] {x}")
    if faltan:
        sys.exit("RESULTADO: faltan palabras del plan: un corte se las come (mira la energía en ese punto: "
                 "METODOLOGIA-FUSION-CARA.md, 'Palabras flojas')")
    print("RESULTADO: no falta ninguna palabra del plan")


def _mosaico(video, tiempos, crop, ancho, columnas, salida):
    """Un PNG con un fotograma por instante (sin drawtext: en Windows se cuelga por fontconfig)."""
    with tempfile.TemporaryDirectory() as tmp:
        for k, t in enumerate(tiempos):
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                            f"crop={crop},scale={ancho}:-2", os.path.join(tmp, f"f{k:03d}.png")], check=True)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", os.path.join(tmp, "f%03d.png"), "-vf",
                        f"tile={columnas}x{-(-len(tiempos) // columnas)}", "-frames:v", "1", salida], check=True)


def hojas(a):
    """Hojas de contacto de la PANTALLA (un fotograma cada `cada` s, 6x5 por hoja) para el mapa de qué pasa en cada
    momento. En la hoja que empieza en T, la casilla fila r, columna c es el instante T + (6r + c) * cada."""
    y = a.y if a.y is not None else min(int(np.argmin(n)) for _, n in banda_superior(a.pantalla) if n[0])
    fin = a.hasta if a.hasta is not None else medios.duracion(a.pantalla)
    os.makedirs(a.salida, exist_ok=True)
    t0 = a.desde
    while t0 < fin:
        ts = [t0 + k * a.cada for k in range(30) if t0 + k * a.cada < fin]
        ruta = os.path.join(a.salida, f"hoja_{t0:06.1f}.png")
        _mosaico(a.pantalla, ts, f"{formato.ANCHO}:{min(500, formato.ALTO - y)}:0:{y}", 360, 6, ruta)
        print(f"{ruta}: {ts[0]:.1f}-{ts[-1]:.1f} s (fila r, columna c = {t0:.1f} + (6r + c) * {a.cada:g} s)")
        t0 += 30 * a.cada


def fotogramas(a):
    """Un fotograma por momento clave del Short. Un número son segundos; una palabra, el instante en que se DICE
    (la busca en orden en la transcripción de verificación; +0,15 s). Lo que se nombra debe estar en pantalla."""
    res, tiempos, etiquetas, desde = None, [], [], 0.0
    for x in a.momentos:
        if re.fullmatch(r"\d+([.,]\d+)?s", x):                  # "12.5s" = segundos; "80" es una palabra (puerto 80)
            t = float(x[:-1].replace(",", "."))
        else:
            if res is None:                                     # con el glosario: "MassScan" -> Masscan, "con un CAD" -> cat
                res = subtitulos.aplicar_glosario(transcripcion.palabras(transcripcion.cargar_segmentos(
                    _transcribir_resultado(a.video))))
            b = _norm(x)
            m = next((w for w in res if w[0] >= desde and (b == _norm(w[2]) or (len(b) >= 4 and b in _norm(w[2])) or difflib.SequenceMatcher(
                None, b, _norm(w[2])).ratio() >= 0.8)), None)
            if m is None:
                print(f"  «{x}» no aparece después de {desde:.2f} s (¿Whisper la escribe distinto?)")
                continue
            t, desde = m[0] + 0.15, m[0]
        tiempos.append(t)
        etiquetas.append(f"{x}@{t:.2f}")
    if not tiempos:
        sys.exit("ningún momento encontrado")
    salida = a.salida or os.path.splitext(a.video)[0] + "_sincronia.png"
    _mosaico(a.video, tiempos, f"{formato.ANCHO}:{formato.ALTO}:0:0", 270, min(6, len(tiempos)), salida)
    print(f"{salida}  (en orden: {', '.join(etiquetas)})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("informe", help="medirlo todo antes de cortar")
    i.add_argument("cara")
    i.add_argument("pantalla")
    i.add_argument("--trans", help="JSON de transcribir.py sobre CARA")
    i.add_argument("--salida")
    i.set_defaults(f=informe)
    h = sub.add_parser("hojas", help="hojas de contacto de la pantalla para el mapa")
    h.add_argument("pantalla")
    h.add_argument("--desde", type=float, default=0.0)
    h.add_argument("--hasta", type=float)
    h.add_argument("--cada", type=float, default=1.0, help="segundos entre fotogramas (defecto 1)")
    h.add_argument("--y", type=int, help="primera fila con imagen (defecto: la medida)")
    h.add_argument("--salida", default=os.path.join(CRUDO, "hojas"))
    h.set_defaults(f=hojas)
    c = sub.add_parser("comprobar", help="palabra a palabra: el plan frente al Short montado")
    c.add_argument("plan")
    c.add_argument("--trans", help="transcripción de la CARA (defecto: <cara>_transcripcion.json)")
    c.add_argument("--resultado", help="transcripción ya hecha del Short (defecto: <salida>_verificacion.json)")
    c.set_defaults(f=comprobar)
    f = sub.add_parser("fotogramas", help="un fotograma por momento clave (segundos o palabras dichas)")
    f.add_argument("video")
    f.add_argument("momentos", nargs="+")
    f.add_argument("--salida")
    f.set_defaults(f=fotogramas)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
