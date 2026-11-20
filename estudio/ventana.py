"""Ventana principal de cutly estudio.

    ┌ menús: Sesión · Ver · Flujos · Ayuda ───────────────────────────────────────────────┐
    │ secciones      │ la sección elegida (su sitio para soltar,     │ Claude Code u        │
    │ (barra lateral │ su acción principal, lo que va saliendo)      │ OpenCode (panel      │
    │  con avisos ●) │                                               │ acoplable; F12 oculta)│
    └ barra de estado: sesión · material · VM ────────────────────────────────────────────┘

El material NO se coloca en carpetas a mano: se suelta en la sección de lo que se quiere hacer (cada una sabe qué hacer
con lo que se suelta en ella: `traer_soltados`; si no tiene sitio, va a Material). El vigía central (servicios.py)
reparte el material y avisa de lo nuevo que deja Claude: la sección se marca con ● y la barra de estado ofrece ir.
Todo lo que una sección le pide a Claude (`pedir`) se escribe en la sesión. Preferencias en QSettings.
"""
import os
import time

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QDockWidget, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPushButton, QStackedWidget, QWidget)

from .manija import ManijaPanel
from .memoria import VigiaMemoria
from .motores import MOTOR_DEFECTO, MOTORES

from . import apariencia
from .entorno import LOGO, REPO
from .flujos import flujos
from .paneles.directo import PanelDirecto
from .paneles.fusion import PanelFusion
from .paneles.grabacion import PanelGrabacion
from .paneles.material import TODO, PanelMaterial
from .paneles.ranura import rutas_soltadas
from .paneles.reproductor import Reproductor
from .paneles.resultados import PanelResultados
from .paneles.vm import PanelVM
from .servicios import Vigia
from .terminal.widget import TerminalClaude

GUIA = os.path.join(REPO, "estudio", "ESTUDIO.md")
NOVEDAD = {"resultado": ("Resultados", "Claude ha terminado un vídeo"),
           "subtitulos": ("Resultados", "Hay subtítulos listos para revisar"),
           "propuesta": ("Directo → clips", "Claude ha propuesto fragmentos del directo")}
ATAJOS = [("Ctrl+1 … Ctrl+7", "Ir a cada sección (en el orden de la barra lateral)"),
          ("F12", "Mostrar u ocultar el panel del agente de IA (Claude Code u OpenCode)"),
          ("Ctrl+`", "Llevar el foco al agente de IA"),
          ("Borde del panel del agente", "Arrastra para ensanchar o encoger · con el foco ahí: ← →"),
          ("Ctrl+= / Ctrl+- / Ctrl+0", "Letra más grande / más pequeña / normal (toda la app y el terminal)"),
          ("F11", "Pantalla completa"), ("Ctrl+Mayús+N", "Nueva sesión (Sesión → Motor elige cuál)"),
          ("Ctrl+Mayús+R", "Continuar la última conversación"), ("F1", "Esta ayuda"),
          ("En una ranura", "Intro: elegir archivo · Supr: vaciar · Ctrl+V: pegar una ruta"),
          ("En Grabación → Short", "Alt+↑/↓: mover la fuente · Supr: quitarla"),
          ("En Directo → clips", "Intro: ver el fragmento · Espacio: elegirlo"),
          ("Revisando subtítulos (en Resultados)", "Ctrl+S: guardar · Ctrl+Intro: ver ese momento"),
          ("En Material", "Intro: abrir · Supr: quitar · tecla Menú: papel y pedir a Claude"),
          ("En el terminal", "Ctrl+C con selección: copiar (sin selección: interrumpir) · Ctrl+V: pegar · "
                             "soltar un archivo: pega su ruta")]


