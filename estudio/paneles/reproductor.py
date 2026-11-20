"""Reproductor de vídeo con controles (lo usan las secciones Directo → clips y Resultados, con su revisor de
subtítulos)."""
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from nucleo import medios

from ..entorno import en_segundo_plano

REINTENTO_MS = 1200             # un vídeo recién aparecido puede seguir escribiéndose: reintenta en vez de arriesgar
REINTENTOS_MAXIMOS = 15         # ~18 s; pasado esto, probablemente no es un problema de "todavía escribiéndose"


def mmss(ms):
    s = max(0, ms) / 1000
    return f"{int(s // 60)}:{s % 60:05.2f}"


class Reproductor(QWidget):
    posicion = Signal(float)              # segundos, mientras se reproduce

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pedido, self._intentos = "", 0
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget(self)
        self.video.setMinimumHeight(240)
        self.player.setVideoOutput(self.video)

        self.b_play = QPushButton("▶  Reproducir")
        self.b_play.setAccessibleName("Reproducir o pausar")
        self.b_play.clicked.connect(self.alternar)
        self.barra = QSlider(Qt.Orientation.Horizontal)
        self.barra.setAccessibleName("Posición del vídeo")
        self.barra.setAccessibleDescription("Flechas: 1 segundo. Re Pág / Av Pág: 10 segundos.")
        self.barra.setSingleStep(1000)
        self.barra.setPageStep(10000)
        self.barra.sliderMoved.connect(self.player.setPosition)
        self.barra.actionTriggered.connect(lambda _a: self.player.setPosition(self.barra.sliderPosition()))
        self.tiempo = QLabel("0:00.00 / 0:00.00")
        self.tiempo.setAccessibleName("Tiempo")
        self.video.setAccessibleName("Vídeo")

        controles = QHBoxLayout()
        controles.addWidget(self.b_play)
        controles.addWidget(self.barra, 1)
        controles.addWidget(self.tiempo)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.video, 1)
        lay.addLayout(controles)

        self.player.durationChanged.connect(lambda d: self.barra.setRange(0, d))
        self.player.positionChanged.connect(self._avanza)
        self.player.playbackStateChanged.connect(
            lambda st: self.b_play.setText("⏸  Pausa" if st == QMediaPlayer.PlaybackState.PlayingState else "▶  Reproducir"))

    def cargar(self, ruta):
        """Cambia de vídeo. Antes de dárselo al reproductor NATIVO (que puede colgarse con un archivo a medio
        escribir: medido, "moov atom not found" al elegir un resultado recién aparecido) comprueba con ffprobe
        que ya se puede leer; si no, reintenta sin bloquear la interfaz en vez de arriesgarse."""
        self.player.stop()
        self._pedido, self._intentos = ruta, 0
        if not ruta:
            self.player.setSource(QUrl())
            return
        self._comprobar(ruta)

    def _comprobar(self, ruta):
        en_segundo_plano(lambda: medios.legible(ruta), lambda ok, r=ruta: self._listo(r, ok))

    def _listo(self, ruta, ok):
        if ruta != self._pedido:
            return                                      # se eligió otra cosa mientras comprobábamos esta
        if ok:
            self.player.setSource(QUrl.fromLocalFile(ruta))
            return
        self._intentos += 1
        if self._intentos > REINTENTOS_MAXIMOS:
            return                                       # ya no parece cuestión de "se está escribiendo todavía"
        QTimer.singleShot(REINTENTO_MS, lambda: ruta == self._pedido and self._comprobar(ruta))

    def ir_a(self, segundos):
        self.player.setPosition(int(segundos * 1000))

    def alternar(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _avanza(self, ms):
        if not self.barra.isSliderDown():
            self.barra.setValue(ms)
        self.tiempo.setText(f"{mmss(ms)} / {mmss(self.player.duration())}")
        self.posicion.emit(ms / 1000)
