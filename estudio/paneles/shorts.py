"""Pestaña Resultados: los vídeos de editor/videos-editados/ (se actualiza sola cuando Claude escribe uno nuevo), su
reproducción y la verificación contra la especificación del Short ideal (verificar_short.py). Soltar aquí cualquier
otro vídeo lo verifica."""
import os

from PySide6.QtCore import QFileSystemWatcher, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from nucleo.rutas import SALIDA

from ..entorno import REPO, ejecutar_cli, para_claude
from .reproductor import Reproductor

VERIFICAR = os.path.join(REPO, "editor", "shorts", "verificar_short.py")


def videos():
    """Vídeos de la carpeta de salida, del más reciente al más antiguo."""
    if not os.path.isdir(SALIDA):
        return []
    v = [os.path.join(SALIDA, f) for f in os.listdir(SALIDA) if f.lower().endswith((".mp4", ".mov", ".mkv"))]
    return sorted(v, key=os.path.getmtime, reverse=True)


class PanelShorts(QWidget):
    pedir = Signal(str)                 # mensaje para la sesión de Claude Code
    revisar = Signal(str)               # abrir estos subtítulos en la pestaña Subtítulos

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self.externos = []              # vídeos soltados aquí para verificarlos (no están en videos-editados)
        self.lista = QListWidget()
        self.lista.setTextElideMode(Qt.TextElideMode.ElideMiddle)     # lo que distingue los nombres está en medio
        self.lista.setMinimumWidth(260)
        self.lista.currentItemChanged.connect(self._elegido)
        self.lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
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

    def traer_soltados(self, rutas):
        """Soltar un vídeo en la pestaña = verificarlo (no hace falta que lo haya hecho Claude)."""
        videos_ = [r for r in rutas if r.lower().endswith((".mp4", ".mov", ".mkv"))]
        if not videos_:
            return
        for v in videos_:
            if v not in self.externos:
                self.externos.insert(0, v)
        self.recargar(seleccionar=videos_[0])
        self.verificar()

    def recargar(self, seleccionar=None):
        actual = seleccionar or (self.lista.currentItem().data(Qt.ItemDataRole.UserRole) if self.lista.currentItem() else None)
        self.lista.blockSignals(True)
        self.lista.clear()
        for v in [e for e in self.externos if os.path.exists(e)] + videos():
            it = QListWidgetItem(os.path.basename(v) + ("   (soltado)" if v in self.externos else ""))
            it.setData(Qt.ItemDataRole.UserRole, v)
            it.setToolTip(v)
            self.lista.addItem(it)
            if v == actual:
                self.lista.setCurrentItem(it)
        self.lista.blockSignals(False)
        if seleccionar and self.lista.currentItem():
            self._elegido(self.lista.currentItem())

    def _elegido(self, it, _prev=None):
        if it:
            self.rep.cargar(it.data(Qt.ItemDataRole.UserRole))

    def _menu(self, pos):
        it = self.lista.itemAt(pos)
        if not it:
            return
        v = it.data(Qt.ItemDataRole.UserRole)
        base = os.path.splitext(v)[0]
        menu = QMenu(self)
        if "_subtitulado" not in base:
            menu.addAction("Subtitular con Claude", lambda: self.pedir.emit(f"/subtitular-short {para_claude(v)}"))
        if os.path.exists(base + ".subtitulos.json"):
            menu.addAction("Revisar sus subtítulos", lambda: self.revisar.emit(base + ".subtitulos.json"))
        menu.addAction("Verificar contra el Short ideal", self.verificar)
        menu.addAction("Preguntar a Claude por este vídeo…", lambda: self.pedir.emit(f"Mira el vídeo {para_claude(v)}: "))
        menu.addSeparator()
        menu.addAction("Abrir", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(v)))
        menu.exec(self.lista.mapToGlobal(pos))

    def verificar(self):
        it = self.lista.currentItem()
        if not it or self._proc is not None:
            return
        v = it.data(Qt.ItemDataRole.UserRole)
        args = [VERIFICAR, v] + ([] if "_subtitulado" in os.path.basename(v) else ["--sin-subtitulos"])
        self.log.clear()
        self._proc = ejecutar_cli(args, self.log, lambda c: setattr(self, "_proc", None), parent=self)
