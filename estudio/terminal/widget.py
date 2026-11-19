"""TerminalClaude: el Claude Code INSTALADO corriendo de verdad (pseudo-terminal) y mostrado con xterm.js dentro de Qt.

Es la misma interfaz y la misma sesión que en cualquier terminal: comandos, permisos, tareas en segundo plano... Lo
único que añade la app es poder escribir en ella desde un botón (`enviar`), como si lo tecleara el usuario.

    t = TerminalClaude(["claude"], cwd=REPO)        # o ["claude", "--continue"] para retomar la última sesión
    t.enviar("/subtitular-short")                    # escribe y pulsa Enter en la sesión
"""
import json
import os
import sys
import tempfile
import time

from PySide6.QtCore import QEvent, QFile, QIODevice, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from .pty import ProcesoPty

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal.html")


class Puente(QObject):
    """Lo que ve el JavaScript de terminal.html (QWebChannel)."""
    datos = Signal(str)            # Python -> xterm.js: salida del programa
    foco = Signal()
    estilo = Signal(str)           # JSON {letra, fondo, texto, lector}: tamaño de letra, colores, modo lector

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


def _ficheros(mime):
    return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()] if mime.hasUrls() else []


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
    """La página del terminal: lleva la consola de JavaScript a stderr y NO navega nunca después de cargar (soltar un
    vídeo encima la llevaría a ese fichero y el terminal desaparecería)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cargada = False
        self.loadFinished.connect(lambda ok: setattr(self, "cargada", self.cargada or ok))

    def javaScriptConsoleMessage(self, nivel, mensaje, linea, origen):
        print(f"[terminal.html:{linea}] {mensaje}", file=sys.stderr)

    def acceptNavigationRequest(self, url, tipo, principal):
        return not (self.cargada and principal)


# si la app se abrió desde dentro de otra sesión de Claude Code, esa sesión deja estas variables: el Claude de la app
# se creería una sesión hija (p. ej. no guardaría su conversación)
HEREDADAS = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID",
             "CLAUDE_EFFORT", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_BRIDGE_SESSION_ID",
             "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN"}     # las de configuración (p. ej. modelo) se quedan


class TerminalClaude(QWebEngineView):
    terminado = Signal(int)
    estado = Signal(str, str)      # (trabajando | necesita | libre, mensaje): lo que dicen los hooks de Claude Code

    def __init__(self, argv, cwd=None, parent=None):
        super().__init__(parent)
        self.setPage(_Pagina(self))
        # los hooks del proyecto (.claude/settings.json -> estudio/hooks/estado_claude.py) escriben aquí en qué está
        # ESTA sesión; heredan la variable del entorno de `claude`, así que otras sesiones no la tocan
        self.fichero_estado = os.path.join(tempfile.gettempdir(), f"cutly_estado_{os.getpid()}_{id(self)}.json")
        env = {k: v for k, v in os.environ.items() if k not in HEREDADAS and not k.startswith("CLAUDE_CODE_CHILD")}
        env["CUTLY_ESTADO_FICHERO"] = self.fichero_estado
        self.proceso = ProcesoPty(argv, cwd=cwd, env=env, parent=self)
        self.ultima_salida = time.monotonic()      # mientras Claude trabaja su indicador escribe sin parar
        self.proceso.salida.connect(lambda _d: setattr(self, "ultima_salida", time.monotonic()))
        self._visto = 0.0
        self._t_estado = QTimer(self, interval=500, timeout=self._leer_estado)
        self._t_estado.start()
        self.proceso.terminado.connect(self.terminado)
        self.puente = Puente(self.proceso, self)
        canal = QWebChannel(self.page())
        canal.registerObject("puente", self.puente)
        self.page().setWebChannel(canal)
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)   # xterm.js del CDN
        self.setHtml(_html(), QUrl.fromLocalFile(HTML))
        self.page().loadFinished.connect(self._vigilar_arrastres)
        self.page().loadFinished.connect(lambda _ok: getattr(self, "_estilo", None) and self.puente.estilo.emit(self._estilo))
        self.setAccessibleName("Sesión de Claude Code")
        self.setAccessibleDescription("Terminal con Claude Code. Control+C con texto seleccionado copia; sin selección "
                                      "interrumpe. Control+V pega.")

    # ---- soltar ficheros encima = pegar su ruta en la sesión (como en cualquier terminal)
    def _vigilar_arrastres(self, _ok=True):
        fp = self.focusProxy()          # el widget interno de WebEngine es el que recibe los arrastres
        if fp is not None and not getattr(self, "_vigilando", False):
            fp.installEventFilter(self)
            self._vigilando = True

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove) and _ficheros(ev.mimeData()):
            ev.acceptProposedAction()
            return True
        if t == QEvent.Type.Drop and _ficheros(ev.mimeData()):
            rutas = " ".join(f'"{r}"' if " " in r else r for r in _ficheros(ev.mimeData()))
            self.proceso.escribir("[200~" + rutas + " [201~")     # pegado: Claude Code lo trata como texto
            ev.acceptProposedAction()
            self.setFocus()
            return True
        return super().eventFilter(obj, ev)

    def ajustar(self, letra=14, fondo="#1e1e1e", texto="#d4d4d4", lector=False):
        """Tamaño de letra, colores y modo lector de pantalla de xterm.js (lo aplica en caliente)."""
        import json
        self._estilo = json.dumps({"letra": letra, "fondo": fondo, "texto": texto, "lector": lector})
        self.puente.estilo.emit(self._estilo)

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

    def _leer_estado(self):
        try:
            mt = os.path.getmtime(self.fichero_estado)
        except OSError:
            return
        if mt == self._visto:
            return
        self._visto = mt
        try:
            with open(self.fichero_estado, encoding="utf-8") as f:
                e = json.load(f)
        except (OSError, ValueError):
            return
        self.estado.emit(e.get("estado", ""), e.get("mensaje", ""))

    def cerrar(self):
        self._t_estado.stop()
        self.proceso.cerrar()
        try:
            os.remove(self.fichero_estado)
        except OSError:
            pass
