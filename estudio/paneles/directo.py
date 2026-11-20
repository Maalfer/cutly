"""Sección "Directo → clips": sacar fragmentos de un directo.

1. Suelta el directo en su ranura (o pega un enlace) y pide la propuesta a Claude (/directo-a-clips).
2. Claude escribe su tabla en <directo>.candidatos.json (nucleo/candidatos.py): aparece aquí sola con el directo al
   lado; Intro o clic en un fragmento = saltar a ese momento; Espacio marca/desmarca.
3. "Cortar los elegidos con Claude": guarda la elección en ese JSON y se lo dice en la sesión.
Metodología: editor/directos/CLAUDE.md.
"""
import glob
import os

from PySide6.QtCore import QFileSystemWatcher, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from nucleo import candidatos, material

from ..entorno import para_claude
from .comun import boton, cabecera, estado, nombrar, primario
from .ranura import Ranura, duracion_txt
from .reproductor import Reproductor

COLS = ["Elegir", "★", "#", "Desde", "Hasta", "Dura", "Título", "Tema"]


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


class TablaFragmentos(QTableWidget):
    """Tabla accesible: Intro salta al fragmento, Espacio lo marca."""
    saltar = Signal(int)

    def keyPressEvent(self, ev):
        fila = self.currentRow()
        if fila >= 0 and ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.saltar.emit(fila)
            return
        if fila >= 0 and ev.key() == Qt.Key.Key_Space:
            it = self.item(fila, 0)
            it.setCheckState(Qt.CheckState.Unchecked if it.checkState() == Qt.CheckState.Checked
                             else Qt.CheckState.Checked)
            return
        super().keyPressEvent(ev)


