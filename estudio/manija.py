"""ManijaPanel: tira para ensanchar o encoger a mano un QDockWidget acoplado.

El separador nativo de QMainWindow debería bastar, pero cuando el contenido del panel es un QWebEngineView (el
terminal de Claude Code, con su motor Chromium) este se come los eventos de ratón justo en el borde y el arrastre
no responde (medido). Esta tira es un QWidget normal, sin motor web, que vive DENTRO del panel, a un lado de su
contenido, y hace el redimensionado ella misma: `resizeDocks()` por sí solo es solo una pista para el siguiente
layout y no siempre cuaja (medido), así que mientras se arrastra se fija el ancho exacto del panel (`setFixedWidth`,
que si obliga a Qt a aplicarlo ya) y solo al soltar se le devuelve la libertad de tamaño (para que la ventana lo
pueda seguir repartiendo al redimensionarse o maximizarse). Funciona también con el teclado (←/→ con el foco en la
tira) para quien no pueda arrastrar con el ratón.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget

ANCHO = 8
PASO_TECLADO = 24
MAXIMO_QT = 16777215        # QWIDGETSIZE_MAX: "sin límite" para Qt


class ManijaPanel(QWidget):
    def __init__(self, ventana, dock, lado="izquierda", minimo=280, hueco=260, parent=None):
        super().__init__(parent)
        self._ventana = ventana
        self._dock = dock
        # la manija vive en el borde del panel que toca al resto de la ventana: moverse hacia ESE lado (alejando el
        # ratón del panel) tiene que ensancharlo, no encogerlo.
        self._signo = -1 if lado == "izquierda" else 1
        self._minimo = minimo
        self._hueco = hueco             # ancho a dejarle siempre al resto de la ventana
        self._arrastre = None
        self.setObjectName("manija_panel")
        self.setFixedWidth(ANCHO)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Ensanchar o encoger el panel de Claude Code")
        self.setToolTip("Arrastra para ensanchar o encoger el panel de Claude Code (con el foco aquí: ← →)")

    def _maximo(self):
        return max(self._minimo, self._ventana.width() - self._hueco)

    def _fijar(self, ancho):
        nuevo = max(self._minimo, min(self._maximo(), round(ancho)))
        self._dock.setFixedWidth(nuevo)

    def _soltar(self):
        self._dock.setMinimumWidth(self._minimo)
        self._dock.setMaximumWidth(MAXIMO_QT)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and not self._dock.isFloating():
            self._arrastre = (ev.globalPosition().x(), self._dock.width())
            # el terminal (QWebEngineView) tiene su propia ventana nativa (Chromium): en cuanto el ratón, ya
            # arrastrando, pasa por encima suyo, su captura nativa puede robarle los eventos a esta tira y el
            # arrastre se vuelve errático (medido con OpenCode, cuyo contenido llega hasta el borde). Una
            # captura EXPLÍCITA de Qt (a nivel de SO) tiene prioridad sobre eso durante todo el arrastre.
            self.grabMouse(Qt.CursorShape.SizeHorCursor)
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._arrastre is None:
            return
        x0, ancho0 = self._arrastre
        dx = (ev.globalPosition().x() - x0) * self._signo
        self._fijar(ancho0 + dx)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._arrastre is not None:
            self._soltar()
            self.releaseMouse()
        self._arrastre = None
        ev.accept()

    def keyPressEvent(self, ev):
        # ← se comporta como arrastrar hacia la izquierda (ensancha aquí); → como arrastrar hacia la derecha
        if ev.key() == Qt.Key.Key_Left:
            self._fijar(self._dock.width() - PASO_TECLADO * self._signo)
        elif ev.key() == Qt.Key.Key_Right:
            self._fijar(self._dock.width() + PASO_TECLADO * self._signo)
        else:
            super().keyPressEvent(ev)
            return
        QTimer.singleShot(0, self._soltar)      # una pulsación no tiene "soltar": se libera en el siguiente ciclo
