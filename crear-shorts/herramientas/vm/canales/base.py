"""Interfaz común de los canales con el invitado. Un canal sabe ejecutar un script de bash DENTRO de la VM (con la
sesión gráfica a mano) y copiar ficheros en los dos sentidos; nada más. Todo el control humano (xdotool, OCR...) va
encima y no sabe por qué canal viaja."""

# Entorno de CADA script en el invitado, venga por el canal que venga:
#   DISPLAY=:0            la sesión X11 del escritorio (xdotool, xclip, xdpyinfo...)
#   LC_ALL/LANG C.UTF-8   IMPRESCINDIBLE: sin locale UTF-8, xdotool descarta los no ASCII (doc 08 nº 38)
ENTORNO = "export DISPLAY=:0 LC_ALL=C.UTF-8 LANG=C.UTF-8"


class CanalTimeout(Exception):
    """El canal no devolvió el control a tiempo (p. ej. un proceso en segundo plano sigue enganchado a la salida)."""


class Canal:
    nombre = "?"

    def disponible(self):
        """¿Responde el invitado por este canal ahora mismo? (rápido: se usa en bucles de espera)."""
        raise NotImplementedError

    def ejecutar(self, script, timeout):
        """Ejecuta `script` (bash) en el invitado con ENTORNO. Devuelve (código, stdout_bytes, stderr_bytes).
        Lanza CanalTimeout si no termina en `timeout` s."""
        raise NotImplementedError

    def traer(self, remoto, local):
        """Copia un fichero del invitado al anfitrión. True si fue bien."""
        raise NotImplementedError

    def enviar(self, local, remoto):
        """Copia un fichero del anfitrión al invitado. True si fue bien."""
        raise NotImplementedError

    def describir(self):
        return self.nombre


def normalizar(script):
    """Bash del invitado espera \\n: un \\r\\n de Windows rompería cada línea."""
    return script.replace("\r\n", "\n")
