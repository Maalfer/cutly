"""El lienzo del Short (medido y aprobado: editor/shorts/SHORT-IDEAL.md). Un único sitio para estos números."""

ANCHO, ALTO, FPS = 1080, 1920, 60      # vertical 9:16 a 60 fps
BANDA_CARA = 648                       # filas 0-647: la cara del usuario; la pantalla empieza en la 648
ALTO_PANTALLA = ALTO - BANDA_CARA      # 1272
RECORTE_W, RECORTE_H = 816, 961        # recorte "nativo de Short" (misma proporción que 1080x1272)
AUDIO_HZ = 48000


def cuantizar(t, fps=FPS):
    """Redondea un tiempo a un fotograma exacto (así audio y vídeo de cada tramo duran lo mismo, sin deriva)."""
    return round(t * fps) / fps
