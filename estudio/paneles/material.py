"""Pestaña Material: la biblioteca de todo lo aportado (como el panel de medios de un editor). Se arrastra aquí (o a
cualquier parte de la ventana) y desde aquí se puede arrastrar a las ranuras de las demás pestañas. Cada archivo
lleva su papel (deducido o fijado) y el menú contextual le pide a Claude el flujo que toca."""
import os

from PySide6.QtCore import QFileSystemWatcher, QMimeData, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from nucleo import material

from ..entorno import en_segundo_plano, para_claude
from ..miniaturas import miniatura
from .ranura import resumen, rutas_soltadas

TODO = material.VIDEO + material.AUDIO + material.IMAGEN


class ListaMaterial(QListWidget):
    """La lista: suelta ficheros dentro y arrastra sus elementos (como ficheros) hacia las ranuras."""
    soltados = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(160, 120))
        self.setGridSize(QSize(190, 190))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def mimeData(self, items):                          # arrastrar elementos = arrastrar sus ficheros
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(it.data(Qt.ItemDataRole.UserRole)) for it in items])
        return m

    def mimeTypes(self):
        return ["text/uri-list"]

    def dragEnterEvent(self, ev):
        if ev.source() is self:
            return super().dragEnterEvent(ev)
        if rutas_soltadas(ev.mimeData(), TODO):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if ev.source() is not self and rutas_soltadas(ev.mimeData(), TODO):
            ev.acceptProposedAction()
        else:
            super().dragMoveEvent(ev)

    def dropEvent(self, ev):
        if ev.source() is self:
            return
        rutas = rutas_soltadas(ev.mimeData(), TODO)
        if rutas:
            ev.acceptProposedAction()
            self.soltados.emit(rutas)


def _traer_varios(rutas):
    destinos = [material.anadir(r) for r in rutas]
    material.sincronizar()
    return destinos


