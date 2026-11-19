"""Pestaña "Directo → clips": sacar fragmentos de un directo.

1. Suelta el directo en su ranura (o pega un enlace) y pide la propuesta a Claude (/directo-a-clips).
2. Claude escribe su tabla en <directo>.candidatos.json (nucleo/candidatos.py): aquí aparece con el directo al lado;
   clic en un fragmento = saltar a ese momento; marca los que quieres.
3. "Cortar los elegidos con Claude": guarda la elección en ese JSON y se lo dice en la sesión.
Metodología: editor/directos/CLAUDE.md.
"""
import glob
import os

from PySide6.QtCore import QFileSystemWatcher, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from nucleo import candidatos, material

from ..entorno import para_claude
from .ranura import Ranura, duracion_txt
from .reproductor import Reproductor

COLS = ["✓", "★", "#", "Desde", "Hasta", "Dura", "Título", "Tema"]


def propuestas():
    """Ficheros de candidatos que haya (los escribe Claude junto a cada directo), el más reciente primero."""
    fs = glob.glob(os.path.join(material.carpeta(), "*.candidatos.json"))
    return sorted(fs, key=os.path.getmtime, reverse=True)


def directo_de(ruta_json, datos):
    d = os.path.join(os.path.dirname(ruta_json), datos.get("directo", ""))
    return d if datos.get("directo") and os.path.exists(d) else None


def mensaje_elegidos(ruta_json, datos):
    elegidos = [f for f in datos["fragmentos"] if f.get("elegido")]
    if not elegidos:
        return None
    lista = ", ".join(f"{f['n']} ({f['titulo']})" for f in elegidos)
    directo = datos.get("directo", "")
    return (f"Del directo {directo} quiero los fragmentos {lista} (marcados \"elegido\" en "
            f"{para_claude(ruta_json)}). Córtalos siguiendo editor/directos/CLAUDE.md y verifica cada empalme.")


