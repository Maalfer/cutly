"""Utilidades sobre series muestreadas a paso fijo (máscaras de voz, de cambio de imagen...)."""


def rachas(mascara, paso=1.0, minimo=0.0):
    """Tramos consecutivos a True de una máscara muestreada cada `paso` s -> [(inicio, fin)] (fin exclusivo).
    Descarta los que duran menos de `minimo` s."""
    out, ini = [], None
    for i, v in enumerate(mascara):
        if v and ini is None:
            ini = i
        if not v and ini is not None:
            if (i - ini) * paso >= minimo:
                out.append((ini * paso, i * paso))
            ini = None
    if ini is not None and (len(mascara) - ini) * paso >= minimo:
        out.append((ini * paso, len(mascara) * paso))
    return out
