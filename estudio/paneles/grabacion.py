"""Pestaña "Grabación → Short": Short vertical mudo a partir de grabaciones SUELTAS (sin registro de crear-shorts),
con intro o imágenes opcionales. Se sueltan VARIAS fuentes en el orden en que se quieren usar (se reordenan
arrastrándolas) y Claude monta el plan y el Short (/short-desde-grabacion). Metodología:
editor/shorts/METODOLOGIA-SHORTS.md."""
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

from nucleo import material

from ..entorno import en_segundo_plano, para_claude
from ..miniaturas import miniatura
from .fusion import titulo_valido
from .ranura import rutas_soltadas

FUENTES = material.VIDEO + material.IMAGEN


def _traer(rutas):
    """Trae las fuentes. Un archivo tiene UN papel: si ya tenía uno fijado (p. ej. es tu cara, en su ranura), se usa
    como fuente sin cambiárselo; la lista de esta pestaña es la que dice qué fuentes van y en qué orden."""
    out = []
    fijados = {e["archivo"] for e in material.sincronizar()["material"] if e.get("rol_manual")}
    for r in rutas:
        destino = material.anadir(r)
        if os.path.basename(destino) not in fijados:
            material.fijar_rol(destino, "imagen" if r.lower().endswith(material.IMAGEN) else "grabacion")
        out.append(destino)
    return out


class ListaFuentes(QListWidget):
    """Ranura MÚLTIPLE y ordenada: se sueltan ficheros dentro y se reordenan arrastrando."""
    soltados = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(64, 64))
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)   # reordenar
        self.setAcceptDrops(True)
        self.setStyleSheet("QListWidget { border: 2px dashed #555; border-radius: 10px; background: #262626; }")

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
    pedir = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        explica = QLabel("Para una grabación que <b>no</b> viene de la VM (sin registro de pasos): suelta aquí la "
                         "grabación y, si quieres, una intro o imágenes, <b>en el orden del vídeo</b> (arrástralas para "
                         "reordenar). Claude decide los planos (recorte, letterbox, paneos) y monta el Short mudo con la "
                         "banda para tu cara; después lo juntas con tu cara en «Cara + pantalla».")
        explica.setWordWrap(True)
        self.lista = ListaFuentes()
        self.lista.soltados.connect(self.traer)
        b_quitar = QPushButton("Quitar seleccionada")
        b_quitar.clicked.connect(lambda: [self.lista.takeItem(self.lista.row(it)) for it in self.lista.selectedItems()]
                                 and self._actualizar())
        self.titulo = QLineEdit()
        self.titulo.setPlaceholderText("Titulo-Con-Gancho (opcional)")
        self.titulo.textChanged.connect(self._actualizar)
        self.b = QPushButton("Montar el Short con Claude")
        self.b.setMinimumHeight(34)
        self.b.clicked.connect(self._montar)
        self.estado = QLabel()
        self.estado.setStyleSheet("color:#aaa")
        self.lista.model().rowsInserted.connect(lambda *_: self._actualizar())
        self.lista.model().rowsRemoved.connect(lambda *_: self._actualizar())

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Título:"))
        fila.addWidget(self.titulo, 1)
        fila.addWidget(self.b)
        lay = QVBoxLayout(self)
        lay.addWidget(explica)
        lay.addWidget(QLabel("<b>Fuentes</b> (suéltalas aquí, en orden):"))
        lay.addWidget(self.lista, 1)
        lay.addWidget(b_quitar, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addLayout(fila)
        lay.addWidget(self.estado)
        self._actualizar()

    def traer(self, rutas):
        self.estado.setText(f"Trayendo {len(rutas)} archivo(s)…")
        en_segundo_plano(lambda: _traer(rutas), self._anadir,
                         lambda err: self.estado.setText(f"No se pudo traer: {err}"))

    def _anadir(self, destinos):
        entradas = {e["archivo"]: e for e in material.cargar()["material"]}
        for d in destinos:
            e = entradas.get(os.path.basename(d), {})
            it = QListWidgetItem(f"{os.path.basename(d)}   [{e.get('rol', '')}]")
            it.setData(Qt.ItemDataRole.UserRole, d)
            it.setToolTip(d)
            self.lista.addItem(it)
            en_segundo_plano(lambda r=d, du=e.get("duracion"): miniatura(r, du),
                             lambda png, item=it: png and item.setIcon(QIcon(QPixmap(png))))
        self._actualizar()

    def _actualizar(self):
        t = self.titulo.text().strip()
        n = self.lista.count()
        ok = n > 0 and (not t or titulo_valido(t))
        self.b.setEnabled(ok)
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

    def traer_soltados(self, rutas):
        """Lo que se suelta en cualquier parte de la pestaña."""
        self.traer([r for r in rutas if r.lower().endswith(FUENTES)])
