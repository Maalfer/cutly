"""Sección "Grabación → Short": Short vertical mudo a partir de grabaciones SUELTAS (sin registro de crear-shorts),
con intro o imágenes opcionales. Se sueltan VARIAS fuentes en el orden en que se quieren usar y Claude monta el plan y
el Short (/short-desde-grabacion). Metodología: editor/shorts/METODOLOGIA-SHORTS.md.

Teclado: Alt+↑/↓ mueven la fuente seleccionada, Supr la quita, «Añadir…» abre el selector (varias a la vez)."""
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget)

from nucleo import material

from ..entorno import en_segundo_plano, para_claude
from ..miniaturas import miniatura
from .comun import boton, cabecera, estado, nombrar, primario
from .fusion import titulo_valido
from .ranura import resumen, rutas_soltadas

FUENTES = material.VIDEO + material.IMAGEN


def _traer(rutas):
    """Trae las fuentes. Un archivo tiene UN papel: si ya tenía uno fijado (p. ej. es tu cara, en su ranura), se usa
    como fuente sin cambiárselo; la lista de esta sección es la que dice qué fuentes van y en qué orden."""
    out = []
    fijados = {e["archivo"] for e in material.sincronizar()["material"] if e.get("rol_manual")}
    for r in rutas:
        destino = material.anadir(r)
        if os.path.basename(destino) not in fijados:
            material.fijar_rol(destino, "imagen" if r.lower().endswith(material.IMAGEN) else "grabacion")
        out.append(destino)
    return out


class ListaFuentes(QListWidget):
    """Ranura MÚLTIPLE y ordenada: se sueltan ficheros dentro y se reordenan arrastrando o con Alt+↑/↓."""
    soltados = Signal(list)
    cambiada = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ranura")
        self.setIconSize(QSize(64, 64))
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setAcceptDrops(True)
        nombrar(self, "Fuentes del Short, en orden",
                "Suelta aquí vídeos e imágenes. Alt+flecha arriba o abajo para mover; Suprimir para quitar.")
        self.vacia = QLabel("Suelta aquí la grabación (y la intro o imágenes), en el orden del vídeo.", self)
        self.vacia.setObjectName("ayuda")
        self.vacia.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vacia.setWordWrap(True)
        self.model().rowsInserted.connect(self._vacio)
        self.model().rowsRemoved.connect(self._vacio)
        self.model().rowsMoved.connect(lambda *_: self.cambiada.emit())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.vacia.setGeometry(self.viewport().geometry().adjusted(12, 12, -12, -12))

    def _vacio(self, *_):
        self.vacia.setVisible(self.count() == 0)
        self.cambiada.emit()

    def keyPressEvent(self, ev):
        fila = self.currentRow()
        if ev.modifiers() & Qt.KeyboardModifier.AltModifier and ev.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and fila >= 0:
            destino = fila - 1 if ev.key() == Qt.Key.Key_Up else fila + 1
            if 0 <= destino < self.count():
                self.insertItem(destino, self.takeItem(fila))
                self.setCurrentRow(destino)
            return
        if ev.key() == Qt.Key.Key_Delete:
            for it in self.selectedItems():
                self.takeItem(self.row(it))
            return
        super().keyPressEvent(ev)

    def dragEnterEvent(self, ev):
        if ev.source() is self:
            return super().dragEnterEvent(ev)
        if rutas_soltadas(ev.mimeData(), FUENTES):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if ev.source() is self:
            return super().dragMoveEvent(ev)
        if rutas_soltadas(ev.mimeData(), FUENTES):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        if ev.source() is self:
            return super().dropEvent(ev)
        rutas = rutas_soltadas(ev.mimeData(), FUENTES)
        if rutas:
            ev.acceptProposedAction()
            self.soltados.emit(rutas)

    def rutas(self):
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]


