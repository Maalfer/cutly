"""Pestaña Shorts: los vídeos de editor/videos-editados/ (se actualiza sola cuando Claude escribe uno nuevo), su
reproducción y la verificación contra la especificación del Short ideal (verificar_short.py)."""
import os

from PySide6.QtCore import QFileSystemWatcher, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

from nucleo.rutas import SALIDA

from ..entorno import REPO, ejecutar_cli
from .reproductor import Reproductor

VERIFICAR = os.path.join(REPO, "editor", "shorts", "verificar_short.py")


def videos():
    """Vídeos de la carpeta de salida, del más reciente al más antiguo."""
    if not os.path.isdir(SALIDA):
        return []
    v = [os.path.join(SALIDA, f) for f in os.listdir(SALIDA) if f.lower().endswith((".mp4", ".mov", ".mkv"))]
    return sorted(v, key=os.path.getmtime, reverse=True)


class PanelShorts(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self.lista = QListWidget()
        self.lista.setTextElideMode(Qt.TextElideMode.ElideMiddle)     # lo que distingue los nombres está en medio
        self.lista.setMinimumWidth(260)
        self.lista.currentItemChanged.connect(self._elegido)
        self.rep = Reproductor()
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setPlaceholderText("Informe de verificar_short.py")

        b_ver = QPushButton("Verificar contra el Short ideal")
        b_ver.clicked.connect(self.verificar)
        b_dir = QPushButton("Abrir carpeta")
        b_dir.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(SALIDA)))
        botones = QHBoxLayout()
        botones.addWidget(b_ver)
        botones.addWidget(b_dir)

        derecha = QWidget()
        d = QVBoxLayout(derecha)
        d.setContentsMargins(0, 0, 0, 0)
        d.addWidget(self.rep, 3)
        d.addLayout(botones)
        d.addWidget(self.log, 2)
        div = QSplitter(Qt.Orientation.Horizontal)
        div.addWidget(self.lista)
        div.addWidget(derecha)
        div.setSizes([220, 600])
        QVBoxLayout(self).addWidget(div)

        os.makedirs(SALIDA, exist_ok=True)
        self.vigia = QFileSystemWatcher([SALIDA], self)
        self.vigia.directoryChanged.connect(lambda _: self.recargar())
        self.recargar()

    def recargar(self):
        actual = self.lista.currentItem().data(Qt.ItemDataRole.UserRole) if self.lista.currentItem() else None
        self.lista.blockSignals(True)
        self.lista.clear()
        for v in videos():
            it = QListWidgetItem(os.path.basename(v))
            it.setData(Qt.ItemDataRole.UserRole, v)
            it.setToolTip(v)
            self.lista.addItem(it)
            if v == actual:
                self.lista.setCurrentItem(it)
        self.lista.blockSignals(False)

    def _elegido(self, it, _prev=None):
        if it:
            self.rep.cargar(it.data(Qt.ItemDataRole.UserRole))

    def verificar(self):
        it = self.lista.currentItem()
        if not it or self._proc is not None:
            return
        v = it.data(Qt.ItemDataRole.UserRole)
        args = [VERIFICAR, v] + ([] if "_subtitulado" in os.path.basename(v) else ["--sin-subtitulos"])
        self.log.clear()
        self._proc = ejecutar_cli(args, self.log, lambda c: setattr(self, "_proc", None), parent=self)
