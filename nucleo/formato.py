"""El lienzo del Short (medido y aprobado: editor/shorts/SHORT-IDEAL.md). Un único sitio para estos números."""

ANCHO, ALTO, FPS = 1080, 1920, 60      # vertical 9:16 a 60 fps
# Banda de la cara: filas 0-759; la pantalla empieza en la 760. Era 648 hasta el 2026-11-20: el usuario pidió más
# holgura porque los subtítulos (que van sobre la unión cara/pantalla) casi le tapaban la boca. +112 px.
BANDA_CARA = 760
ALTO_PANTALLA = ALTO - BANDA_CARA      # 1160
# Recorte "nativo de Short": misma proporción que 1080xALTO_PANTALLA (lados pares; 896x962 escalado a 1080 de ancho
# da 1160 justos). Con la banda de 648 era 816x961.
RECORTE_W, RECORTE_H = 896, 962
# Subtítulos: caja de 107 px sobre la unión, 29 px encima de la cara y 78 sobre la pantalla (medido en el ideal).
SUBT_Y0 = BANDA_CARA - 29
AUDIO_HZ = 48000


def cuantizar(t, fps=FPS):
    """Redondea un tiempo a un fotograma exacto (así audio y vídeo de cada tramo duran lo mismo, sin deriva)."""
    return round(t * fps) / fps