class PanelGrabacion(QWidget):
    TITULO = "Grabación → Short"
    pedir = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lista = ListaFuentes()
        self.lista.soltados.connect(self.traer)
        self.lista.cambiada.connect(self._actualizar)
        b_anadir = boton("Añadir…", "Elegir fuentes (puedes elegir varias)", self._elegir)
        b_quitar = boton("Quitar", "Quita la fuente seleccionada de la lista (sigue en el material)",
                         lambda: [self.lista.takeItem(self.lista.row(it)) for it in self.lista.selectedItems()])
        self.titulo = nombrar(QLineEdit(), "Título del Short", "Opcional, en Capitalized-Kebab-Case")
        self.titulo.setPlaceholderText("Titulo-Con-Gancho (opcional)")
        self.titulo.textChanged.connect(self._actualizar)
        self.b = primario("Montar el Short con Claude", "Claude decide los planos (recorte, letterbox, paneos) y monta el "
                                                        "Short mudo con la banda para tu cara")
        self.b.clicked.connect(self._montar)
        self.estado = estado()

        acciones = QHBoxLayout()
        acciones.addWidget(b_anadir)
        acciones.addWidget(b_quitar)
        acciones.addStretch(1)
        fila = QHBoxLayout()
        etiqueta = QLabel("&Título:")
        etiqueta.setBuddy(self.titulo)
        fila.addWidget(etiqueta)
        fila.addWidget(self.titulo, 1)
        fila.addWidget(self.b)
        lay = QVBoxLayout(self)
        lay.addWidget(cabecera(self.TITULO, "Para una grabación que no viene de la VM (sin registro de pasos): suelta la "
                                            "grabación y, si quieres, una intro o imágenes, en el orden del vídeo. "
                                            "Después lo juntas con tu cara en «Cara + pantalla»."))
        lay.addWidget(self.lista, 1)
        lay.addLayout(acciones)
        lay.addLayout(fila)
        lay.addWidget(self.estado)
        self._actualizar()

    # ---- contrato de sección
    def traer_soltados(self, rutas):
        rutas = [r for r in rutas if r.lower().endswith(FUENTES)]
        if rutas:
            self.traer(rutas)

    # ---- interno
    def _elegir(self):
        filtro = "Vídeos e imágenes (" + " ".join("*" + e for e in FUENTES) + ")"
        rutas, _ = QFileDialog.getOpenFileNames(self, "Elegir fuentes", "", filtro)
        if rutas:
            self.traer(rutas)

    def traer(self, rutas):
        self.estado.setText(f"Trayendo {len(rutas)} archivo(s)…")
        en_segundo_plano(lambda: _traer(rutas), self._anadir,
                         lambda err: self.estado.setText(f"No se pudo traer: {err}"))

    def _anadir(self, destinos):
        entradas = {e["archivo"]: e for e in material.cargar()["material"]}
        for d in destinos:
            e = entradas.get(os.path.basename(d), {})
            it = QListWidgetItem(f"{os.path.basename(d)}\n{resumen(e)}")
            it.setData(Qt.ItemDataRole.UserRole, d)
            it.setToolTip(d)
            self.lista.addItem(it)
            en_segundo_plano(lambda r=d, du=e.get("duracion"): miniatura(r, du),
                             lambda png, item=it: png and item.setIcon(QIcon(QPixmap(png))))

    def _actualizar(self):
        t = self.titulo.text().strip()
        n = self.lista.count()
        self.b.setEnabled(n > 0 and (not t or titulo_valido(t)))
        if not n:
            self.estado.setText("Suelta al menos una grabación.")
        elif t and not titulo_valido(t):
            self.estado.setText("El título va en Capitalized-Kebab-Case, sin tildes ni símbolos.")
        else:
            self.estado.setText(f"{n} fuente(s), en este orden.")

    def _montar(self):
        partes = ["/short-desde-grabacion"] + [para_claude(r) for r in self.lista.rutas()]
        if self.titulo.text().strip():
            partes.append(self.titulo.text().strip())
        self.pedir.emit(" ".join(partes))
