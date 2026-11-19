"""Sección "Material": la biblioteca de todo lo aportado (como el panel de medios de un editor). Se suelta aquí (o en
cualquier sección sin sitio propio) y desde aquí se arrastra a las ranuras de las demás secciones. Cada archivo lleva
su papel (deducido o fijado) y el menú le pide a Claude el flujo que toca. El inventario lo trae el vigía central.

Teclado: Intro abre, Supr quita, tecla Menú (o Mayús+F10) abre las acciones: papel y "Pedir a Claude"."""
import os

from PySide6.QtCore import QMimeData, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QVBoxLayout, QWidget)

from nucleo import material

from ..entorno import en_segundo_plano, para_claude
from ..miniaturas import miniatura
from .comun import boton, cabecera, estado, nombrar
from .ranura import resumen, rutas_soltadas

TODO = material.VIDEO + material.AUDIO + material.IMAGEN


class ListaMaterial(QListWidget):
    """La lista: suelta ficheros dentro y arrastra sus elementos (como ficheros) hacia las ranuras."""
    soltados = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(160, 120))
        self.setGridSize(QSize(200, 200))
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
    return [material.anadir(r) for r in rutas]


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
    grabaciones = por.get("grabacion", []) + por.get("imagen", [])
    if grabaciones:
        out.append(("Montar un Short con esto", "/short-desde-grabacion " + " ".join(para_claude(r) for r in grabaciones)))
    for r in por.get("toma", []):
        nombre = os.path.splitext(os.path.basename(r))[0]
        out.append((f"Construir el Short de la toma {nombre}",
                    f"Construye el Short mudo de la toma {nombre} con `python editor/shorts/short_desde_toma.py "
                    f"{nombre} --titulo <Titulo-Con-Gancho>` (propón tú el título) y revisa el mapa de edición."))
    if rutas:
        lista = ", ".join(f"{para_claude(r)} ({rol})" for r, rol in zip(rutas, roles))
        out.append(("Preguntar a Claude por esto…", f"Mira este material: {lista}. "))
    return out


