"""Revisión de subtítulos: vive DENTRO de «Resultados», no en su propia sección. Cuando el vídeo elegido en
Resultados tiene un <video>.subtitulos.json al lado, `RevisorSubtitulos` aparece bajo el reproductor con la tabla
editable de bloques (sincronizada con el vídeo que ya está reproduciendo Resultados); al terminar, guarda y avisa a
Claude de que ya puede quemarlos (paso 3 de /subtitular-short).

Es el mismo fichero que lee `subtitular.py quemar`: aquí solo se cambia el "texto" de cada bloque (si cambia el número
de palabras, quemar reparte los tiempos solo). Si Claude lo reescribe mientras está abierto, se recarga.
Teclado: Ctrl+S guarda; Ctrl+Intro en una fila salta a ese momento del vídeo (en el reproductor de Resultados).
"""
import glob
import os

from PySide6.QtCore import QFileSystemWatcher, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import QHeaderView, QHBoxLayout, QLabel, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from nucleo import archivos, material
from nucleo.rutas import REPO, SALIDA

from .comun import ayuda, boton, estado, nombrar


# ---------------------------------------------------------------- lógica (sin interfaz: pruebas/test_estudio.py)
def carpetas():
    """Donde puede haber subtítulos: junto a los Shorts montados por Claude y junto a los que se soltaron."""
    return [SALIDA, material.carpeta()]


def ficheros():
    fs = [f for c in carpetas() for f in glob.glob(os.path.join(c, "*.subtitulos.json"))]
    return sorted(set(fs), key=os.path.getmtime, reverse=True)


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
class TablaBloques(QTableWidget):
    saltar = Signal(int)

    def keyPressEvent(self, ev):
        if (ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and ev.modifiers() & Qt.KeyboardModifier.ControlModifier
                and self.currentRow() >= 0):
            self.saltar.emit(self.currentRow())
            return
        super().keyPressEvent(ev)


