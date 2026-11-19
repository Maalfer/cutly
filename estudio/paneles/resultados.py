"""Sección "Resultados": lo que va saliendo en editor/videos-editados/ (aparece solo cuando Claude lo termina), su
reproducción, la verificación de un Short contra la especificación del Short ideal (verificar_short.py) y las acciones
que siguen (subtitular, revisar sus subtítulos). Soltar aquí cualquier otro vídeo lo verifica."""
import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QSplitter,
                               QVBoxLayout, QWidget)

from nucleo import material
from nucleo.rutas import SALIDA

from ..entorno import REPO, ejecutar_cli, en_segundo_plano, para_claude
from .comun import boton, cabecera, estado, nombrar
from .ranura import resumen
from .reproductor import Reproductor

VERIFICAR = os.path.join(REPO, "editor", "shorts", "verificar_short.py")
VIDEO = (".mp4", ".mov", ".mkv")


def videos():
    """Vídeos de la carpeta de salida, del más reciente al más antiguo (sin intermedios a medio escribir)."""
    if not os.path.isdir(SALIDA):
        return []
    v = [os.path.join(SALIDA, f) for f in os.listdir(SALIDA)
         if f.lower().endswith(VIDEO) and ".tmp." not in f.lower()]
    return sorted(v, key=os.path.getmtime, reverse=True)


def veredicto(informe):
    """Resumen del informe de verificar_short.py: (texto, objectName para el color)."""
    fallos = informe.count("[FALLA]")
    if "cumple la especificación" in informe:
        return "✔ Cumple la especificación del Short ideal", "ok"
    if fallos:
        return f"✘ {fallos} punto(s) por corregir (detalle abajo)", "error"
    return "", "ayuda"


class PanelResultados(QWidget):
    TITULO = "Resultados"
    pedir = Signal(str)
    revisar = Signal(str)               # abrir estos subtítulos en la sección Subtítulos

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self.externos = []              # vídeos soltados aquí para verificarlos (no están en videos-editados)
        self.lista = nombrar(QListWidget(), "Resultados", "Vídeos terminados. Tecla Menú: más acciones.")
        self.lista.setTextElideMode(Qt.TextElideMode.ElideMiddle)     # lo que distingue los nombres está en medio
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)   # recortar, no desplazar
        self.lista.setUniformItemSizes(True)
        self.lista.setMinimumWidth(240)
        self.lista.currentItemChanged.connect(self._elegido)
        self.lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        self.rep = Reproductor()
        self.info = estado()
        self.veredicto = estado()
        self.log = nombrar(QPlainTextEdit(readOnly=True), "Informe de verificación")
        self.log.setPlaceholderText("Informe de la verificación")

        self.b_ver = boton("Verificar contra el Short ideal", "verificar_short.py: formato, banda de la cara, pausas, "
                                                              "volumen, subtítulos…", self.verificar)
        self.b_subs = boton("Subtitular con Claude", "Pide a Claude los subtítulos de este Short", self._subtitular)
        self.b_revisar = boton("Revisar sus subtítulos", "Abre sus subtítulos en la sección Subtítulos", self._revisar)
        b_dir = boton("Abrir carpeta", "La carpeta de resultados en el explorador",
                      lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(SALIDA)))
        botones = QHBoxLayout()
        for b in (self.b_ver, self.b_subs, self.b_revisar):
            botones.addWidget(b)
        botones.addStretch(1)
        botones.addWidget(b_dir)

        derecha = QWidget()
        d = QVBoxLayout(derecha)
        d.setContentsMargins(0, 0, 0, 0)
        d.addWidget(self.rep, 3)
        d.addWidget(self.info)
        d.addLayout(botones)
        d.addWidget(self.veredicto)
        d.addWidget(self.log, 2)
        div = QSplitter(Qt.Orientation.Horizontal)
        div.addWidget(self.lista)
        div.addWidget(derecha)
        div.setSizes([240, 620])
        lay = QVBoxLayout(self)
        lay.addWidget(cabecera(self.TITULO, "Lo que Claude va terminando aparece aquí solo. Suelta cualquier otro vídeo "
                                            "para verificarlo."))
        lay.addWidget(div, 1)
        self.al_carpetas()
        self._acciones(None)

    # ---- contrato de sección
    def traer_soltados(self, rutas):
        """Soltar un vídeo = verificarlo (no hace falta que lo haya hecho Claude)."""
        videos_ = [r for r in rutas if r.lower().endswith(VIDEO)]
        if not videos_:
            return
        for v in videos_:
            if v not in self.externos:
                self.externos.insert(0, v)
        self.recargar(seleccionar=videos_[0])
        self.verificar()

    def al_carpetas(self):
        self.recargar()

    def al_novedad(self, tipo, ruta):
        if tipo == "resultado":
            self.recargar(seleccionar=ruta)

    # ---- lista
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
        if not self.lista.count():
            self.info.setText("Aún no hay resultados.")

    def _actual(self):
        it = self.lista.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _elegido(self, it, _prev=None):
        v = it.data(Qt.ItemDataRole.UserRole) if it else None
        self._acciones(v)
        if v:
            self.rep.cargar(v)
            self.log.clear()
            self.veredicto.setText("")
            en_segundo_plano(lambda: (v, material.describir(v)), self._datos)

    def _datos(self, par):
        v, d = par
        if v != self._actual():
            return
        self.info.setText(resumen(d))
        vertical = (d.get("alto") or 0) > (d.get("ancho") or 0)
        self.b_ver.setEnabled(vertical)
        self.b_ver.setToolTip("" if vertical else "Solo para Shorts verticales: este es un clip horizontal")

    def _acciones(self, v):
        base = os.path.splitext(v)[0] if v else ""
        self.b_ver.setEnabled(bool(v))
        self.b_subs.setEnabled(bool(v) and "_subtitulado" not in base)
        self.b_revisar.setEnabled(bool(v) and os.path.exists(base + ".subtitulos.json"))

    def _subtitular(self):
        if self._actual():
            self.pedir.emit(f"/subtitular-short {para_claude(self._actual())}")

    def _revisar(self):
        if self._actual():
            self.revisar.emit(os.path.splitext(self._actual())[0] + ".subtitulos.json")

    def _menu(self, pos):
        it = self.lista.itemAt(pos) or self.lista.currentItem()
        if not it:
            return
        v = it.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        for b in (self.b_ver, self.b_subs, self.b_revisar):
            if b.isEnabled():
                menu.addAction(b.text(), b.click)
        menu.addAction("Preguntar a Claude por este vídeo…", lambda: self.pedir.emit(f"Mira el vídeo {para_claude(v)}: "))
        menu.addSeparator()
        menu.addAction("Abrir con el reproductor del sistema", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(v)))
        menu.exec(self.lista.mapToGlobal(pos))

    def verificar(self):
        v = self._actual()
        if not v or self._proc is not None:
            return
        args = [VERIFICAR, v] + ([] if "_subtitulado" in os.path.basename(v) else ["--sin-subtitulos"])
        self.log.clear()
        self.veredicto.setText("Verificando…")
        self._proc = ejecutar_cli(args, self.log, self._verificado, parent=self)

    def _verificado(self, _codigo):
        self._proc = None
        texto, clase = veredicto(self.log.toPlainText())
        self.veredicto.setText(texto)
        self.veredicto.setObjectName(clase)
        self.veredicto.style().unpolish(self.veredicto)
        self.veredicto.style().polish(self.veredicto)
