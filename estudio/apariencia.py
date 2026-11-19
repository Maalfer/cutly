"""Aspecto de cutly estudio: temas (oscuro, claro, alto contraste), una hoja de estilo única construida con sus
colores (nada de colores sueltos por los paneles) y la escala de letra (accesibilidad: Ctrl+= / Ctrl+- / Ctrl+0).

Los paneles marcan sus widgets con propiedades/objectName y el estilo los pinta:
    boton.setProperty("primario", True)      -> la acción principal de una sección (color de acento)
    QLabel#ayuda                             -> texto secundario (con contraste suficiente)
    QLabel#titulo                            -> título de sección
    QFrame#ranura[encima="true"]             -> sitio para soltar, resaltado mientras se arrastra encima
"""
from PySide6.QtGui import QColor, QFont, QPalette

TEMAS = {
    # contraste de texto/fondo >= 4.5:1 (WCAG AA) en todos; alto contraste >= 7:1
    "oscuro": {"fondo": "#1f1f1f", "panel": "#262628", "base": "#1a1a1a", "borde": "#4a4a4f", "texto": "#ececec",
               "ayuda": "#b4b4b4", "acento": "#2563eb", "acento_texto": "#ffffff", "foco": "#79b0ff",
               "ok": "#7bd88f", "aviso": "#ffcf5c", "error": "#ff8a80", "suelta": "#1d2c40", "terminal": "#1e1e1e"},
    "claro": {"fondo": "#f3f3f3", "panel": "#ffffff", "base": "#ffffff", "borde": "#b9b9c0", "texto": "#1b1b1b",
              "ayuda": "#4d4d55", "acento": "#1d5fd1", "acento_texto": "#ffffff", "foco": "#1d5fd1",
              "ok": "#1e7a35", "aviso": "#8a5a00", "error": "#b3261e", "suelta": "#e3eefc", "terminal": "#1e1e1e"},
    "alto contraste": {"fondo": "#000000", "panel": "#000000", "base": "#000000", "borde": "#ffffff",
                       "texto": "#ffffff", "ayuda": "#ffffff", "acento": "#ffff00", "acento_texto": "#000000",
                       "foco": "#00ffff", "ok": "#00ff00", "aviso": "#ffff00", "error": "#ff6060", "suelta": "#002b4d",
                       "terminal": "#000000"},
}
TEMA_DEFECTO = "oscuro"
LETRA_BASE = 10          # pt; la escala la multiplica
ESCALAS = (0.85, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0)


def colores(tema):
    return TEMAS.get(tema, TEMAS[TEMA_DEFECTO])


def paleta(tema):
    c = colores(tema)
    p = QPalette()
    for rol, k in ((QPalette.ColorRole.Window, "fondo"), (QPalette.ColorRole.WindowText, "texto"),
                   (QPalette.ColorRole.Base, "base"), (QPalette.ColorRole.AlternateBase, "panel"),
                   (QPalette.ColorRole.Text, "texto"), (QPalette.ColorRole.Button, "panel"),
                   (QPalette.ColorRole.ButtonText, "texto"), (QPalette.ColorRole.Highlight, "acento"),
                   (QPalette.ColorRole.HighlightedText, "acento_texto"), (QPalette.ColorRole.ToolTipBase, "panel"),
                   (QPalette.ColorRole.ToolTipText, "texto"), (QPalette.ColorRole.PlaceholderText, "ayuda"),
                   (QPalette.ColorRole.Link, "foco")):
        p.setColor(rol, QColor(c[k]))
    for rol in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, rol, QColor(c["ayuda"]))
    return p


