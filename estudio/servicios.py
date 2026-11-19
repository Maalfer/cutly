"""Vigía: el ÚNICO que observa las carpetas de trabajo (el material y los resultados). Agrupa las ráfagas de cambios,
sincroniza el material una sola vez (en segundo plano) y avisa de lo nuevo que deja Claude:

    material(dict)          el manifiesto, cada vez que cambia
    carpetas()              algo cambió en editor/crudo/ o editor/videos-editados/ (listas que se recargan)
    novedad(tipo, ruta)     "resultado" (vídeo nuevo), "subtitulos" (listos para revisar), "propuesta" (fragmentos
                            de un directo): la ventana marca su sección y ofrece ir

Antes cada pestaña vigilaba y sincronizaba por su cuenta (varios ffprobe por el mismo cambio).
"""
import glob
import os

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from nucleo import material
from nucleo.rutas import SALIDA

from .entorno import en_segundo_plano


def _novedades_posibles():
    """{ruta: tipo} de todo lo que, si aparece, merece un aviso."""
    out = {}
    for f in glob.glob(os.path.join(SALIDA, "*.mp4")):
        out[f] = "resultado"
    for c in (SALIDA, material.carpeta()):
        for f in glob.glob(os.path.join(c, "*.subtitulos.json")):
            out[f] = "subtitulos"
    for f in glob.glob(os.path.join(material.carpeta(), "*.candidatos.json")):
        out[f] = "propuesta"
    return out


class Vigia(QObject):
    material = Signal(dict)
    carpetas = Signal()
    novedad = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        for c in (material.carpeta(), SALIDA):
            os.makedirs(c, exist_ok=True)
        self._w = QFileSystemWatcher([material.carpeta(), SALIDA], self)
        self._w.directoryChanged.connect(lambda _d: self._agrupar.start())
        self._agrupar = QTimer(self, singleShot=True, interval=700, timeout=self._cambio)
        self._sincronizando = False
        self._otra_vez = False
        self._conocidas = dict(_novedades_posibles())     # lo que ya había al abrir no es "nuevo"
        self._creciendo = {}                               # vídeos que se están escribiendo: ruta -> último tamaño
        self._estable = QTimer(self, interval=2500, timeout=self._comprobar_crecimiento)
        self.ultimo = {"material": []}

    def arrancar(self):
        self.sincronizar()

    def _cambio(self):
        self.carpetas.emit()
        ahora = _novedades_posibles()
        for ruta, tipo in ahora.items():
            if ruta in self._conocidas:
                continue
            if tipo == "resultado":
                # un vídeo aparece en cuanto se EMPIEZA a escribir: se anuncia cuando deja de crecer
                self._creciendo[ruta] = -1
                self._estable.start()
            else:
                self.novedad.emit(tipo, ruta)
        self._conocidas = ahora
        self.sincronizar()

    def _comprobar_crecimiento(self):
        for ruta, antes in list(self._creciendo.items()):
            if not os.path.exists(ruta):
                del self._creciendo[ruta]
                continue
            ahora = os.path.getsize(ruta)
            if ahora == antes and ahora > 0:
                del self._creciendo[ruta]
                self.novedad.emit("resultado", ruta)
            else:
                self._creciendo[ruta] = ahora
        if not self._creciendo:
            self._estable.stop()

    def sincronizar(self):
        """material.sincronizar() en segundo plano, nunca dos a la vez (si llega otro cambio, se repite al acabar)."""
        if self._sincronizando:
            self._otra_vez = True
            return
        self._sincronizando = True
        en_segundo_plano(material.sincronizar, self._sincronizado, lambda _e: self._sincronizado(None))

    def _sincronizado(self, m):
        self._sincronizando = False
        if m is not None:
            self.ultimo = m
            self.material.emit(m)
        if self._otra_vez:
            self._otra_vez = False
            self.sincronizar()
