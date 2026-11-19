"""Ventana principal de cutly estudio: Claude Code (el instalado, con su interfaz completa) a la izquierda; a la
derecha, una pestaña por cosa que se quiere hacer; arriba, un botón por flujo (las skills).

El material NO se coloca en carpetas a mano: se arrastra a la pestaña de lo que quieres hacer. Cada pestaña sabe qué
hacer con lo que se suelta en ella (`traer_soltados`: a su ranura, a su lista, a verificar...); si la pestaña no
tiene sitio para material, va a Material. Todo lo que una pestaña le pide a Claude llega por `pedir` a la sesión.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QTabWidget, QToolBar

from .entorno import REPO
from .flujos import flujos
from .paneles.directo import PanelDirecto
from .paneles.fusion import PanelFusion
from .paneles.grabacion import PanelGrabacion
from .paneles.material import TODO, PanelMaterial
from .paneles.ranura import rutas_soltadas
from .paneles.shorts import PanelShorts
from .paneles.subtitulos import PanelSubtitulos
from .paneles.vm import PanelVM
from .terminal.widget import TerminalClaude


class Ventana(QMainWindow):
    def __init__(self, comando):
        super().__init__()
        self.comando = comando
        self.setWindowTitle("cutly estudio")
        self.resize(1700, 1000)
        self.setAcceptDrops(True)

        self.terminal = None
        self.div = QSplitter(Qt.Orientation.Horizontal)
        self.pestanas = QTabWidget()
        self.material = PanelMaterial()
        self.fusion = PanelFusion()
        self.grabacion = PanelGrabacion()
        self.subs = PanelSubtitulos()
        self.directo = PanelDirecto()
        self.shorts = PanelShorts()
        self.vm = PanelVM()
        # una pestaña por cosa que se quiere hacer, y en cada una, dónde soltar su material
        for panel, nombre, ayuda in (
                (self.directo, "Directo → clips", "Suelta un directo: Claude propone fragmentos, eliges y los corta"),
                (self.fusion, "Cara + pantalla", "Suelta tu cara y el Short de pantalla: Claude los junta"),
                (self.grabacion, "Grabación → Short", "Suelta grabaciones sueltas (e intro, imágenes): Short mudo"),
                (self.subs, "Subtítulos", "Suelta un Short montado: subtítulos y revisión del texto"),
                (self.shorts, "Resultados", "Lo que ha salido; suelta cualquier vídeo para verificarlo"),
                (self.material, "Material", "Todo lo aportado y su papel; suelta aquí lo que sea"),
                (self.vm, "VM", "La máquina virtual de las demos")):
            self.pestanas.addTab(panel, nombre)
            self.pestanas.setTabToolTip(self.pestanas.count() - 1, ayuda)
            if hasattr(panel, "pedir"):
                panel.pedir.connect(self.pedir)

        # el material manda: cuando cambia, las ranuras muestran lo último asignado a su papel
        self.material.cambiado.connect(self._material_cambiado)
        self.shorts.revisar.connect(self._revisar_subtitulos)

        self.div.addWidget(QLabel())                      # sitio del terminal
        self.div.addWidget(self.pestanas)
        self.div.setSizes([950, 750])
        self.setCentralWidget(self.div)

        self.l_vm = QLabel()
        self.l_material = QLabel()
        self.statusBar().addPermanentWidget(self.l_material)
        self.statusBar().addPermanentWidget(self.l_vm)
        self.vm.resumen.connect(self.l_vm.setText)

        self._barra_flujos()
        self.nueva_sesion(self.comando)

    # ---- Claude Code
    def nueva_sesion(self, comando):
        if self.terminal is not None:
            self.terminal.cerrar()
            self.terminal.deleteLater()
        self.terminal = TerminalClaude(comando, cwd=REPO)
        self.terminal.terminado.connect(self._sesion_terminada)
        self.div.replaceWidget(0, self.terminal)
        self.div.setSizes([950, 750])
        self.statusBar().showMessage(f"sesión: {' '.join(comando)}  (en {REPO})", 8000)
        self.terminal.setFocus()

    def pedir(self, texto):
        """Lo que una pestaña le pide a Claude. Si acaba en espacio, se deja escrito para que lo completes tú."""
        self.enviar(texto, intro=not texto.endswith(" "))

    def enviar(self, texto, intro=True):
        if not self.terminal.enviar(texto, intro):
            self.statusBar().showMessage("La sesión de Claude Code no está activa: abre una nueva (barra de arriba).")
            return
        self.terminal.setFocus()

    def _sesion_terminada(self, codigo):
        self.statusBar().showMessage(f"La sesión terminó (código {codigo}). 'Nueva sesión' o 'Continuar' para seguir.")

    def _material_cambiado(self, m):
        self.fusion.cargar(m)
        self.directo.cargar(m)
        self.subs.ranura.cargar_actual(m)
        n = len(m["material"])
        roles = sorted({e["rol"] for e in m["material"]})
        self.l_material.setText(f"material: {n}" + (f" ({', '.join(roles)})" if roles else "") + "   ")

    def _revisar_subtitulos(self, ruta_json):
        self.subs.recargar_lista()
        i = self.subs.combo.findData(ruta_json)
        if i >= 0:
            self.subs.combo.setCurrentIndex(i)
        self.pestanas.setCurrentWidget(self.subs)

    # ---- soltar fuera de una ranura: lo decide la pestaña visible (o va a Material)
    def dragEnterEvent(self, ev):
        if rutas_soltadas(ev.mimeData(), TODO):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        rutas = rutas_soltadas(ev.mimeData(), TODO)
        if not rutas:
            return
        ev.acceptProposedAction()
        panel = self.pestanas.currentWidget()
        destino = panel if hasattr(panel, "traer_soltados") else self.material
        destino.traer_soltados(rutas)
        nombre = self.pestanas.tabText(self.pestanas.indexOf(destino))
        self.statusBar().showMessage(f"{len(rutas)} archivo(s) a «{nombre}»", 6000)

    # ---- barra de flujos
    def _barra_flujos(self):
        barra = QToolBar("Flujos")
        barra.setMovable(False)
        self.addToolBar(barra)
        a = QAction("Nueva sesión", self, triggered=lambda: self.nueva_sesion(["claude"]))
        a.setToolTip("Abre una sesión nueva de Claude Code en el repo")
        barra.addAction(a)
        a = QAction("Continuar la última", self, triggered=lambda: self.nueva_sesion(["claude", "--continue"]))
        a.setToolTip("claude --continue: retoma la conversación más reciente de este repo")
        barra.addAction(a)
        barra.addSeparator()
        for f in flujos():
            a = QAction(f["rotulo"], self)
            a.setToolTip(f"{f['comando']} {f['argumentos']}\n\n{f['descripcion']}".strip())
            a.triggered.connect(lambda _=False, c=f["comando"]: self.enviar(c))
            barra.addAction(a)
        # atajos: Ctrl+1..6 para las pestañas, Ctrl+` para volver al terminal
        for i in range(self.pestanas.count()):
            atajo = QAction(self, shortcut=QKeySequence(f"Ctrl+{i + 1}"))
            atajo.triggered.connect(lambda _=False, k=i: self.pestanas.setCurrentIndex(k))
            self.addAction(atajo)
        volver = QAction(self, shortcut=QKeySequence("Ctrl+`"), triggered=lambda: self.terminal.setFocus())
        self.addAction(volver)

    def closeEvent(self, ev):
        if self.terminal is not None:
            self.terminal.cerrar()
        super().closeEvent(ev)

