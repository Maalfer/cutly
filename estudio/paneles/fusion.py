"""Pestaña Fusión: arrastra el vídeo de tu cara y el Short de pantalla a sus ranuras y pide a Claude que los junte
(/fusionar-cara-pantalla con ESOS archivos). Metodología: editor/shorts/METODOLOGIA-FUSION-CARA.md."""
import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from nucleo import material

from ..entorno import en_segundo_plano, para_claude
from .ranura import Ranura


def titulo_valido(t):
    """Capitalized-Kebab-Case sin tildes ni símbolos (sirve de título de YouTube y de nombre de archivo)."""
    return bool(re.fullmatch(r"[A-Z0-9][A-Za-z0-9]*(-[A-Za-z0-9]+)*", t))


def papel_para_fusion(ruta):
    """Cara o pantalla, según el vídeo (sin pista que suene = el Short mudo de pantalla)."""
    return "pantalla" if material.inferir_rol(ruta, material.describir(ruta)) == "pantalla" else "cara"


class PanelFusion(QWidget):
    pedir = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        explica = QLabel("Junta el <b>Short de pantalla</b> (mudo, con la banda negra arriba) con el <b>vídeo de tu "
                         "cara y tu voz</b>: Claude quita tomas repetidas y pausas, mete la cara en la banda y "
                         "sincroniza la pantalla con lo que dices. Después, los subtítulos en la pestaña Subtítulos.")
        explica.setWordWrap(True)
        self.cara = Ranura("cara", "Cara", "el vídeo de tu cara y tu voz")
        self.pantalla = Ranura("pantalla", "Pantalla", "el Short mudo de pantalla")
        self.titulo = QLineEdit()
        self.titulo.setPlaceholderText("Titulo-Con-Gancho (opcional: si lo dejas vacío lo propone Claude)")
        self.titulo.textChanged.connect(self._actualizar)
        self.b = QPushButton("Fusionar con Claude")
        self.b.setMinimumHeight(36)
        self.b.clicked.connect(self._fusionar)
        self.aviso = QLabel()
        self.aviso.setStyleSheet("color:#aaa")
        for r in (self.cara, self.pantalla):
            r.cambiado.connect(lambda _r: self._actualizar())

        ranuras = QHBoxLayout()
        ranuras.addWidget(self.cara)
        ranuras.addWidget(self.pantalla)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Título:"))
        fila.addWidget(self.titulo, 1)
        fila.addWidget(self.b)
        lay = QVBoxLayout(self)
        lay.addWidget(explica)
        lay.addLayout(ranuras)
        lay.addLayout(fila)
        lay.addWidget(self.aviso)
        lay.addStretch(1)
        self._actualizar()

    def traer_soltados(self, rutas):
        """Soltar en cualquier parte de la pestaña: cada vídeo a su ranura según lo que es (mudo = pantalla,
        con voz = cara)."""
        videos = [r for r in rutas if r.lower().endswith(material.VIDEO)][:2]
        if videos:
            en_segundo_plano(lambda: [(r, papel_para_fusion(r)) for r in videos], self._repartir)

    def _repartir(self, pares):
        for ruta, papel in pares:
            (self.pantalla if papel == "pantalla" else self.cara).traer(ruta)

    def cargar(self, m):
        self.cara.cargar_actual(m)
        self.pantalla.cargar_actual(m)

    def _actualizar(self):
        t = self.titulo.text().strip()
        falta = [n for n, r in (("la cara", self.cara), ("la pantalla", self.pantalla)) if not r.ruta]
        if falta:
            self.aviso.setText("Falta " + " y ".join(falta) + ".")
        elif t and not titulo_valido(t):
            self.aviso.setText("El título va en Capitalized-Kebab-Case, sin tildes ni símbolos: Entrar-Por-SSH-Sin-Clave")
        else:
            self.aviso.setText("Listo: Claude lo hará en la sesión de la izquierda (te pedirá permisos si hace falta).")
        self.b.setEnabled(not falta and (not t or titulo_valido(t)))

    def _fusionar(self):
        partes = ["/fusionar-cara-pantalla", para_claude(self.cara.ruta), para_claude(self.pantalla.ruta)]
        if self.titulo.text().strip():
            partes.append(self.titulo.text().strip())
        self.pedir.emit(" ".join(partes))