class Ventana(QMainWindow):
    def __init__(self, comando, app=None, continuar=False):
        super().__init__()
        self.app = app or QApplication.instance()
        # preferencias del usuario (tema, letra, disposición, motor); CUTLY_AJUSTES las separa (p. ej. en pruebas)
        self.ajustes = QSettings("cutly", os.environ.get("CUTLY_AJUSTES", "estudio"))
        self.tema = self.ajustes.value("tema", apariencia.TEMA_DEFECTO)
        self.escala = float(self.ajustes.value("escala", 1.0))
        self.lector = self.ajustes.value("lector", False, type=bool)
        self.motor = self.ajustes.value("motor", MOTOR_DEFECTO)
        if self.motor not in MOTORES:
            self.motor = MOTOR_DEFECTO
        # `comando` explícito (p. ej. --comando de __main__.py, para pruebas) manda sobre el motor elegido
        if comando is None:
            comando = MOTORES[self.motor]["continuar" if continuar else "comando"]
        apariencia.aplicar(self.app, self.tema, self.escala)
        self.setWindowTitle("cutly estudio")
        self.setWindowIcon(QIcon(LOGO))
        self.setAcceptDrops(True)
        self.resize(1680, 1000)
        self.terminal = None

        # ---- secciones (una por cosa que se quiere hacer) y su navegación
        self.secciones = [PanelDirecto(), PanelFusion(), PanelGrabacion(), PanelResultados(), PanelMaterial(), PanelVM()]
        (self.directo, self.fusion, self.grabacion, self.resultados, self.material, self.vm) = self.secciones
        self.pila = QStackedWidget()
        self.nav = QListWidget()
        self.nav.setObjectName("navegacion")
        self.nav.setAccessibleName("Secciones")
        self.nav.setAccessibleDescription("Elige qué quieres hacer. Flechas para moverte.")
        for s in self.secciones:
            self.pila.addWidget(s)
            it = QListWidgetItem(s.TITULO)
            it.setData(Qt.ItemDataRole.UserRole, s.TITULO)
            self.nav.addItem(it)
            if hasattr(s, "pedir"):
                s.pedir.connect(self.pedir)
        self.nav.currentRowChanged.connect(self._ir)
        self.nav.setFixedWidth(round(200 * self.escala))
        centro = QWidget()                                 # barra lateral de ancho fijo + la sección, sin huecos
        fila = QHBoxLayout(centro)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)
        fila.addWidget(self.nav)
        fila.addWidget(self.pila, 1)
        self.setCentralWidget(centro)

        # ---- el agente de IA elegido (Claude Code u OpenCode), acoplable
        self.dock = QDockWidget(MOTORES[self.motor]["nombre"], self)
        self.dock.setObjectName("dock_claude")
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                              QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                              QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        # el terminal es un QWebEngineView: se come el arrastre del separador nativo en su borde (medido), así que
        # una manija propia (sin motor web) se encarga de ensanchar/encoger el panel — ver estudio/manija.py
        self._manija_claude = ManijaPanel(self, self.dock, lado="izquierda", hueco=self.nav.width() + 260)
        self.dock.topLevelChanged.connect(lambda flotando: self._manija_claude.setVisible(not flotando))
        zona = QWidget()
        zona.setObjectName("zona_claude")
        self._fila_claude = QHBoxLayout(zona)
        self._fila_claude.setContentsMargins(0, 0, 0, 0)
        self._fila_claude.setSpacing(0)
        self._fila_claude.addWidget(self._manija_claude)
        self.dock.setWidget(zona)

        # ---- barra de estado
        self.l_claude = QLabel()                           # en qué está Claude (lo cuentan sus hooks)
        self.l_claude.setAccessibleName("Estado de Claude")
        self.b_cola = QPushButton()                        # peticiones guardadas mientras Claude trabaja
        self.b_cola.setVisible(False)
        self.b_cola.setToolTip("Claude está trabajando: lo que pides espera a que termine. Pulsa para enviarlo ya.")
        self.b_cola.clicked.connect(self._vaciar_cola)
        self.statusBar().addPermanentWidget(self.b_cola)
        self.statusBar().addPermanentWidget(self.l_claude)
        self.l_sesion, self.l_material, self.l_vm = QLabel(), QLabel(), QLabel()
        for l in (self.l_sesion, self.l_material, self.l_vm):
            self.statusBar().addPermanentWidget(l)
        self.vm.resumen.connect(self.l_vm.setText)
        self._ir_a = QPushButton()                         # "Ir a <sección>" cuando Claude deja algo nuevo
        self._ir_a.setVisible(False)
        self._destino_novedad = None
        self._ir_a.clicked.connect(self._ir_a_novedad)
        self.statusBar().addWidget(self._ir_a)

        # ---- vigía central: material, carpetas y novedades
        self.vigia = Vigia(self)
        self.vigia.material.connect(self._material)
        self.vigia.carpetas.connect(lambda: [s.al_carpetas() for s in self.secciones if hasattr(s, "al_carpetas")])
        self.vigia.novedad.connect(self._novedad)
        # una herramienta va a reemplazar un vídeo: todo reproductor que lo tenga abierto lo suelta (Windows)
        self.vigia.reescribiendo.connect(lambda base: [r.soltar_si(base) for r in self.findChildren(Reproductor)])
        self.material.actualizar.connect(self.vigia.sincronizar)

        # ---- memoria del sistema: cerrar a tiempo y ordenadamente si se pone crítica (ver estudio/memoria.py)
        self._cerrando_por_memoria = False
        self.vigia_memoria = VigiaMemoria(parent=self)
        self.vigia_memoria.critica.connect(self._memoria_critica)

        self.estado_claude = ""
        self.cola = []
        self._t_quieto = QTimer(self, interval=2000, timeout=self._comprobar_quieto)
        self._t_quieto.start()

        self._menus()
        self.nueva_sesion(comando)
        self._restaurar()
        self.vigia.arrancar()

    # ---- navegación
    def _ir(self, fila):
        if fila < 0:
            return
        self.pila.setCurrentIndex(fila)
        it = self.nav.item(fila)
        it.setText(it.data(Qt.ItemDataRole.UserRole))          # visto: fuera el aviso
        it.setData(Qt.ItemDataRole.AccessibleDescriptionRole, "")

    def ir_a(self, seccion):
        self.nav.setCurrentRow(self.secciones.index(seccion))

    def seccion_actual(self):
        return self.pila.currentWidget()

    # ---- Claude Code
    def _en_panel_claude(self, widget):
        """Pone `widget` (el aviso o el terminal) junto a la manija de ensanchar/encoger, dentro del panel."""
        anterior = self._fila_claude.takeAt(1)
        if anterior is not None and anterior.widget() is not None:
            anterior.widget().setParent(None)
        self._fila_claude.insertWidget(1, widget, 1)

    def nueva_sesion(self, comando):
        if self.terminal is not None:
            self.terminal.cerrar()
            self.terminal.deleteLater()
            self.terminal = None
        binario = comando[0] if comando else ""
        info_motor = next((m for m in MOTORES.values() if m["binario"] == binario), None)
        nombre = info_motor["nombre"] if info_motor else binario
        try:
            self.terminal = TerminalClaude(comando, cwd=REPO)
        except FileNotFoundError:
            aviso = QLabel(f"No encuentro {nombre} («{binario}» en el PATH).\n\nInstálalo e inicia sesión en él, y "
                           "luego Sesión → Nueva sesión (o elige otro motor en Sesión → Motor).")
            aviso.setObjectName("aviso")
            aviso.setWordWrap(True)
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._en_panel_claude(aviso)
            self.l_sesion.setText(f"sin {nombre}   ")
            return
        self.terminal.terminado.connect(self._sesion_terminada)
        self.terminal.estado.connect(self._estado_claude)
        self.cola.clear()
        self._estado_claude("arrancando", "")
        self.terminal.ajustar(*self._estilo_terminal())
        self._en_panel_claude(self.terminal)
        self.l_sesion.setText(f"sesión: {' '.join(comando)}   ")
        self.terminal.setFocus()

    def _estilo_terminal(self):
        c = apariencia.colores(self.tema)
        return round(14 * self.escala), c["terminal"], "#ffffff" if self.tema == "alto contraste" else "#d4d4d4", \
            self.lector

    def _cambiar_motor(self, clave):
        """Sesión → Motor: alterna entre los agentes de IA del panel (Claude Code, OpenCode)."""
        if clave == self.motor:
            return
        if not self._confirmar_parar(f"cambias a {MOTORES[clave]['nombre']}"):
            self._acciones_motor[self.motor].setChecked(True)      # deshace la marca visual del clic
            return
        self.motor = clave
        self.ajustes.setValue("motor", clave)
        self._acciones_motor[clave].setChecked(True)      # por si se llamó sin pasar por el clic del menú
        nombre = MOTORES[clave]["nombre"]
        self._accion_dock.setText(f"Panel de &{nombre}")
        self._accion_nueva.setToolTip(f"Abre una sesión nueva de {nombre} en el repo")
        self._accion_nueva.setStatusTip(f"Abre una sesión nueva de {nombre} en el repo")
        continuar_txt = " ".join(MOTORES[clave]["continuar"])
        self._accion_continuar.setToolTip(continuar_txt)
        self._accion_continuar.setStatusTip(continuar_txt)
        self.nueva_sesion(MOTORES[clave]["comando"])

    def pedir(self, texto):
        """Lo que una sección le pide a Claude. Si acaba en espacio, se deja escrito para que lo completes tú.
        Si Claude está trabajando o esperando tu respuesta, espera en cola: no se mezcla con lo que hace."""
        if self.estado_claude in ("arrancando", "trabajando", "necesita") and self.terminal is not None:
            self.cola.append(texto)
            self._pintar_cola()
            self.statusBar().showMessage("Claude está ocupado: se lo pido en cuanto termine.", 6000)
            return
        self.enviar(texto, intro=not texto.endswith(" "))

    def _pintar_cola(self):
        n = len(self.cola)
        self.b_cola.setVisible(bool(n))
        self.b_cola.setText(f"{n} petición(es) en espera · enviar ya")
        self.b_cola.setAccessibleName(f"{n} peticiones esperando a que Claude termine. Enviar ya")

    def _vaciar_cola(self):
        if self.cola:
            texto = self.cola.pop(0)
            self.enviar(texto, intro=not texto.endswith(" "))
        self._pintar_cola()

    # ---- en qué está el motor (Claude Code: sus hooks, estudio/hooks/estado_claude.py; OpenCode: el plugin
    # .opencode/plugins/cutly-estado.js — mismo contrato de fichero, CUTLY_ESTADO_FICHERO)
    def _estado_claude(self, estado, mensaje):
        self.estado_claude = estado
        n = MOTORES[self.motor]["nombre"]
        textos = {"arrancando": (f"{n} arrancando…", "ayuda"),
                  "trabajando": (f"{n} trabajando…", "aviso"),
                  "necesita": (f"⚠ {n} espera tu respuesta", "error"),
                  "libre": (f"{n} listo", "ok")}
        texto, clase = textos.get(estado, ("", "ayuda"))
        self.l_claude.setText(texto + "   " if texto else "")
        self.l_claude.setObjectName(clase)
        apariencia.repintar(self.l_claude)
        self.dock.setWindowTitle(n + {"trabajando": " — trabajando…",
                                      "necesita": " — espera tu respuesta"}.get(estado, ""))
        if estado == "necesita":
            # que no pase desapercibido aunque estés en otra sección o en otra ventana
            self.dock.show()
            self.dock.raise_()
            QApplication.alert(self)
            self.statusBar().showMessage(f"Claude: {mensaje or 'necesita tu respuesta'}", 15000)
        elif estado == "libre" and self.cola:
            self._vaciar_cola()

    def _comprobar_quieto(self):
        """Lo que los hooks no cuentan: cuándo Claude ya puede recibir (arranque terminado) y que ha parado si lo
        interrumpes con Esc. Mientras trabaja, su indicador escribe sin parar; si el terminal lleva rato quieto, está libre."""
        if self.terminal is None:
            return
        quieto = time.monotonic() - self.terminal.ultima_salida
        if (self.estado_claude == "arrancando" and quieto > 2.5) or (self.estado_claude == "trabajando" and quieto > 8):
            self._estado_claude("libre", "")

    def _confirmar_parar(self, que):
        """Cerrar o cambiar de sesión detiene lo que Claude esté haciendo (y lo que haya lanzado)."""
        if self.estado_claude not in ("trabajando", "necesita"):
            return True
        r = QMessageBox.question(self, "Claude está trabajando",
                                 f"Claude está trabajando. Si {que}, se detiene lo que está haciendo. ¿Seguir?")
        return r == QMessageBox.StandardButton.Yes

    def enviar(self, texto, intro=True):
        if self.terminal is None or not self.terminal.enviar(texto, intro):
            self.statusBar().showMessage("La sesión de Claude Code no está activa: Sesión → Nueva sesión.", 8000)
            return
        if intro:                       # no esperar al hook: lo siguiente que pidas ya debe ir a la cola
            self._estado_claude("trabajando", "")
        self.dock.show()
        self.dock.raise_()
        self.terminal.setFocus()

    def _sesion_terminada(self, codigo):
        self.l_sesion.setText(f"sesión terminada ({codigo})   ")
        self.statusBar().showMessage("La sesión de Claude Code terminó: Sesión → Nueva sesión o Continuar.", 10000)

    # ---- vigía
    def _material(self, m):
        for s in self.secciones:
            if hasattr(s, "al_material"):
                s.al_material(m)
        roles = sorted({e["rol"] for e in m["material"]})
        self.l_material.setText(f"material: {len(m['material'])}" + (f" ({', '.join(roles)})" if roles else "") + "   ")

    def _novedad(self, tipo, ruta):
        titulo, mensaje = NOVEDAD.get(tipo, (None, None))
        destino = next((s for s in self.secciones if s.TITULO == titulo), None)
        if destino is None:
            return
        if hasattr(destino, "al_novedad"):
            destino.al_novedad(tipo, ruta)
        fila = self.secciones.index(destino)
        if self.nav.currentRow() != fila:
            it = self.nav.item(fila)
            it.setText(f"{titulo}  ●")
            it.setData(Qt.ItemDataRole.AccessibleDescriptionRole, "hay novedades")
        self.statusBar().showMessage(f"{mensaje}: {os.path.basename(ruta)}", 15000)
        self._ir_a.setText(f"Ir a {titulo}")
        self._ir_a.setAccessibleName(f"Ir a {titulo}: {mensaje}")
        self._destino_novedad = destino
        self._ir_a.setVisible(True)

    def _ir_a_novedad(self):
        if self._destino_novedad is not None:
            self.ir_a(self._destino_novedad)
        self._ir_a.setVisible(False)

    # ---- memoria crítica: cerrar YA, sin preguntar (preguntar en una emergencia es el riesgo, no la solución)
    def _memoria_critica(self, mb_libres):
        if self._cerrando_por_memoria:
            return
        self._cerrando_por_memoria = True
        self.statusBar().showMessage(f"Memoria del sistema crítica ({mb_libres:.0f} MB libres): cutly estudio "
                                     "se cierra solo para no dejar nada a medias. Vuelve a abrirlo cuando haya "
                                     "más memoria libre.", 0)
        QApplication.alert(self)
        QTimer.singleShot(2000, self.close)

    # ---- soltar fuera de un sitio concreto: lo decide la sección visible (o va a Material)
    def dragEnterEvent(self, ev):
        if rutas_soltadas(ev.mimeData(), TODO):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        rutas = rutas_soltadas(ev.mimeData(), TODO)
        if not rutas:
            return
        ev.acceptProposedAction()
        actual = self.seccion_actual()
        destino = actual if hasattr(actual, "traer_soltados") else self.material
        destino.traer_soltados(rutas)
        self.statusBar().showMessage(f"{len(rutas)} archivo(s) a «{destino.TITULO}»", 6000)

    # ---- menús y atajos
    def _accion(self, menu, texto, atajo=None, al_pulsar=None, ayuda=""):
        a = QAction(texto, self)
        if atajo:
            a.setShortcuts(atajo if isinstance(atajo, list) else [QKeySequence(atajo)])
        if ayuda:
            a.setStatusTip(ayuda)
            a.setToolTip(ayuda)
        if al_pulsar:
            a.triggered.connect(al_pulsar)
        menu.addAction(a)
        return a

    def _menus(self):
        barra = self.menuBar()
        m = barra.addMenu("&Sesión")
        motores = m.addMenu("&Motor")
        grupo_motor = QActionGroup(self)
        self._acciones_motor = {}
        for clave, info in MOTORES.items():
            a = self._accion(motores, info["nombre"], None, lambda _=False, c=clave: self._cambiar_motor(c),
                             f"Cargar {info['nombre']} en el panel")
            a.setCheckable(True)
            a.setChecked(clave == self.motor)
            grupo_motor.addAction(a)
            self._acciones_motor[clave] = a
        m.addSeparator()
        self._accion_nueva = self._accion(m, "&Nueva sesión", "Ctrl+Shift+N",
                                          lambda: self._confirmar_parar("empiezas otra sesión") and
                                                  self.nueva_sesion(MOTORES[self.motor]["comando"]),
                                          f"Abre una sesión nueva de {MOTORES[self.motor]['nombre']} en el repo")
        self._accion_continuar = self._accion(m, "&Continuar la última conversación", "Ctrl+Shift+R",
                                              lambda: self._confirmar_parar("cambias de sesión") and
                                                      self.nueva_sesion(MOTORES[self.motor]["continuar"]),
                                              " ".join(MOTORES[self.motor]["continuar"]))
        m.addSeparator()
        self._accion(m, "&Salir", QKeySequence.StandardKey.Quit, self.close)

        v = barra.addMenu("&Ver")
        for i, s in enumerate(self.secciones):
            self._accion(v, s.TITULO, f"Ctrl+{i + 1}", lambda _=False, k=i: self.nav.setCurrentRow(k))
        v.addSeparator()
        self._accion_dock = self.dock.toggleViewAction()
        self._accion_dock.setText(f"Panel de &{MOTORES[self.motor]['nombre']}")
        self._accion_dock.setShortcut(QKeySequence("F12"))
        v.addAction(self._accion_dock)
        self._accion_foco = self._accion(v, "&Foco en el agente de IA", "Ctrl+`",
                                         lambda: (self.dock.show(), self.terminal and self.terminal.setFocus()))
        v.addSeparator()
        temas = v.addMenu("&Tema")
        grupo = QActionGroup(self)
        for nombre in apariencia.TEMAS:
            a = self._accion(temas, nombre.capitalize(), None, lambda _=False, n=nombre: self._cambiar(tema=n))
            a.setCheckable(True)
            a.setChecked(nombre == self.tema)
            grupo.addAction(a)
        self._accion(v, "Letra más &grande", [QKeySequence("Ctrl+="), QKeySequence("Ctrl++")],
                     lambda: self._paso_letra(+1))
        self._accion(v, "Letra más &pequeña", "Ctrl+-", lambda: self._paso_letra(-1))
        self._accion(v, "Tamaño de letra &normal", "Ctrl+0", lambda: self._cambiar(escala=1.0))
        lector = self._accion(v, "Modo &lector de pantalla en el terminal", None,
                              lambda c: self._cambiar(lector=c), "Expone el texto del terminal a los lectores de "
                                                                 "pantalla (algo más lento)")
        lector.setCheckable(True)
        lector.setChecked(self.lector)
        v.addSeparator()
        self._accion(v, "Pantalla &completa", "F11",
                     lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen())

        f = barra.addMenu("&Flujos")
        for fl in flujos():
            # si la skill espera argumentos (p. ej. el tema de una demo), se deja escrito el comando SIN pulsar
            # Intro: hay hueco para completarlo antes de enviarlo (mismo criterio que pedir())
            texto = fl["comando"] + " " if fl["argumentos"] else fl["comando"]
            self._accion(f, fl["rotulo"], None, lambda _=False, t=texto: self.pedir(t),
                         f"{fl['comando']} {fl['argumentos']} — {fl['descripcion']}")

        a = barra.addMenu("A&yuda")
        self._accion(a, "&Atajos de teclado", "F1", self._atajos)
        self._accion(a, "&Guía de cutly estudio", None, lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(GUIA)))
        self._accion(a, "Acerca de", None, self._acerca_de)

    def _acerca_de(self):
        caja = QMessageBox(self)
        caja.setWindowTitle("Acerca de")
        caja.setTextFormat(Qt.TextFormat.RichText)
        caja.setIconPixmap(QPixmap(LOGO).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        caja.setText(f"<b>cutly estudio</b><br>Claude Code u OpenCode (los instalados, con su interfaz completa; "
                    f"Sesión → Motor elige cuál — ahora mismo: {MOTORES[self.motor]['nombre']}) y, alrededor, "
                    "una sección por cosa que quieres hacer con tus vídeos.<br><br>Guía: estudio/ESTUDIO.md")
        caja.exec()

    def _atajos(self):
        filas = "".join(f"<tr><td style='padding:3px 12px 3px 0'><b>{k}</b></td><td>{d}</td></tr>" for k, d in ATAJOS)
        caja = QMessageBox(self)
        caja.setWindowTitle("Atajos de teclado")
        caja.setTextFormat(Qt.TextFormat.RichText)
        caja.setText(f"<table>{filas}</table>")
        caja.exec()

    # ---- apariencia
    def _paso_letra(self, paso):
        escalas = apariencia.ESCALAS
        i = min(range(len(escalas)), key=lambda k: abs(escalas[k] - self.escala))
        self._cambiar(escala=escalas[max(0, min(len(escalas) - 1, i + paso))])

    def _cambiar(self, tema=None, escala=None, lector=None):
        self.tema = tema or self.tema
        self.escala = escala or self.escala
        self.lector = self.lector if lector is None else bool(lector)
        apariencia.aplicar(self.app, self.tema, self.escala)
        self.nav.setFixedWidth(round(200 * self.escala))
        if self.terminal is not None:
            self.terminal.ajustar(*self._estilo_terminal())
        for k, val in (("tema", self.tema), ("escala", self.escala), ("lector", self.lector)):
            self.ajustes.setValue(k, val)
        self.statusBar().showMessage(f"Tema {self.tema} · letra al {round(self.escala * 100)} %", 4000)

    # ---- recordar la disposición
    def _restaurar(self):
        geo, estado = self.ajustes.value("geometria"), self.ajustes.value("estado")
        if geo is not None:
            self.restoreGeometry(geo)
        if estado is not None:
            self.restoreState(estado)
        else:
            self.resizeDocks([self.dock], [760], Qt.Orientation.Horizontal)
        self.nav.setCurrentRow(int(self.ajustes.value("seccion", 0)))

    def closeEvent(self, ev):
        # con memoria crítica no se pregunta: parar a tiempo es justo lo que evita dejar algo a medias
        if not self._cerrando_por_memoria and not self._confirmar_parar("cierras cutly estudio"):
            ev.ignore()
            return
        self.ajustes.setValue("geometria", self.saveGeometry())
        self.ajustes.setValue("estado", self.saveState())
        self.ajustes.setValue("seccion", self.nav.currentRow())
        if self.terminal is not None:
            self.terminal.cerrar()
        super().closeEvent(ev)
