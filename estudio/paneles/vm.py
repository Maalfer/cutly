"""Pestaña VM: estado de la VM (lo que VirtualBox sabe sin credenciales), su pantalla en directo y las acciones del
ciclo de vida (doctor, arrancar con sesión, apagar, guardar estado). Las acciones son las CLIs de vm_control.py."""
import os
import tempfile

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..entorno import VM_CONTROL, ejecutar_cli, en_segundo_plano

CAPTURA = os.path.join(tempfile.gettempdir(), "cutly_estudio_vm.png")


def _leer_estado():
    from vm import info
    return info.resumen()


def _capturar():
    from vm.anfitrion import vbox
    from vm.config import VM
    return vbox("controlvm", VM, "screenshotpng", CAPTURA, check=False).returncode == 0


class PanelVM(QWidget):
    resumen = Signal(str)               # una línea para la barra de estado de la ventana

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._capturando = False
        self._encendida = False

        estado = QGroupBox("Estado")
        f = QFormLayout(estado)
        self.l = {k: QLabel("…") for k in ("estado", "sesion", "canal", "adiciones", "ip", "grabacion")}
        for k, titulo in (("estado", "VM"), ("sesion", "Sesión"), ("adiciones", "Guest Additions"), ("ip", "IP"),
                          ("grabacion", "Grabación")):
            self.l[k].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            f.addRow(titulo + ":", self.l[k])

        self.pantalla = QLabel("(VM apagada)")
        self.pantalla.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pantalla.setMinimumHeight(220)
        self.pantalla.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.pantalla.setStyleSheet("background:#111;color:#888;")
        self.en_directo = QCheckBox("Pantalla en directo")
        self.en_directo.setChecked(True)

        botones = QHBoxLayout()
        for texto, args, ayuda in (
                ("Diagnóstico", ["doctor"], "vm_control.py doctor: qué falta y cómo arreglarlo"),
                ("Arrancar", ["start", "--login"], "arranca, configura la grabación e inicia sesión si hay "
                                                   "VM_GUEST_PASSFILE"),
                ("Iniciar sesión", ["login"], "teclea tu contraseña (VM_GUEST_PASSFILE) en la pantalla de login"),
                ("Guardar estado", ["suspend"], "savestate: reanuda en segundos (no es un snapshot)"),
                ("Apagar", ["stop"], "apagado ordenado (ACPI)")):
            b = QPushButton(texto)
            b.setToolTip(ayuda)
            b.clicked.connect(lambda _=False, a=args: self.ejecutar(a))
            botones.addWidget(b)

        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(2000)
        self.log.setPlaceholderText("Salida de vm_control.py")

        lay = QVBoxLayout(self)
        lay.addWidget(estado)
        lay.addWidget(self.en_directo)
        lay.addWidget(self.pantalla, 3)
        lay.addLayout(botones)
        lay.addWidget(self.log, 2)

        self.t_estado = QTimer(self, interval=5000, timeout=self.refrescar)
        self.t_captura = QTimer(self, interval=1500, timeout=self.capturar)
        self.t_estado.start()
        self.t_captura.start()
        self.refrescar()

    # ---- estado
    def refrescar(self):
        en_segundo_plano(_leer_estado, self._pintar_estado, lambda e: self.l["estado"].setText(f"error: {e}"))

    def _pintar_estado(self, r):
        self._encendida = r["estado"] == "running"
        self.l["estado"].setText(r["estado"])
        sesion = r["usuarios"] or ("no iniciada" if r["sesion"] is False else "?")
        self.l["sesion"].setText(sesion if self._encendida else "—")
        self.l["adiciones"].setText(f"{r['version_adiciones']} (nivel {r['nivel_adiciones']})" if self._encendida else "—")
        self.l["ip"].setText(r["ip"] or "—")
        g = r["grabacion"]
        self.l["grabacion"].setText(f"{g['res']} @ {g['fps']} fps, {g['kbps']} kbps" + ("  ● GRABANDO" if g["activa"] else ""))
        self.resumen.emit(f"VM {r['estado']}" + (f" · sesión {r['usuarios']}" if r["usuarios"] else "")
                          + (" · ● GRABANDO" if g["activa"] else ""))
        if not self._encendida:
            self.pantalla.setPixmap(QPixmap())
            self.pantalla.setText(f"(VM {r['estado']})")

    # ---- pantalla en directo (solo mira: no toca la VM)
    def capturar(self):
        if not (self._encendida and self.en_directo.isChecked() and self.isVisible()) or self._capturando:
            return
        self._capturando = True
        en_segundo_plano(_capturar, self._pintar_captura, lambda e: setattr(self, "_capturando", False))

    def _pintar_captura(self, ok):
        self._capturando = False
        if ok and os.path.exists(CAPTURA):
            px = QPixmap(CAPTURA)
            if not px.isNull():
                self.pantalla.setPixmap(px.scaled(self.pantalla.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))

    # ---- acciones
    def ejecutar(self, args):
        if self._proc is not None:
            self.log.appendPlainText("(espera a que termine la orden anterior)")
            return
        self._proc = ejecutar_cli([VM_CONTROL, *args], self.log, self._fin, parent=self)

    def _fin(self, codigo):
        self.log.appendPlainText(f"[código {codigo}]\n")
        self._proc = None
        self.refrescar()
