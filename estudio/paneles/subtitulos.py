"""Pestaña Subtítulos: revisar y corregir el <video>.subtitulos.json que deja `subtitular.py preparar` (paso 3 de
/subtitular-short) con el vídeo sincronizado, guardar, y avisar a Claude Code de que ya está revisado.

Es el mismo fichero que lee `subtitular.py quemar`: aquí solo se cambia el "texto" de cada bloque (si cambia el número
de palabras, quemar reparte los tiempos solo). Si Claude lo reescribe mientras está abierto, se recarga.
"""
import glob
import os

from PySide6.QtCore import QFileSystemWatcher, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from nucleo import archivos
from nucleo.rutas import REPO, SALIDA

from .reproductor import Reproductor


# ---------------------------------------------------------------- lógica (sin interfaz: pruebas/test_estudio.py)
def ficheros():
    return sorted(glob.glob(os.path.join(SALIDA, "*.subtitulos.json")), key=os.path.getmtime, reverse=True)


def video_de(ruta_json, datos):
    """El vídeo al que pertenecen los subtítulos: el campo "video" junto al JSON, o <base>.mp4."""
    d = os.path.dirname(ruta_json)
    if datos.get("video") and os.path.exists(os.path.join(d, datos["video"])):
        return os.path.join(d, datos["video"])
    return ruta_json[: -len(".subtitulos.json")] + ".mp4"


def bloque_en(bloques, t):
    """Índice del bloque que se ve en el instante t (el último que ya ha empezado), o -1."""
    i = -1
    for k, b in enumerate(bloques):
        if b["ini"] - 0.03 <= t:
            i = k
        else:
            break
    return i


def aplicar_textos(datos, textos):
    """Copia los textos editados a los bloques (solo "texto"; tiempos y palabras intactos)."""
    for b, t in zip(datos["bloques"], textos):
        b["texto"] = " ".join(t.split())
    return datos