class PanelDirecto(QWidget):
    pedir = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.json = None
        self.datos = None
        explica = QLabel("<b>1.</b> Suelta el directo (o pega un enlace) y pide la propuesta. <b>2.</b> Claude te "
                         "propone fragmentos: aparecen abajo con el directo al lado. <b>3.</b> Marca los que quieres y "
                         "pide que los corte.")
        explica.setWordWrap(True)
        self.ranura = Ranura("directo", "Directo", "el directo o la grabación larga")
        self.ranura.cambiado.connect(lambda _r: self._actualizar())
        self.url = QLineEdit()
        self.url.setPlaceholderText("…o pega un enlace de YouTube/Twitch")
        self.url.textChanged.connect(self._actualizar)
        self.b = QPushButton("Proponer fragmentos con Claude")
        self.b.setMinimumHeight(34)
        self.b.clicked.connect(self._proponer)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(lambda _i: self.abrir(self.combo.currentData()))
        self.rep = Reproductor()
        self.tabla = QTableWidget(0, len(COLS))
        self.tabla.setHorizontalHeaderLabels(COLS)
        self.tabla.verticalHeader().hide()
        self.tabla.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.cellClicked.connect(self._saltar)
        self.tabla.itemChanged.connect(self._marcado)
        self.b_cortar = QPushButton("Cortar los elegidos con Claude")
        self.b_cortar.setMinimumHeight(34)
        self.b_cortar.clicked.connect(self._cortar)
        self.estado = QLabel()
        self.estado.setStyleSheet("color:#aaa")

        fila = QHBoxLayout()
        fila.addWidget(self.url, 1)
        fila.addWidget(self.b)
        prop = QHBoxLayout()
        prop.addWidget(QLabel("Propuesta:"))
        prop.addWidget(self.combo, 1)
        div = QSplitter(Qt.Orientation.Horizontal)
        div.addWidget(self.rep)
        div.addWidget(self.tabla)
        div.setSizes([340, 560])
        abajo = QHBoxLayout()
        abajo.addWidget(self.estado, 1)
        abajo.addWidget(self.b_cortar)
        lay = QVBoxLayout(self)
        lay.addWidget(explica)
        lay.addWidget(self.ranura)
        lay.addLayout(fila)
        lay.addLayout(prop)
        lay.addWidget(div, 1)
        lay.addLayout(abajo)

        os.makedirs(material.carpeta(), exist_ok=True)
        self.vigia = QFileSystemWatcher([material.carpeta()], self)
        self.vigia.directoryChanged.connect(lambda _: self.recargar())
        self.vigia.fileChanged.connect(lambda r: r == self.json and self.abrir(r, forzar=True))
        self._actualizar()
        self.recargar()

    # ---- paso 1
    def cargar(self, m):
        self.ranura.cargar_actual(m)

    def _actualizar(self):
        self.b.setEnabled(bool(self.ranura.ruta or self.url.text().strip().startswith("http")))

    def _proponer(self):
        url = self.url.text().strip()
        self.pedir.emit(f"/directo-a-clips {url if url.startswith('http') else para_claude(self.ranura.ruta)}")

    def traer_soltados(self, rutas):
        """Soltar en cualquier parte de la pestaña = a la ranura del directo."""
        videos = [r for r in rutas if r.lower().endswith(material.VIDEO)]
        if videos:
            self.ranura.traer(videos[0])

    # ---- pasos 2 y 3
    def recargar(self):
        actual = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for f in propuestas():
            self.combo.addItem(os.path.basename(f), f)
        i = self.combo.findData(actual) if actual else 0
        self.combo.setCurrentIndex(max(i, 0) if self.combo.count() else -1)
        self.combo.blockSignals(False)
        self.abrir(self.combo.currentData())

    def abrir(self, ruta, forzar=False):
        if ruta == self.json and not forzar:
            return
        if self.json and self.json in self.vigia.files():
            self.vigia.removePath(self.json)
        self.json = ruta
        self.datos = candidatos.cargar(ruta) if ruta and os.path.exists(ruta) else None
        if ruta:
            self.vigia.addPath(ruta)
            video = directo_de(ruta, self.datos or {})
            if video and not forzar:
                self.rep.cargar(video)
        self._llenar()

    def _llenar(self):
        self.tabla.blockSignals(True)
        fr = self.datos["fragmentos"] if self.datos else []
        self.tabla.setRowCount(len(fr))
        for i, f in enumerate(fr):
            marca = QTableWidgetItem()
            marca.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            marca.setCheckState(Qt.CheckState.Checked if f.get("elegido") else Qt.CheckState.Unchecked)
            self.tabla.setItem(i, 0, marca)
            valores = ["★" if f.get("estrella") else "", str(f["n"]), candidatos.hhmmss(f["inicio"]),
                       candidatos.hhmmss(f["fin"]), duracion_txt(float(f["fin"]) - float(f["inicio"])), f["titulo"],
                       f.get("tema", "")]
            for c, v in enumerate(valores, start=1):
                it = QTableWidgetItem(v)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if f.get("estrella"):
                    it.setForeground(QColor("#ffd479"))
                it.setToolTip(f.get("tema", ""))
                self.tabla.setItem(i, c, it)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.tabla.blockSignals(False)
        self._pintar_estado()

    def _saltar(self, fila, columna):
        if self.datos and columna != 0:
            self.rep.ir_a(float(self.datos["fragmentos"][fila]["inicio"]))
            self.rep.player.play()

    def _marcado(self, it):
        if it.column() == 0 and self.datos:
            self.datos["fragmentos"][it.row()]["elegido"] = it.checkState() == Qt.CheckState.Checked
            self._pintar_estado()

    def _pintar_estado(self):
        if not self.datos:
            self.estado.setText("Aún no hay propuesta: suelta un directo arriba y pide fragmentos a Claude.")
            self.b_cortar.setEnabled(False)
            return
        problemas = candidatos.validar(self.datos)
        n = sum(1 for f in self.datos["fragmentos"] if f.get("elegido"))
        texto = f"{len(self.datos['fragmentos'])} fragmentos propuestos · {n} elegido(s)"
        if not directo_de(self.json, self.datos):
            texto += " · (no encuentro el directo para verlo)"
        if problemas:
            texto += " · AVISO: " + "; ".join(problemas[:2])
        self.estado.setText(texto)
        self.b_cortar.setEnabled(n > 0)

    def _cortar(self):
        if not self.datos:
            return
        self.vigia.removePath(self.json)               # nuestro guardado no cuenta como cambio de Claude
        candidatos.guardar(self.json, self.datos)
        self.vigia.addPath(self.json)
        m = mensaje_elegidos(self.json, self.datos)
        if m:
            self.pedir.emit(m)
