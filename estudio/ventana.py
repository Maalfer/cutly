"""Ventana principal de cutly estudio: Claude Code (el instalado, con su interfaz completa) a la izquierda; a la
derecha, las pestañas visuales (VM, Shorts, Subtítulos); arriba, un botón por flujo de trabajo (las skills)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QTabWidget, QToolBar

from .entorno import REPO
from .flujos import flujos
from .paneles.shorts import PanelShorts
from .paneles.subtitulos import PanelSubtitulos
from .paneles.vm import PanelVM
from .terminal.widget import TerminalClaude


class Ventana(QMainWindow):
    def __init__(self, comando):
        super().__init__()
        self.comando = comando
        self.setWindowTitle("cutly estudio")
        self.resize(1700, 980)

        self.terminal = None
        self.div = QSplitter(Qt.Orientation.Horizontal)
        self.pestanas = QTabWidget()
        self.vm = PanelVM()
        self.shorts = PanelShorts()
        self.subs = PanelSubtitulos()
        self.subs.avisar.connect(lambda texto: self.enviar(texto))
        self.pestanas.addTab(self.vm, "VM")
        self.pestanas.addTab(self.shorts, "Shorts")
        self.pestanas.addTab(self.subs, "Subtítulos")
        self.div.addWidget(QLabel())                      # sitio del terminal
        self.div.addWidget(self.pestanas)
        self.div.setSizes([1000, 700])
        self.setCentralWidget(self.div)

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
        self.div.setSizes([1000, 700])
        self.statusBar().showMessage(f"sesión: {' '.join(comando)}  (en {REPO})")
        self.terminal.setFocus()

    def enviar(self, texto):
        if not self.terminal.enviar(texto):
            self.statusBar().showMessage("La sesión de Claude Code no está activa: abre una nueva (barra de arriba).")

    def _sesion_terminada(self, codigo):
        self.statusBar().showMessage(f"La sesión terminó (código {codigo}). 'Nueva sesión' o 'Continuar' para seguir.")

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

    def closeEvent(self, ev):
        if self.terminal is not None:
            self.terminal.cerrar()
        super().closeEvent(ev)
