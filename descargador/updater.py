import hashlib
import json
from pathlib import Path
import sys
import tempfile
import urllib.request
import os
import subprocess

from .version import APP_VERSION, GITHUB_REPOSITORY

API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"


def _version_tuple(value):
    return tuple(int(x) for x in value.lstrip("v").split("."))


def hay_version_nueva(actual, publicada):
    return _version_tuple(publicada) > _version_tuple(actual)


def buscar_actualizacion(url=API_URL):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=12) as respuesta:
        release = json.load(respuesta)
    version = release["tag_name"].lstrip("v")
    if not hay_version_nueva(APP_VERSION, version):
        return None
    sufijo = "-Setup.exe" if sys.platform.startswith("win") else ".AppImage"
    asset = next((x for x in release.get("assets", []) if x["name"].endswith(sufijo)), None)
    if not asset:
        return None
    checksum = next((x for x in release["assets"] if x["name"] == asset["name"] + ".sha256"), None)
    return {"version": version, "asset": asset, "checksum": checksum}


def descargar_actualizacion(update):
    destino = Path(tempfile.gettempdir()) / update["asset"]["name"]
    with urllib.request.urlopen(update["asset"]["browser_download_url"], timeout=60) as r, open(destino, "wb") as f:
        while bloque := r.read(1024 * 1024):
            f.write(bloque)
    if update["checksum"]:
        with urllib.request.urlopen(update["checksum"]["browser_download_url"], timeout=15) as r:
            esperado = r.read().decode().split()[0].lower()
        if hashlib.sha256(destino.read_bytes()).hexdigest().lower() != esperado:
            destino.unlink(missing_ok=True)
            raise RuntimeError("Checksum invalido")
    return destino


def aplicar_actualizacion(archivo):
    archivo = Path(archivo).resolve()
    if sys.platform.startswith("win"):
        helper = Path(tempfile.gettempdir()) / "controlapps-update.cmd"
        helper.write_text("@echo off\r\ntimeout /t 2 /nobreak >nul\r\n"
                          f'start "" "{archivo}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART\r\n'
                          "del \"%~f0\"\r\n", encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(helper)], creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        original = Path(os.environ.get("APPIMAGE", sys.argv[0])).resolve()
        helper = Path(tempfile.gettempdir()) / "controlapps-update.sh"
        helper.write_text("#!/usr/bin/env bash\nsleep 2\n"
                          f'mv -f "{archivo}" "{original}"\nchmod +x "{original}"\n'
                          f'"{original}" &\nrm -- "$0"\n', encoding="utf-8")
        helper.chmod(0o700)
        subprocess.Popen([str(helper)])
