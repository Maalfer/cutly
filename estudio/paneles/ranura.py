"""Ranura de material: el sitio de cada menú donde se SUELTA un vídeo ("Cara", "Pantalla", "Short a subtitular"...).
Soltarlo lo trae al material (editor/crudo/, sin copiar si está en el mismo disco) y le fija ese papel en
material.json; así Claude sabe qué es cada archivo. También acepta lo que se arrastra desde la pestaña Material."""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from nucleo import material

from ..entorno import en_segundo_plano
from ..miniaturas import miniatura


def rutas_soltadas(mime, extensiones=None):
    """Ficheros locales de un arrastre (filtrados por extensión si se da)."""
    out = []
    for url in mime.urls() if mime.hasUrls() else []:
        p = url.toLocalFile()
        if p and os.path.isfile(p) and (not extensiones or p.lower().endswith(extensiones)):
            out.append(p)
    return out


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
    e = material.fijar_rol(destino, rol)
    return destino, e


class Ranura(QFrame):
    cambiado = Signal(str)              # ruta del archivo en el material ("" si se vacía la ranura)

    def __init__(self, rol, titulo, ayuda, extensiones=material.VIDEO, parent=None):
        super().__init__(parent)
        self.rol, self.extensiones = rol, extensiones
        self.ruta = ""
        self.setAcceptDrops(True)
        self.setObjectName("ranura")
        self._estilo(False)

        self.mini = QLabel()
        self.mini.setFixedSize(108, 120)
        self.mini.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mini.setStyleSheet("background:#111;color:#777;border-radius:6px;")
        self.titulo = QLabel(f"<b>{titulo}</b>")
        self._vacia = f"<span style='color:#999'>Arrastra aquí {ayuda}</span>"
        self.nombre = QLabel(self._vacia)
        self.nombre.setWordWrap(True)
        self.info = QLabel()
        self.info.setStyleSheet("color:#aaa")
        b_elegir = QPushButton("Elegir…")
        b_elegir.clicked.connect(self._elegir)
        self.b_quitar = QPushButton("Quitar")
        self.b_quitar.setToolTip("Vacía la ranura (el archivo sigue en el material)")
        self.b_quitar.clicked.connect(lambda: self.poner(""))

        texto = QVBoxLayout()
        texto.addWidget(self.titulo)
        texto.addWidget(self.nombre)
        texto.addWidget(self.info)
        texto.addStretch(1)
        botones = QHBoxLayout()
        botones.addWidget(b_elegir)
        botones.addWidget(self.b_quitar)
        botones.addStretch(1)
        texto.addLayout(botones)
        lay = QHBoxLayout(self)
        lay.addWidget(self.mini)
        lay.addLayout(texto, 1)
        self.poner("")

    def _estilo(self, encima):
        borde = "#4ea1ff" if encima else "#555"
        fondo = "#22303f" if encima else "#262626"
        self.setStyleSheet(f"QFrame#ranura {{ border: 2px dashed {borde}; border-radius: 10px; background: {fondo}; }}")

    # ---- arrastrar y soltar
    def dragEnterEvent(self, ev):
        if rutas_soltadas(ev.mimeData(), self.extensiones):
            ev.acceptProposedAction()
            self._estilo(True)

    def dragLeaveEvent(self, ev):
        self._estilo(False)

    def dropEvent(self, ev):
        self._estilo(False)
        rutas = rutas_soltadas(ev.mimeData(), self.extensiones)
        if rutas:
            ev.acceptProposedAction()
            self.traer(rutas[0])

    def _elegir(self):
        filtro = "Material (" + " ".join("*" + e for e in self.extensiones) + ")"
        ruta, _ = QFileDialog.getOpenFileName(self, f"Elegir {self.rol}", "", filtro)
        if ruta:
            self.traer(ruta)

    # ---- material
    def traer(self, origen):
        """Lleva el archivo al material con este papel (en segundo plano: copiar un directo puede tardar)."""
        self.nombre.setText(f"Trayendo {os.path.basename(origen)}…")
        en_segundo_plano(lambda: _traer_y_fijar(origen, self.rol), lambda r: self.poner(r[0], r[1]),
                         lambda err: self.nombre.setText(f"<span style='color:#f77'>No se pudo: {err}</span>"))

    def cargar_actual(self, m=None):
        """Muestra lo último asignado a este papel (al abrir la app y cuando cambia el material)."""
        rutas = material.por_rol(self.rol, m)
        nueva = rutas[0] if rutas else ""
        if nueva != self.ruta:
            self.poner(nueva)

    def poner(self, ruta, entrada=None):
        self.ruta = ruta if ruta and os.path.exists(ruta) else ""
        self.b_quitar.setEnabled(bool(self.ruta))
        if not self.ruta:
            self.mini.setPixmap(QPixmap())
            self.mini.setText("⬇")
            self.nombre.setText(self._vacia)
            self.nombre.setToolTip("")
            self.info.setText("")
            self.cambiado.emit("")
            return
        if entrada is None:
            entrada = next((e for e in material.cargar()["material"] if e["archivo"] == os.path.basename(ruta)), {})
        self.nombre.setText(os.path.basename(ruta))
        self.nombre.setToolTip(ruta)
        self.info.setText(resumen(entrada))
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
