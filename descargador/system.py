"""Pequenas integraciones con el sistema operativo."""

import os
import subprocess
import sys


def abrir_ruta(ruta):
    """Abre un archivo o carpeta con la aplicacion predeterminada del sistema."""
    if sys.platform.startswith("win"):
        os.startfile(ruta)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", ruta])
    else:
        subprocess.Popen(["xdg-open", ruta])