class PanelDirecto(QWidget):
    TITULO = "Directo → clips"
    pedir = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.json = None
        self.datos = None
        self.ranura = Ranura("directo", "Directo", "el directo o la grabación larga")
        self.ranura.cambiado.connect(lambda _r: self._actualizar())
        self.url = nombrar(QLineEdit(), "Enlace del directo", "Un enlace de YouTube o Twitch en lugar del archivo")
        self.url.setPlaceholderText("…o pega un enlace de YouTube/Twitch")
        self.url.textChanged.connect(self._actualizar)
        self.b = primario("Proponer fragmentos con Claude", "Claude transcribe el directo y propone fragmentos")
        self.b.clicked.connect(self._proponer)

        self.combo = nombrar(QComboBox(), "Propuesta de fragmentos", "Qué propuesta se muestra (una por directo)")
        self.combo.currentIndexChanged.connect(lambda _i: self.abrir(self.combo.currentData()))
        self.rep = Reproductor()
        self.tabla = nombrar(TablaFragmentos(0, len(COLS)), "Fragmentos propuestos",
                             "Intro: ver el fragmento. Espacio: elegirlo.")
        self.tabla.setHorizontalHeaderLabels(COLS)
        self.tabla.verticalHeader().hide()
        cab = self.tabla.horizontalHeader()               # columnas que se ajustan solas (también al cambiar la letra)
        for c in range(len(COLS) - 1):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(len(COLS) - 1, QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setWordWrap(True)
        self.tabla.cellDoubleClicked.connect(lambda fila, _c: self._saltar(fila))
        self.tabla.cellClicked.connect(lambda fila, c: c != 0 and self._saltar(fila))
        self.tabla.saltar.connect(self._saltar)
        self.tabla.itemChanged.connect(self._marcado)
        self.b_cortar = boton("Cortar los elegidos con Claude", "Guarda tu elección y se la pasa a Claude", self._cortar)
        self.b_cortar.setProperty("primario", True)
        self.estado = estado()
        self.vigia_json = QFileSystemWatcher(self)                       # solo el fichero abierto
        self.vigia_json.fileChanged.connect(lambda r: r == self.json and self.abrir(r, forzar=True))

        fila = QHBoxLayout()
        fila.addWidget(self.url, 1)
        fila.addWidget(self.b)
        prop = QHBoxLayout()
        etiqueta = QLabel("&Propuesta:")
        etiqueta.setBuddy(self.combo)
        prop.addWidget(etiqueta)
        prop.addWidget(self.combo, 1)
        div = QSplitter(Qt.Orientation.Horizontal)
        div.addWidget(self.rep)
        div.addWidget(self.tabla)
        div.setSizes([260, 640])
        abajo = QHBoxLayout()
        abajo.addWidget(self.estado, 1)
        abajo.addWidget(self.b_cortar)
        lay = QVBoxLayout(self)
        lay.addWidget(cabecera(self.TITULO, "1. Suelta el directo (o pega un enlace) y pide la propuesta.  2. Los "
                                            "fragmentos aparecen abajo con el directo al lado.  3. Elige y pide que "
                                            "los corte."))
        fila_ranura = QHBoxLayout()
        fila_ranura.addWidget(self.ranura)
        fila_ranura.addStretch(1)
        lay.addLayout(fila_ranura)
        lay.addLayout(fila)
        lay.addLayout(prop)
        lay.addWidget(div, 1)
        lay.addLayout(abajo)
        self._actualizar()
        self.al_carpetas()

    # ---- contrato de sección
    def traer_soltados(self, rutas):
        videos = [r for r in rutas if r.lower().endswith(material.VIDEO)]
        if videos:
            self.ranura.traer(videos[0])

    def al_material(self, m):
        self.ranura.cargar_actual(m)

    def al_carpetas(self):
        actual = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for f in propuestas():
            self.combo.addItem(os.path.basename(f), f)
        i = self.combo.findData(actual) if actual else 0
        self.combo.setCurrentIndex(max(i, 0) if self.combo.count() else -1)
        self.combo.blockSignals(False)
        self.abrir(self.combo.currentData())

    def al_novedad(self, tipo, ruta):
        if tipo == "propuesta":
            self.al_carpetas()
            i = self.combo.findData(ruta)
            if i >= 0:
                self.combo.setCurrentIndex(i)

    # ---- paso 1
    def _actualizar(self):
        self.b.setEnabled(bool(self.ranura.ruta or self.url.text().strip().startswith("http")))

    def _proponer(self):
        url = self.url.text().strip()
        self.pedir.emit(f"/directo-a-clips {url if url.startswith('http') else para_claude(self.ranura.ruta)}")

    # ---- pasos 2 y 3
    def abrir(self, ruta, forzar=False):
        if ruta and ruta == self.json and not forzar:
            return
        if self.json and self.json in self.vigia_json.files():
            self.vigia_json.removePath(self.json)
        self.json = ruta
        self.datos = candidatos.cargar(ruta) if ruta and os.path.exists(ruta) else None
        if ruta and os.path.exists(ruta):
            self.vigia_json.addPath(ruta)
            video = directo_de(ruta, self.datos)
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
            marca.setData(Qt.ItemDataRole.AccessibleTextRole, f"Elegir el fragmento {f['n']}")
            self.tabla.setItem(i, 0, marca)
            valores = ["★" if f.get("estrella") else "", str(f["n"]), candidatos.hhmmss(f["inicio"]),
                       candidatos.hhmmss(f["fin"]), duracion_txt(float(f["fin"]) - float(f["inicio"])), f["titulo"],
                       f.get("tema", "")]
            for c, v in enumerate(valores, start=1):
                it = QTableWidgetItem(v)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setToolTip(f.get("tema", ""))
                if c == 1 and v:
                    it.setData(Qt.ItemDataRole.AccessibleTextRole, "destacado")
                self.tabla.setItem(i, c, it)
        self.tabla.resizeRowsToContents()
        self.tabla.blockSignals(False)
        self._pintar_estado()

    def _saltar(self, fila):
        if self.datos and 0 <= fila < len(self.datos["fragmentos"]):
            self.rep.ir_a(float(self.datos["fragmentos"][fila]["inicio"]))
            self.rep.player.play()

    def _marcado(self, it):
        if it.column() == 0 and self.datos:
            self.datos["fragmentos"][it.row()]["elegido"] = it.checkState() == Qt.CheckState.Checked
            self._pintar_estado()

    def _pintar_estado(self):
        if not self.datos:
            self.estado.setText("Aún no hay propuesta: suelta un directo arriba y pide fragmentos a Claude. "
                                "Cuando la escriba, aparecerá aquí sola.")
            self.b_cortar.setEnabled(False)
            return
        problemas = candidatos.validar(self.datos)
        n = sum(1 for f in self.datos["fragmentos"] if f.get("elegido"))
        texto = f"{len(self.datos['fragmentos'])} fragmentos propuestos · {n} elegido(s)"
        if not directo_de(self.json, self.datos):
            texto += " · no encuentro el directo para verlo"
        if problemas:
            texto += " · AVISO: " + "; ".join(problemas[:2])
        self.estado.setText(texto)
        self.b_cortar.setEnabled(n > 0)

    def _cortar(self):
        if not self.datos:
            return
        self.vigia_json.removePath(self.json)               # nuestro guardado no cuenta como cambio de Claude
        candidatos.guardar(self.json, self.datos)
        self.vigia_json.addPath(self.json)
        m = mensaje_elegidos(self.json, self.datos)
        if m:
            self.pedir.emit(m)