class RevisorSubtitulos(QWidget):
    """Tabla editable de los bloques de un <video>.subtitulos.json, para revisarlos con el vídeo que ya se está viendo
    en Resultados. `reproductor` es ESE reproductor (no tiene uno propio): `seguir(t)` resalta el bloque que suena
    (Resultados conecta ahí su señal `posicion`) y hacer clic en una fila salta ese reproductor a ese momento."""
    pedir = Signal(str)

    def __init__(self, reproductor, parent=None):
        super().__init__(parent)
        self.rep = reproductor
        self.ruta = None
        self.datos = None
        self.sucio = False
        self._actual = -1

        self.rotulo = QLabel()                              # vista previa: como saldrá quemado (caja negra, letra blanca)
        self.rotulo.setObjectName("rotulo")
        self.rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rotulo.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        self.rotulo.setStyleSheet("QLabel#rotulo { background: #000; color: #fff; padding: 8px; border-radius: 12px; }")
        nombrar(self.rotulo, "Subtítulo actual")
        self.tabla = nombrar(TablaBloques(0, 4), "Bloques de subtítulos",
                             "Edita la columna Texto. Control+Intro: ver ese momento en el vídeo.")
        self.tabla.setHorizontalHeaderLabels(["#", "Inicio", "Fin", "Texto (editable)"])
        self.tabla.verticalHeader().hide()
        cab = self.tabla.horizontalHeader()               # columnas que se ajustan solas (también al cambiar la letra)
        for c in range(3):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabla.cellClicked.connect(lambda fila, c: c < 3 and self._saltar(fila))
        self.tabla.saltar.connect(self._saltar)
        self.tabla.itemChanged.connect(self._editado)

        self.b_guardar = boton("Guardar", "Ctrl+S", self.guardar)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.guardar)
        self.b_ok = boton("Revisado: avisar a Claude", "Guarda y le dice a Claude que ya puede quemarlos", self.revisado)
        self.b_ok.setProperty("primario", True)
        self.estado = estado()
        self.vigia_json = QFileSystemWatcher(self)                       # solo el fichero abierto
        self.vigia_json.fileChanged.connect(self._cambio_externo)

        abajo = QHBoxLayout()
        abajo.addWidget(self.estado, 1)
        abajo.addWidget(self.b_guardar)
        abajo.addWidget(self.b_ok)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(ayuda("Subtítulos de este Short: corrige el texto y pulsa «Revisado»."))
        lay.addWidget(self.rotulo)
        lay.addWidget(self.tabla, 1)
        lay.addLayout(abajo)
        self.setVisible(False)

    # ---- abrir / mostrar
    def abrir(self, ruta):
        """`ruta` es el .subtitulos.json a revisar, o None para vaciar y ocultarse (el vídeo elegido no tiene)."""
        if ruta == self.ruta and self.datos is not None:
            return
        if self.sucio and not self._descartar():
            return
        if self.ruta and self.ruta in self.vigia_json.files():
            self.vigia_json.removePath(self.ruta)
        self.ruta = ruta
        self.datos = archivos.leer_json(ruta) if ruta and os.path.exists(ruta) else None
        if self.datos:
            self.vigia_json.addPath(ruta)
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
        self.tabla.blockSignals(False)
        self.sucio = False
        self._actual = -1
        self.b_ok.setEnabled(self.datos is not None)
        self.b_guardar.setEnabled(self.datos is not None)
        self._pintar_estado()

    def _saltar(self, fila):
        if self.datos and 0 <= fila < len(self.datos["bloques"]):
            self.rep.ir_a(self.datos["bloques"][fila]["ini"])

    def seguir(self, t):
        """Resultados conecta aquí la posición de SU reproductor: resalta el bloque que suena en ese instante."""
        if not self.datos:
            return
        i = bloque_en(self.datos["bloques"], t)
        if i == self._actual:
            return
        resalte = self.palette().color(QPalette.ColorRole.Highlight)
        resalte.setAlpha(110)
        self.tabla.blockSignals(True)             # resaltar no es editar: que no cuente como cambio sin guardar
        for fila in (self._actual, i):
            if 0 <= fila < self.tabla.rowCount():
                for c in range(4):
                    self.tabla.item(fila, c).setBackground(resalte if fila == i else Qt.GlobalColor.transparent)
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
        self.vigia_json.removePath(self.ruta)          # que nuestro propio guardado no cuente como cambio externo
        archivos.escribir_json(self.ruta, self.datos)
        self.vigia_json.addPath(self.ruta)
        self.sucio = False
        self._pintar_estado()
        return True

    def revisado(self):
        if not self.datos or not self.guardar():
            return
        rel = os.path.relpath(self.ruta, REPO).replace(os.sep, "/")
        self.pedir.emit(f"He revisado y guardado los subtítulos de {rel}. Ya puedes quemarlos y verificar el resultado.")
        self.estado.setText("Avisado a Claude (míralo en su panel).")

    def _cambio_externo(self, ruta):
        if ruta != self.ruta or not os.path.exists(ruta):
            return
        if self.sucio:
            self.estado.setText("Claude ha cambiado el fichero mientras editabas: guarda o recarga.")
            return
        self.datos = archivos.leer_json(ruta)
        self._llenar()
        self.vigia_json.addPath(ruta)                  # algunos editores reemplazan el fichero: volver a vigilarlo
        self.estado.setText("Recargado: Claude ha actualizado el fichero.")

    def _descartar(self):
        r = QMessageBox.question(self, "Cambios sin guardar", "Hay correcciones sin guardar. ¿Descartarlas?")
        return r == QMessageBox.StandardButton.Yes

    def _pintar_estado(self):
        if not self.datos:
            return
        n = len(self.datos["bloques"])
        self.estado.setText(f"{n} bloques · {'cambios SIN guardar (Ctrl+S)' if self.sucio else 'guardado'}")