def hoja(tema, escala=1.0):
    c = colores(tema)
    r = round(6 * escala)
    return f"""
    QWidget {{ color: {c['texto']}; }}
    QMainWindow, QDialog {{ background: {c['fondo']}; }}
    QToolTip {{ background: {c['panel']}; color: {c['texto']}; border: 1px solid {c['borde']}; padding: 4px; }}
    QLabel#titulo {{ font-size: {round(16 * escala)}pt; font-weight: 600; }}
    QLabel#ayuda {{ color: {c['ayuda']}; }}
    QLabel#ok {{ color: {c['ok']}; }} QLabel#aviso {{ color: {c['aviso']}; }} QLabel#error {{ color: {c['error']}; }}
    QPushButton {{ background: {c['panel']}; border: 1px solid {c['borde']}; border-radius: {r}px;
                   padding: {round(5 * escala)}px {round(12 * escala)}px; }}
    QPushButton:hover {{ border-color: {c['foco']}; }}
    QPushButton:disabled {{ color: {c['ayuda']}; border-style: dashed; }}
    QPushButton[primario="true"] {{ background: {c['acento']}; color: {c['acento_texto']}; border-color: {c['acento']};
                                    font-weight: 600; padding: {round(8 * escala)}px {round(16 * escala)}px; }}
    QPushButton[primario="true"]:disabled {{ background: {c['panel']}; color: {c['ayuda']}; border-color: {c['borde']}; }}
    QPushButton:focus, QLineEdit:focus, QComboBox:focus, QListWidget:focus, QTableWidget:focus,
    QCheckBox:focus, QSlider:focus, QFrame#ranura:focus, QPlainTextEdit:focus {{
        outline: none; border: 2px solid {c['foco']}; }}
    QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget {{
        background: {c['base']}; border: 1px solid {c['borde']}; border-radius: {r}px; padding: 3px; }}
    QHeaderView::section {{ background: {c['panel']}; border: none; border-bottom: 1px solid {c['borde']}; padding: 4px; }}
    QTableWidget::item:selected, QListWidget::item:selected {{ background: {c['acento']}; color: {c['acento_texto']}; }}
    QFrame#ranura {{ border: 2px dashed {c['borde']}; border-radius: {round(10 * escala)}px; background: {c['panel']}; }}
    QFrame#ranura[encima="true"] {{ border-color: {c['foco']}; background: {c['suelta']}; }}
    QFrame#ranura[lleno="true"] {{ border-style: solid; }}
    QListWidget#navegacion {{ background: {c['panel']}; border: none; border-right: 1px solid {c['borde']};
                              padding-top: 6px; font-size: {round(11 * escala)}pt; }}
    QListWidget#navegacion::item {{ padding: {round(10 * escala)}px {round(12 * escala)}px; border-radius: {r}px;
                                     margin: 2px 6px; }}
    QListWidget#navegacion::item:selected {{ background: {c['acento']}; color: {c['acento_texto']}; }}
    QSlider::groove:horizontal {{ height: {round(6 * escala)}px; background: {c['base']}; border: 1px solid {c['borde']};
                                  border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {c['acento']}; border-radius: 3px; }}
    QSlider::handle:horizontal {{ background: {c['acento']}; border: 2px solid {c['texto']};
                                  width: {round(14 * escala)}px; margin: -{round(6 * escala)}px 0; border-radius: {round(8 * escala)}px; }}
    QCheckBox::indicator {{ width: {round(16 * escala)}px; height: {round(16 * escala)}px; }}
    QDockWidget::title {{ background: {c['panel']}; padding: 6px; border-bottom: 1px solid {c['borde']}; }}
    QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['borde']}; }}
    QMenuBar, QMenu {{ background: {c['panel']}; }}
    QMenu::item:selected, QMenuBar::item:selected {{ background: {c['acento']}; color: {c['acento_texto']}; }}
    """


def aplicar(app, tema, escala):
    app.setStyle("Fusion")            # el mismo aspecto en Windows, macOS y Linux
    app.setPalette(paleta(tema))
    f = QFont(app.font())
    f.setPointSizeF(LETRA_BASE * escala)
    app.setFont(f)
    app.setStyleSheet(hoja(tema, escala))


def repintar(widget):
    """Tras cambiar una propiedad que usa la hoja de estilo (p. ej. encima, lleno), que se vuelva a pintar."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
