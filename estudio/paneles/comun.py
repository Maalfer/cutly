"""Piezas comunes de las secciones y el contrato que cumplen todas (la ventana solo conoce esto):

    TITULO = "…"                         nombre de la sección (barra lateral, accesibilidad)
    pedir = Signal(str)                  lo que la sección le pide a Claude (la ventana lo escribe en la sesión;
                                         si el texto acaba en espacio, se deja escrito para completarlo)
    traer_soltados(rutas)                (opcional) lo que se suelta en la zona vacía de la sección
    al_material(m) / al_carpetas()       (opcional) avisos del vigía central (estudio/servicios.py)
    al_novedad(tipo, ruta)               (opcional) Claude ha dejado algo nuevo para esta sección: mostrarlo

Estilo: nada de colores sueltos; se marcan los widgets y estudio/apariencia.py los pinta.
"""
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


def cabecera(titulo, explicacion):
    """Título + explicación breve de para qué sirve la sección (lo primero que lee el usuario y el lector de pantalla)."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    t = QLabel(titulo)
    t.setObjectName("titulo")
    t.setAccessibleName(titulo)
    e = ayuda(explicacion)
    lay.addWidget(t)
    lay.addWidget(e)
    return w


def ayuda(texto):
    """Texto secundario (contraste suficiente en todos los temas), con ajuste de línea."""
    l = QLabel(texto)
    l.setObjectName("ayuda")
    l.setWordWrap(True)
    return l


def estado():
    """Línea de estado de una sección (se lee también con lector de pantalla)."""
    l = ayuda("")
    l.setAccessibleName("Estado")
    return l


def primario(texto, descripcion=""):
    """El botón de LA acción principal de una sección (resaltado; uno por sección)."""
    b = QPushButton(texto)
    b.setProperty("primario", True)
    b.setAccessibleName(texto)
    if descripcion:
        b.setToolTip(descripcion)
        b.setAccessibleDescription(descripcion)
    return b


def boton(texto, descripcion="", al_pulsar=None):
    b = QPushButton(texto)
    b.setAccessibleName(texto)
    if descripcion:
        b.setToolTip(descripcion)
        b.setAccessibleDescription(descripcion)
    if al_pulsar:
        b.clicked.connect(al_pulsar)
    return b


def nombrar(widget, nombre, descripcion=""):
    """Nombre (y descripción) para lectores de pantalla."""
    widget.setAccessibleName(nombre)
    if descripcion:
        widget.setAccessibleDescription(descripcion)
    return widget
