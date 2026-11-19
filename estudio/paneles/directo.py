"""Pestaña Directo: arrastra un directo (o una grabación larga 16:9) y pide a Claude la tabla de fragmentos para
YouTube (/directo-a-clips con ESE archivo). También acepta un enlace (YouTube/Twitch). Metodología:
editor/directos/CLAUDE.md."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ..entorno import para_claude
from .ranura import Ranura


class PanelDirecto(QWidget):
    pedir = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        explica = QLabel("Claude transcribe el directo entero, te propone una <b>tabla de fragmentos</b> para YouTube "
                         "y <b>espera a que elijas</b>; luego corta, limpia y verifica cada clip.")
        explica.setWordWrap(True)
        self.ranura = Ranura("directo", "Directo", "el directo o la grabación larga")
        self.ranura.cambiado.connect(lambda _r: self._actualizar())
        self.url = QLineEdit()
        self.url.setPlaceholderText("…o pega un enlace de YouTube/Twitch")
        self.url.textChanged.connect(self._actualizar)
        self.b = QPushButton("Proponer clips con Claude")
        self.b.setMinimumHeight(36)
        self.b.clicked.connect(self._pedir)
        fila = QHBoxLayout()
        fila.addWidget(self.url, 1)
        fila.addWidget(self.b)
        lay = QVBoxLayout(self)
        lay.addWidget(explica)
        lay.addWidget(self.ranura)
        lay.addLayout(fila)
        lay.addStretch(1)
        self._actualizar()

    def cargar(self, m):
        self.ranura.cargar_actual(m)

    def _actualizar(self):
        self.b.setEnabled(bool(self.ranura.ruta or self.url.text().strip().startswith("http")))

    def _pedir(self):
        url = self.url.text().strip()
        origen = url if url.startswith("http") else para_claude(self.ranura.ruta)
        self.pedir.emit(f"/directo-a-clips {origen}")
