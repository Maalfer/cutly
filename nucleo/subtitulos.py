"""Texto y tiempos de los subtítulos karaoke (sin dibujar nada: el dibujo y el estilo visual son de cada línea, p. ej.
editor/shorts/subtitular.py). Palabra = [inicio, fin, texto].

    palabras  --aplicar_glosario-->  palabras corregidas  --agrupar-->  bloques  --linea_de_tiempo-->  estados
"""
import os
import re

from nucleo.archivos import leer_json
from nucleo.rutas import GLOSARIO

FIN_FRASE = re.compile(r"[.!?…]$")


def repartir(t0, t1, textos):
    """Reparte [t0, t1] entre `textos` en proporción a su longitud -> [[ini, fin, texto], ...]."""
    tot = sum(len(x) for x in textos)
    out, t = [], t0
    for x in textos:
        d = (t1 - t0) * len(x) / tot
        out.append([t, t + d, x])
        t += d
    return out


def aplicar_glosario(ws, glosario=GLOSARIO):
    """Reemplazos por FRASE del glosario ([regex, texto correcto], sin distinguir mayúsculas) sobre la secuencia de
    palabras, conservando los tiempos (si cambia el número de palabras, se reparte el tiempo del tramo). Después pone
    mayúscula al principio y tras cada fin de frase."""
    if os.path.exists(glosario):
        for patron, nuevo in leer_json(glosario)["reemplazos"]:
            rx = re.compile(patron, re.IGNORECASE)
            cambiado = True
            while cambiado:
                cambiado = False
                texto, pos = "", []
                for w in ws:
                    if texto:
                        texto += " "
                    pos.append((len(texto), len(texto) + len(w[2])))
                    texto += w[2]
                for m in rx.finditer(texto):
                    if m.group(0) == nuevo:
                        continue
                    i0 = next(i for i, (a, b) in enumerate(pos) if b > m.start())
                    i1 = next(i for i, (a, b) in enumerate(pos) if b >= m.end())
                    nuevas = nuevo.split()
                    nuevas[0] = ws[i0][2][: m.start() - pos[i0][0]] + nuevas[0]
                    nuevas[-1] = nuevas[-1] + ws[i1][2][m.end() - pos[i1][0]:]
                    ws = ws[:i0] + repartir(ws[i0][0], ws[i1][1], nuevas) + ws[i1 + 1:]
                    cambiado = True
                    break
    for i, w in enumerate(ws):
        if i == 0 or FIN_FRASE.search(ws[i - 1][2]):
            w[2] = w[2][:1].upper() + w[2][1:]
    return ws


def agrupar(ws, max_chars=24, max_palabras=5, max_dur=1.6, hueco_corte=0.45):
    """Bloques de una línea: se corta tras . ? ! …, al pasar de max_chars/max_palabras/max_dur o ante un hueco de
    voz > hueco_corte. Una palabra huérfana que cabe en el bloque anterior (misma frase) se une a él."""
    bloques, cur = [], []
    for w in ws:
        if cur:
            texto = " ".join(x[2] for x in cur + [w])
            if (len(texto) > max_chars or len(cur) >= max_palabras
                    or w[1] - cur[0][0] > max_dur or w[0] - cur[-1][1] > hueco_corte):
                bloques.append(cur)
                cur = []
        cur.append(w)
        if FIN_FRASE.search(w[2]):
            bloques.append(cur)
            cur = []
    if cur:
        bloques.append(cur)
    out = []
    for b in bloques:
        if (len(b) == 1 and out and not FIN_FRASE.search(out[-1][-1][2])
                and len(" ".join(x[2] for x in out[-1] + b)) <= max_chars + 4 and b[0][0] - out[-1][-1][1] < 0.3):
            out[-1] = out[-1] + b
        else:
            out.append(b)
    return out


def a_json(bloques):
    """Bloques -> lista de dicts del .subtitulos.json ({ini, fin, texto, palabras})."""
    return [{"ini": round(b[0][0], 3), "fin": round(b[-1][1], 3), "texto": " ".join(w[2] for w in b),
             "palabras": [[round(w[0], 3), round(w[1], 3), w[2]] for w in b]} for b in bloques]


def linea_de_tiempo(bloques, dur, anticipo=0.03, pausa_larga=0.8, cola=0.25):
    """Estados del karaoke en orden: [(t_inicio, None | (indice_bloque, textos, n_palabras_ya_dichas)), ...].
    `bloques` son dicts del .subtitulos.json (si su "texto" se corrigió con otro número de palabras, los tiempos se
    reparten dentro del bloque).

    - El bloque entra (todo gris) `anticipo` s antes de su primera palabra, EN EL MISMO instante en que sale el
      anterior: sin hueco entre bloques (un hueco de 2-3 fotogramas se ve como un parpadeo de la caja).
    - Cada palabra se pone blanca cuando empieza.
    - Tras el último bloque, o si hasta el siguiente hay más de `pausa_larga` s, se retira `cola` s después de su
      última palabra (no se queda colgado)."""
    estados = [(0.0, None)]
    for bi, b in enumerate(bloques):
        ws = b["palabras"]
        textos = b["texto"].split()
        if len(textos) != len(ws):
            ws = repartir(ws[0][0], ws[-1][1], textos)
        for k in range(len(ws) + 1):
            t = ws[0][0] - anticipo if k == 0 else ws[k - 1][0]
            estados.append((max(t, estados[-1][0]), (bi, textos, k)))
        ult = ws[-1][1]
        sig = bloques[bi + 1]["palabras"][0][0] - anticipo if bi + 1 < len(bloques) else None
        if sig is not None and sig - ult <= pausa_larga:
            continue
        estados.append((max(min(ult + cola, dur), estados[-1][0]), None))
    return estados
