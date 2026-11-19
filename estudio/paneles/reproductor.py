"""Reproductor de vídeo con controles (lo usan las pestañas Shorts y Subtítulos)."""
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget


def mmss(ms):
    s = max(0, ms) / 1000
    return f"{int(s // 60)}:{s % 60:05.2f}"


class Reproductor(QWidget):
    posicion = Signal(float)              # segundos, mientras se reproduce

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget(self)
        self.video.setMinimumHeight(240)
        self.player.setVideoOutput(self.video)

        self.b_play = QPushButton("▶")
        self.b_play.setFixedWidth(40)
        self.b_play.clicked.connect(self.alternar)
        self.barra = QSlider(Qt.Orientation.Horizontal)
        self.barra.sliderMoved.connect(self.player.setPosition)
        self.tiempo = QLabel("0:00.00 / 0:00.00")

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
            lambda st: self.b_play.setText("⏸" if st == QMediaPlayer.PlaybackState.PlayingState else "▶"))

    def cargar(self, ruta):
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(ruta) if ruta else QUrl())

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