class PanelMaterial(QWidget):
    TITULO = "Material"
    pedir = Signal(str)                 # mensaje / comando para la sesión de Claude Code
    actualizar = Signal()               # "sincroniza ya" (lo atiende el vigía central)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lista = nombrar(ListaMaterial(), "Material",
                             "Todo lo aportado. Intro: abrir. Suprimir: quitar. Tecla Menú: papel y pedir a Claude.")
        self.lista.soltados.connect(self.traer)
        self.lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        self.lista.itemActivated.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.ItemDataRole.UserRole))))
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.lista, activated=lambda: self._quitar(self._seleccion()),
                  context=Qt.ShortcutContext.WidgetShortcut)
        self.estado = estado()
        b_anadir = boton("Añadir…", "Elegir archivos para el material", self._elegir)
        b_claude = boton("Contar a Claude qué material hay",
                         "Le pide que lea el inventario (python editor/comun/material.py)",
                         lambda: self.pedir.emit("Mira el material que he aportado: `python editor/comun/material.py` "
                                                 "(papel de cada archivo en editor/crudo/material.json)."))
        abajo = QHBoxLayout()
        abajo.addWidget(self.estado, 1)
        abajo.addWidget(b_anadir)
        abajo.addWidget(b_claude)
        lay = QVBoxLayout(self)
        lay.addWidget(cabecera(self.TITULO, "Todo lo que has aportado, con su papel. Suelta aquí lo que sea, o "
                                            "arrástralo desde aquí a la sección donde lo quieras usar."))
        lay.addWidget(self.lista, 1)
        lay.addLayout(abajo)
        self._iconos = {}
        self.estado.setText("Cargando el material…")

    # ---- contrato de sección
    def traer_soltados(self, rutas):
        self.traer(rutas)

    def al_material(self, m):
        self._pintar(m)

    # ---- datos
    def _elegir(self):
        filtro = "Material (" + " ".join("*" + e for e in TODO) + ")"
        rutas, _ = QFileDialog.getOpenFileNames(self, "Añadir al material", "", filtro)
        if rutas:
            self.traer(rutas)

    def traer(self, rutas):
        self.estado.setText(f"Trayendo {len(rutas)} archivo(s)…")
        en_segundo_plano(lambda: _traer_varios(rutas), lambda _d: self.actualizar.emit(),
                         lambda err: self.estado.setText(f"No se pudo traer: {err}"))

    def _seleccion(self):
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.lista.selectedItems()]

    def _pintar(self, m):
        seleccion = set(self._seleccion())
        self.lista.clear()
        for e in m["material"]:
            ruta = os.path.join(material.carpeta(), e["archivo"])
            fijado = " ✓" if e.get("rol_manual") else ""
            it = QListWidgetItem(f"{e['archivo']}\n{e['rol']}{fijado} · {resumen(e)}")
            it.setData(Qt.ItemDataRole.UserRole, ruta)
            it.setData(Qt.ItemDataRole.AccessibleTextRole, f"{e['archivo']}, papel {e['rol']}, {resumen(e)}")
            it.setToolTip(f"{ruta}\npapel: {e['rol']} — {material.ROLES.get(e['rol'], '')}"
                          f"{' (fijado por ti)' if e.get('rol_manual') else ' (deducido)'}")
            if ruta in self._iconos:
                it.setIcon(self._iconos[ruta])
            else:
                en_segundo_plano(lambda r=ruta, d=e.get("duracion"): (r, miniatura(r, d)), self._poner_icono)
            self.lista.addItem(it)
            it.setSelected(ruta in seleccion)
        n = len(m["material"])
        self.estado.setText(f"{n} archivo(s) en el material" if n else "Aún no hay material: suéltalo aquí o en la "
                                                                       "sección de lo que quieras hacer.")

    def _poner_icono(self, par):
        ruta, png = par
        if not png:
            return
        icono = QIcon(QPixmap(png))
        self._iconos[ruta] = icono
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.ItemDataRole.UserRole) == ruta:
                self.lista.item(i).setIcon(icono)

    # ---- menú contextual (también con la tecla Menú)
    def _menu(self, pos):
        rutas = self._seleccion()
        if not rutas:
            return
        entradas = {e["archivo"]: e for e in material.cargar()["material"]}
        roles = [entradas.get(os.path.basename(r), {}).get("rol") for r in rutas]
        menu = QMenu(self)
        claude = menu.addMenu("&Pedir a Claude")
        for texto, mensaje in acciones_claude(rutas, roles):
            claude.addAction(texto, lambda m=mensaje: self.pedir.emit(m))
        claude.setEnabled(not claude.isEmpty())
        papel = menu.addMenu("P&apel")
        for rol, desc in material.ROLES.items():
            a = papel.addAction(f"{rol} — {desc}")
            a.setCheckable(True)
            a.setChecked(len(set(roles)) == 1 and roles[0] == rol)
            a.triggered.connect(lambda _=False, r=rol: self._fijar(rutas, r))
        menu.addSeparator()
        menu.addAction("&Abrir", lambda: [QDesktopServices.openUrl(QUrl.fromLocalFile(r)) for r in rutas])
        menu.addAction("Mostrar en la &carpeta",
                       lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(material.carpeta())))
        menu.addAction("&Quitar del material…", lambda: self._quitar(rutas))
        menu.exec(self.lista.mapToGlobal(pos))

    def _fijar(self, rutas, rol):
        en_segundo_plano(lambda: [material.fijar_rol(r, rol) for r in rutas], lambda _: self.actualizar.emit())

    def _quitar(self, rutas):
        if not rutas:
            return
        enlazados = [r for r in rutas if os.stat(r).st_nlink > 1]
        texto = f"¿Quitar {len(rutas)} archivo(s) del material?"
        if enlazados:
            texto += f"\n\n{len(enlazados)} son enlaces al original: el original NO se borra."
        if len(enlazados) < len(rutas):
            texto += "\n\nLos que se copiaron se borran del material (el original, si lo había, sigue donde estaba)."
        if QMessageBox.question(self, "Quitar material", texto) == QMessageBox.StandardButton.Yes:
            for r in rutas:
                os.remove(r)
            self.actualizar.emit()
