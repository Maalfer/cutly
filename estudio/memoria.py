"""VigiaMemoria: si la memoria del sistema se pone crítica, avisa para que la ventana se cierre ORDENADAMENTE
(guarda preferencias, termina el árbol de procesos de Claude Code) en vez de que algo externo —el propio SO, o
quien vigile procesos por quedarse sin memoria— la mate a la fuerza a mitad de un guardado. Eso es justo lo que
dejó un vídeo roto (moov atom not found) la vez que pasó: ffmpeg escribiendo el entregable final cuando el
proceso murió sin avisar. Complementa, no sustituye, a nucleo/ffmpeg.py:salida_atomica (que asegura que un
vídeo final nunca queda a medias pase lo que pase); esto reduce que haga falta llegar a ese caso.

Sin `psutil` instalado, no vigila nada (la app sigue funcionando igual, solo sin esta red de seguridad): no es
una dependencia dura, es una mejora si está.
"""
from PySide6.QtCore import QObject, QTimer, Signal

MINIMO_MB = 400          # por debajo de esto, un ffmpeg a medio escribir puede dejar un .mp4 roto
INTERVALO_MS = 10000


def libre_mb():
    try:
        import psutil
    except ImportError:
        return None
    try:
        return psutil.virtual_memory().available / (1024 * 1024)
    except Exception:
        return None


class VigiaMemoria(QObject):
    critica = Signal(float)          # MB libres, la primera vez que cruza el mínimo

    def __init__(self, minimo_mb=MINIMO_MB, parent=None):
        super().__init__(parent)
        self.minimo_mb = minimo_mb
        self._avisado = False
        self._t = QTimer(self, interval=INTERVALO_MS, timeout=self._comprobar)
        if libre_mb() is not None:          # sin psutil, ni se arranca: nunca falla por su ausencia
            self._t.start()

    def _comprobar(self):
        mb = libre_mb()
        if mb is None:
            self._t.stop()
            return
        if mb < self.minimo_mb and not self._avisado:
            self._avisado = True
            self.critica.emit(mb)
        elif mb >= self.minimo_mb * 1.5:    # margen para no parpadear justo en el límite
            self._avisado = False