# ---------------------------------------------------------------- interfaz
class PanelSubtitulos(QWidget):
    avisar = Signal(str)          # mensaje para la sesión de Claude Code

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ruta = None
        self.datos = None
        self.sucio = False
        self._actual = -1

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(lambda _: self.abrir(self.combo.currentData()))
        self.rep = Reproductor()
        self.rep.posicion.connect(self._sigue)
        self.rotulo = QLabel()
        self.rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rotulo.setFont(QFont("Inter", 18, QFont.Weight.Bold))
        self.rotulo.setStyleSheet("background:#000;color:#fff;padding:8px;border-radius:12px;")

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["#", "Inicio", "Fin", "Texto (editable)"])
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabla.verticalHeader().hide()
        self.tabla.cellClicked.connect(lambda fila, _c: self.rep.ir_a(self.datos["bloques"][fila]["ini"]))
        self.tabla.itemChanged.connect(self._editado)

        self.b_guardar = QPushButton("Guardar")
        self.b_guardar.clicked.connect(self.guardar)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.guardar)
        b_ok = QPushButton("Revisado: avisar a Claude para quemarlos")
        b_ok.setToolTip("Guarda y escribe en la sesión de Claude Code que ya están revisados (paso 3 de /subtitular-short)")
        b_ok.clicked.connect(self.revisado)
        self.estado = QLabel()

        arriba = QHBoxLayout()
        arriba.addWidget(QLabel("Subtítulos:"))
        arriba.addWidget(self.combo, 1)
        abajo = QHBoxLayout()
        abajo.addWidget(self.estado, 1)
        abajo.addWidget(self.b_guardar)
        abajo.addWidget(b_ok)

        izq = QWidget()
        li = QVBoxLayout(izq)
        li.setContentsMargins(0, 0, 0, 0)
        li.addWidget(self.rep, 1)
        li.addWidget(self.rotulo)
        div = QSplitter(Qt.Orientation.Horizontal)
        div.addWidget(izq)
        div.addWidget(self.tabla)
        div.setSizes([380, 520])
        lay = QVBoxLayout(self)
        lay.addLayout(arriba)
        lay.addWidget(div, 1)
        lay.addLayout(abajo)

        os.makedirs(SALIDA, exist_ok=True)
        self.vigia = QFileSystemWatcher([SALIDA], self)
        self.vigia.directoryChanged.connect(lambda _: self.recargar_lista())
        self.vigia.fileChanged.connect(self._cambio_externo)
        self.recargar_lista()

    # ---- lista de ficheros
    def recargar_lista(self):
        actual = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for f in ficheros():
            self.combo.addItem(os.path.basename(f), f)
        i = self.combo.findData(actual) if actual else (0 if self.combo.count() else -1)
        self.combo.setCurrentIndex(max(i, 0) if self.combo.count() else -1)
        self.combo.blockSignals(False)
        if self.combo.currentData() != self.ruta:
            self.abrir(self.combo.currentData())
        if not self.combo.count():
            self.estado.setText("No hay ningún .subtitulos.json en editor/videos-editados/ "
                                "(lo crea /subtitular-short, paso 1)")

    # ---- abrir / mostrar
    def abrir(self, ruta):
        if ruta == self.ruta and self.datos is not None:
            return
        if self.sucio and not self._descartar():
            return
        if self.ruta and self.ruta in self.vigia.files():
            self.vigia.removePath(self.ruta)
        self.ruta = ruta
        self.datos = archivos.leer_json(ruta) if ruta else None
        if ruta:
            self.vigia.addPath(ruta)
            self.rep.cargar(video_de(ruta, self.datos))
        self._llenar()

    def _llenar(self):
        self.tabla.blockSignals(True)
        bloques = self.datos["bloques"] if self.datos else []
        self.tabla.setRowCount(len(bloques))
        for i, b in enumerate(bloques):
            for c, v in enumerate((str(i + 1), f"{b['ini']:.2f}", f"{b['fin']:.2f}", b["texto"])):
                it = QTableWidgetItem(v)
                if c < 3:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabla.setItem(i, c, it)
        self.tabla.resizeColumnsToContents()
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabla.blockSignals(False)
        self.sucio = False
        self._actual = -1
        self._pintar_estado()

    def _sigue(self, t):
        if not self.datos:
            return
        i = bloque_en(self.datos["bloques"], t)
        if i == self._actual:
            return
        self.tabla.blockSignals(True)             # resaltar no es editar: que no cuente como cambio sin guardar
        for fila in (self._actual, i):
            if 0 <= fila < self.tabla.rowCount():
                color = QColor("#2d4f7c") if fila == i else QColor(0, 0, 0, 0)
                for c in range(4):
                    self.tabla.item(fila, c).setBackground(color)
        self.tabla.blockSignals(False)
        self._actual = i
        if i >= 0:
            self.tabla.scrollToItem(self.tabla.item(i, 0))
            self.rotulo.setText(self.tabla.item(i, 3).text())
        else:
            self.rotulo.setText("")

    # ---- edición / guardado
    def _editado(self, _it):
        self.sucio = True
        self._pintar_estado()

    def textos(self):
        return [self.tabla.item(i, 3).text() for i in range(self.tabla.rowCount())]

    def guardar(self):
        if not self.datos:
            return False
        aplicar_textos(self.datos, self.textos())
        self.vigia.removePath(self.ruta)              # que nuestro propio guardado no cuente como cambio externo
        archivos.escribir_json(self.ruta, self.datos)
        self.vigia.addPath(self.ruta)
        self.sucio = False
        self._pintar_estado()
        return True

    def revisado(self):
        if not self.datos or not self.guardar():
            return
        rel = os.path.relpath(self.ruta, REPO).replace(os.sep, "/")
        self.avisar.emit(f"He revisado y guardado los subtítulos de {rel}. Ya puedes quemarlos y verificar el resultado.")
        self.estado.setText("Avisado a Claude Code (mira la sesión a la izquierda).")

    def _cambio_externo(self, ruta):
        if ruta != self.ruta or not os.path.exists(ruta):
            return
        if self.sucio:
            self.estado.setText("Claude ha cambiado el fichero mientras editabas: guarda o recarga.")
            return
        self.datos = archivos.leer_json(ruta)
        self._llenar()
        self.vigia.addPath(ruta)                      # algunos editores reemplazan el fichero: volver a vigilarlo
        self.estado.setText("Recargado: Claude ha actualizado el fichero.")

    def _descartar(self):
        r = QMessageBox.question(self, "Cambios sin guardar", "Hay correcciones sin guardar. ¿Descartarlas?")
        return r == QMessageBox.StandardButton.Yes

    def _pintar_estado(self):
        if not self.datos:
            return
        n = len(self.datos["bloques"])
        self.estado.setText(f"{n} bloques · {'cambios SIN guardar' if self.sucio else 'guardado'}")
