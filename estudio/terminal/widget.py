"""TerminalClaude: el Claude Code INSTALADO corriendo de verdad (pseudo-terminal) y mostrado con xterm.js dentro de Qt.

Es la misma interfaz y la misma sesión que en cualquier terminal: comandos, permisos, tareas en segundo plano... Lo
único que añade la app es poder escribir en ella desde un botón (`enviar`), como si lo tecleara el usuario.

    t = TerminalClaude(["claude"], cwd=REPO)        # o ["claude", "--continue"] para retomar la última sesión
    t.enviar("/subtitular-short")                    # escribe y pulsa Enter en la sesión
"""
import os

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
import sys

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from .pty import ProcesoPty

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal.html")


class Puente(QObject):
    """Lo que ve el JavaScript de terminal.html (QWebChannel)."""
    datos = Signal(str)            # Python -> xterm.js: salida del programa
    foco = Signal()

    def __init__(self, proceso, parent=None):
        super().__init__(parent)
        self.proceso = proceso
        self.arrancado = False
        self._pendiente = []
        # la salida llega a trozos muy pequeños mientras Claude Code redibuja: se agrupa cada 16 ms (60 Hz)
        self._timer = QTimer(self, interval=16, singleShot=True, timeout=self._volcar)
        proceso.salida.connect(self._acumular)

    def _acumular(self, texto):
        self._pendiente.append(texto)
        if not self._timer.isActive():
            self._timer.start()

    def _volcar(self):
        if self._pendiente:
            self.datos.emit("".join(self._pendiente))
            self._pendiente.clear()

    @Slot(str)
    def entrada(self, texto):
        self.proceso.escribir(texto)

    @Slot(int, int)
    def tam(self, columnas, filas):
        self.proceso.redimensionar(columnas, filas)

    @Slot(int, int)
    def listo(self, columnas, filas):
        if not self.arrancado:            # el programa arranca ya con el tamaño real de la ventana
            self.arrancado = True
            self.proceso.iniciar(columnas, filas)

    @Slot(str)
    def copiar(self, texto):
        QGuiApplication.clipboard().setText(texto)

    @Slot()
    def pegar(self):
        texto = QGuiApplication.clipboard().text()
        if texto:
            # pegado entre corchetes: el programa lo trata como texto pegado, no como teclas (Claude Code lo entiende)
            self.proceso.escribir("\x1b[200~" + texto.replace("\r\n", "\n") + "\x1b[201~")

    @Slot(str)
    def abrir(self, url):
        QDesktopServices.openUrl(QUrl(url))


def _html():
    """terminal.html con qwebchannel.js DENTRO: una página local no puede cargarlo de qrc:/ (medido:
    "QWebChannel is not defined"), así que se lee de los recursos de Qt y se inserta."""
    f = QFile(":/qtwebchannel/qwebchannel.js")
    f.open(QIODevice.OpenModeFlag.ReadOnly)
    canal_js = bytes(f.readAll()).decode("utf-8")
    f.close()
    with open(HTML, encoding="utf-8") as fh:
        html = fh.read()
    marca = '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>'
    assert marca in html, "terminal.html ya no tiene la etiqueta de qwebchannel.js que hay que sustituir"
    return html.replace(marca, f"<script>{canal_js}</script>")


class _Pagina(QWebEnginePage):
    """Lleva los mensajes de la consola de JavaScript a stderr (para diagnosticar la carga de xterm.js)."""
    def javaScriptConsoleMessage(self, nivel, mensaje, linea, origen):
        print(f"[terminal.html:{linea}] {mensaje}", file=sys.stderr)


class TerminalClaude(QWebEngineView):
    terminado = Signal(int)

    def __init__(self, argv, cwd=None, parent=None):
        super().__init__(parent)
        self.setPage(_Pagina(self))
        self.proceso = ProcesoPty(argv, cwd=cwd, parent=self)
        self.proceso.terminado.connect(self.terminado)
        self.puente = Puente(self.proceso, self)
        canal = QWebChannel(self.page())
        canal.registerObject("puente", self.puente)
        self.page().setWebChannel(canal)
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)   # xterm.js del CDN
        self.setHtml(_html(), QUrl.fromLocalFile(HTML))

    def enviar(self, texto, intro=True):
        """Escribe `texto` en la sesión (como si lo tecleara el usuario) y, si intro, pulsa Enter."""
        if not self.proceso.vivo():
            return False
        self.proceso.escribir(texto)
        if intro:
            # Enter aparte y un instante después: si llega pegado al texto, Claude Code lo toma como parte de él
            QTimer.singleShot(150, lambda: self.proceso.escribir("\r"))
        self.puente.foco.emit()
        return True

    def cerrar(self):
        self.proceso.cerrar()
