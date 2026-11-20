"""Ranura de material: el sitio de una sección donde se SUELTA un archivo con un papel ("Cara", "Pantalla", "Short a
subtitular"...). Soltarlo lo trae al material (editor/crudo/, sin copiar si está en el mismo disco) y le fija ese
papel en material.json; así Claude sabe qué es cada archivo.

Accesible sin ratón: tiene foco de teclado; Intro/Espacio abre el selector de archivos, Supr la vacía y Ctrl+V pega
una ruta copiada (o un archivo copiado en el explorador).
"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QPixmap
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from nucleo import material

from ..apariencia import repintar
from ..entorno import en_segundo_plano
from ..miniaturas import miniatura
from .comun import ayuda, boton


def rutas_soltadas(mime, extensiones=None):
    """Ficheros locales de un arrastre o del portapapeles (filtrados por extensión si se da). Acepta también texto
    con rutas, una por línea (lo que deja "copiar como ruta" del explorador)."""
    out = []
    if mime.hasUrls():
        out = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
    elif mime.hasText():
        out = [l.strip().strip('"') for l in mime.text().splitlines() if l.strip()]
    return [p for p in out if p and os.path.isfile(p) and (not extensiones or p.lower().endswith(extensiones))]


def duracion_txt(seg):
    if not seg:
        return ""
    m, s = divmod(int(round(seg)), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def resumen(e):
    """Una línea con lo que importa de una entrada del material."""
    partes = [duracion_txt(e.get("duracion"))]
    if e.get("ancho"):
        partes.append(f"{e['ancho']}×{e['alto']}")
    if e.get("fps"):
        partes.append(f"{e['fps']:g} fps")
    if "audio" in e:
        partes.append("con voz" if e["audio"] else "mudo")
    return " · ".join(p for p in partes if p)


def _traer_y_fijar(origen, rol):
    destino = material.anadir(origen)
    return destino, material.fijar_rol(destino, rol)


class Ranura(QFrame):
    cambiado = Signal(str)              # ruta del archivo en el material ("" si se vacía la ranura)

    def __init__(self, rol, titulo, ayuda_txt, extensiones=material.VIDEO, parent=None):
        super().__init__(parent)
        self.rol, self.extensiones, self.titulo_txt = rol, extensiones, titulo
        self.ruta = ""
        self._vacia = f"Arrastra aquí {ayuda_txt}, o pulsa Elegir."
        self.setObjectName("ranura")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"Ranura {titulo}")
        self.setMaximumWidth(380)          # una tarjeta compacta: no un cuadro enorme aunque la ventana sea ancha

        self.mini = QLabel("⬇")
        self.mini.setFixedSize(60, 68)
        self.mini.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mini.setAccessibleName(f"Miniatura de {titulo}")
        self.titulo = QLabel(f"<b>{titulo}</b>")
        self.nombre = ayuda(self._vacia)
        self.info = ayuda("")
        self.b_elegir = boton("Elegir…", f"Elegir el archivo para {titulo}", self.elegir)
        self.b_quitar = boton("Quitar", "Vacía la ranura (el archivo sigue en el material)", lambda: self.poner(""))
        for b in (self.b_elegir, self.b_quitar):
            b.setProperty("pequeno", True)                  # secundarios: la ranura es solo el paso de traer el archivo

        texto = QVBoxLayout()
        texto.setSpacing(2)
        texto.addWidget(self.titulo)
        texto.addWidget(self.nombre)
        texto.addWidget(self.info)
        texto.addStretch(1)
        botones = QHBoxLayout()
        botones.addWidget(self.b_elegir)
        botones.addWidget(self.b_quitar)
        botones.addStretch(1)
        texto.addLayout(botones)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)
        lay.addWidget(self.mini)
        lay.addLayout(texto, 1)
        self.poner("")

    # ---- arrastrar y soltar / teclado
    def _marcar(self, encima):
        self.setProperty("encima", encima)
        repintar(self)

    def dragEnterEvent(self, ev):
        if rutas_soltadas(ev.mimeData(), self.extensiones):
            ev.acceptProposedAction()
            self._marcar(True)

    def dragLeaveEvent(self, ev):
        self._marcar(False)

    def dropEvent(self, ev):
        self._marcar(False)
        rutas = rutas_soltadas(ev.mimeData(), self.extensiones)
        if rutas:
            ev.acceptProposedAction()
            self.traer(rutas[0])

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.elegir()
        elif ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.ruta:
            self.poner("")
        elif ev.matches(QKeySequence.StandardKey.Paste):
            rutas = rutas_soltadas(QGuiApplication.clipboard().mimeData(), self.extensiones)
            if rutas:
                self.traer(rutas[0])
            else:
                self.nombre.setText("El portapapeles no tiene un archivo válido para esta ranura.")
        else:
            super().keyPressEvent(ev)

    def elegir(self):
        filtro = "Material (" + " ".join("*" + e for e in self.extensiones) + ")"
        ruta, _ = QFileDialog.getOpenFileName(self, f"Elegir: {self.titulo_txt}", "", filtro)
        if ruta:
            self.traer(ruta)

    # ---- material
    def traer(self, origen):
        """Lleva el archivo al material con este papel (en segundo plano: copiar un directo puede tardar)."""
        self.nombre.setText(f"Trayendo {os.path.basename(origen)}…")
        self.setCursor(Qt.CursorShape.BusyCursor)
        en_segundo_plano(lambda: _traer_y_fijar(origen, self.rol), lambda r: self.poner(r[0], r[1]), self._fallo)

    def _fallo(self, err):
        self.unsetCursor()
        self.nombre.setText(f"No se pudo traer: {err}")

    def cargar_actual(self, m=None):
        """Muestra lo último asignado a este papel (al abrir la app y cuando cambia el material)."""
        rutas = material.por_rol(self.rol, m)
        nueva = rutas[0] if rutas else ""
        if nueva != self.ruta:
            self.poner(nueva)

    def poner(self, ruta, entrada=None):
        self.unsetCursor()
        self.ruta = ruta if ruta and os.path.exists(ruta) else ""
        self.b_quitar.setEnabled(bool(self.ruta))
        self.setProperty("lleno", bool(self.ruta))
        repintar(self)
        guia = "Intro: elegir archivo. Suprimir: vaciar. Control+V: pegar una ruta."
        if not self.ruta:
            self.mini.setPixmap(QPixmap())
            self.mini.setText("⬇")
            self.nombre.setText(self._vacia)
            self.nombre.setToolTip("")
            self.info.setText("")
            self.setAccessibleDescription(f"Vacía. {self._vacia} {guia}")
            self.cambiado.emit("")
            return
        if entrada is None:
            entrada = next((e for e in material.cargar()["material"] if e["archivo"] == os.path.basename(ruta)), {})
        self.nombre.setText(os.path.basename(ruta))
        self.nombre.setToolTip(ruta)
        self.info.setText(resumen(entrada))
        self.setAccessibleDescription(f"Contiene {os.path.basename(ruta)}, {resumen(entrada)}. {guia}")
        self.mini.setText("…")
        en_segundo_plano(lambda: miniatura(ruta, entrada.get("duracion")), self._pintar_mini)
        self.cambiado.emit(self.ruta)

    def _pintar_mini(self, png):
        if png and self.ruta:
            px = QPixmap(png)
            if not px.isNull():
                self.mini.setPixmap(px.scaled(self.mini.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
                return
        self.mini.setText("♪" if self.ruta.lower().endswith(material.AUDIO) else "")