class PanelMaterial(QWidget):
    pedir = Signal(str)                 # mensaje / comando para la sesión de Claude Code
    cambiado = Signal(dict)             # el manifiesto, cada vez que cambia (lo usan las ranuras y la barra de estado)

    def __init__(self, parent=None):
        super().__init__(parent)
        aviso = QLabel("Arrastra aquí vídeos, audio o imágenes (o suéltalos en cualquier parte de la ventana). "
                       "Para darles un papel concreto, arrástralos a la ranura de su pestaña (Fusión, Subtítulos, "
                       "Directo) o usa el menú del botón derecho.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color:#aaa")
        self.lista = ListaMaterial()
        self.lista.soltados.connect(self.traer)
        self.lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        self.lista.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.ItemDataRole.UserRole))))
        self.estado = QLabel()
        b_claude = QPushButton("Contar a Claude qué material hay")
        b_claude.setToolTip("Le pide que lea el inventario (python editor/comun/material.py)")
        b_claude.clicked.connect(lambda: self.pedir.emit(
            "Mira el material que he aportado: `python editor/comun/material.py` (papel de cada archivo en "
            "editor/crudo/material.json)."))
        abajo = QHBoxLayout()
        abajo.addWidget(self.estado, 1)
        abajo.addWidget(b_claude)
        lay = QVBoxLayout(self)
        lay.addWidget(aviso)
        lay.addWidget(self.lista, 1)
        lay.addLayout(abajo)

        os.makedirs(material.carpeta(), exist_ok=True)
        self._pendiente = QTimer(self, singleShot=True, interval=600, timeout=self.recargar)
        self.vigia = QFileSystemWatcher([material.carpeta()], self)
        self.vigia.directoryChanged.connect(lambda _: self._pendiente.start())   # agrupa ráfagas de cambios
        self._iconos = {}
        self.recargar()

    # ---- datos
    def traer(self, rutas):
        self.estado.setText(f"Trayendo {len(rutas)} archivo(s)…")
        en_segundo_plano(lambda: _traer_varios(rutas), lambda _d: self.recargar(),
                         lambda err: self.estado.setText(f"No se pudo traer: {err}"))

    def recargar(self):
        en_segundo_plano(material.sincronizar, self._pintar)

    def _pintar(self, m):
        seleccion = {it.data(Qt.ItemDataRole.UserRole) for it in self.lista.selectedItems()}
        self.lista.clear()
        for e in m["material"]:
            ruta = os.path.join(material.carpeta(), e["archivo"])
            it = QListWidgetItem(f"{e['archivo']}\n[{e['rol']}{' ✓' if e.get('rol_manual') else ''}] {resumen(e)}")
            it.setData(Qt.ItemDataRole.UserRole, ruta)
            it.setToolTip(f"{ruta}\npapel: {e['rol']} — {material.ROLES.get(e['rol'], '')}"
                          f"{' (fijado por ti)' if e.get('rol_manual') else ' (deducido)'}")
            if ruta in self._iconos:
                it.setIcon(self._iconos[ruta])
            else:
                en_segundo_plano(lambda r=ruta, d=e.get("duracion"): (r, miniatura(r, d)), self._poner_icono)
            self.lista.addItem(it)
            it.setSelected(ruta in seleccion)
        n = len(m["material"])
        self.estado.setText(f"{n} archivo(s) en el material" if n else "Aún no hay material: arrástralo aquí.")
        self.cambiado.emit(m)

    def _poner_icono(self, par):
        ruta, png = par
        if not png:
            return
        icono = QIcon(QPixmap(png))
        self._iconos[ruta] = icono
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == ruta:
                self.lista.item(i).setIcon(icono)

    # ---- menú contextual
    def _menu(self, pos):
        items = self.lista.selectedItems()
        if not items:
            return
        rutas = [it.data(Qt.ItemDataRole.UserRole) for it in items]
        entradas = {e["archivo"]: e for e in material.cargar()["material"]}
        roles = [entradas.get(os.path.basename(r), {}).get("rol") for r in rutas]
        menu = QMenu(self)

        claude = menu.addMenu("Pedir a Claude")
        for texto, mensaje in acciones_claude(rutas, roles):
            claude.addAction(texto, lambda m=mensaje: self.pedir.emit(m))
        claude.setEnabled(not claude.isEmpty())

        papel = menu.addMenu("Papel")
        for rol, desc in material.ROLES.items():
            a = papel.addAction(f"{rol} — {desc}")
            a.setCheckable(True)
            a.setChecked(len(set(roles)) == 1 and roles[0] == rol)
            a.triggered.connect(lambda _=False, r=rol: self._fijar(rutas, r))
        menu.addSeparator()
        menu.addAction("Abrir", lambda: [QDesktopServices.openUrl(QUrl.fromLocalFile(r)) for r in rutas])
        menu.addAction("Mostrar en la carpeta", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(material.carpeta())))
        menu.addAction("Quitar del material…", lambda: self._quitar(rutas))
        menu.exec(self.lista.mapToGlobal(pos))

    def _fijar(self, rutas, rol):
        en_segundo_plano(lambda: [material.fijar_rol(r, rol) for r in rutas], lambda _: self.recargar())

    def _quitar(self, rutas):
        enlazados = [r for r in rutas if os.stat(r).st_nlink > 1]
        texto = f"¿Quitar {len(rutas)} archivo(s) del material?"
        if enlazados:
            texto += f"\n\n{len(enlazados)} son enlaces al original: el original NO se borra."
        if len(enlazados) < len(rutas):
            texto += "\n\nLos que se copiaron se borran del material (el original, si lo había, sigue donde estaba)."
        if QMessageBox.question(self, "Quitar material", texto) == QMessageBox.StandardButton.Yes:
            for r in rutas:
                os.remove(r)
            self.recargar()


def acciones_claude(rutas, roles):
    """Qué se le puede pedir a Claude con una selección, según el papel de cada archivo -> [(texto, mensaje)]."""
    por = {}
    for r, rol in zip(rutas, roles):
        por.setdefault(rol, []).append(r)
    out = []
    if por.get("cara") and por.get("pantalla"):
        out.append(("Fusionar cara + pantalla",
                    f"/fusionar-cara-pantalla {para_claude(por['cara'][0])} {para_claude(por['pantalla'][0])}"))
    for r in por.get("short", []):
        out.append((f"Subtitular {os.path.basename(r)}", f"/subtitular-short {para_claude(r)}"))
    for r in por.get("directo", []):
        out.append((f"Proponer clips de {os.path.basename(r)}", f"/directo-a-clips {para_claude(r)}"))
    for r in por.get("toma", []):
        nombre = os.path.splitext(os.path.basename(r))[0]
        out.append((f"Construir el Short de la toma {nombre}",
                    f"Construye el Short mudo de la toma {nombre} con `python editor/shorts/short_desde_toma.py "
                    f"{nombre} --titulo <Titulo-Con-Gancho>` (propón tú el título) y revisa el mapa de edición."))
    if rutas:
        lista = ", ".join(f"{para_claude(r)} ({rol})" for r, rol in zip(rutas, roles))
        out.append(("Preguntar a Claude por esto…", f"Mira este material: {lista}. "))
    return out
