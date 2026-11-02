"""Host de Native Messaging: puente entre la extension del navegador y la app.

Solo usa la libreria estandar a proposito: se empaqueta como un .exe aparte,
chico y rapido de arrancar, que el navegador lanza cada vez que la extension
le habla. El host no descarga nada: deja el pedido en una carpeta "inbox" que
la ventana principal revisa, y abre la app si todavia no esta corriendo.

Protocolo (JSON, con el prefijo de 4 bytes little-endian de Chrome):
  {"type": "ping"}                                  -> estado y version
  {"type": "add", "url": ..., "inicio": s, "fin": s, "modo": "video|original|mp3"}
"""

import json
import os
import struct
import subprocess
import sys
import time
import uuid
from urllib.parse import urlparse

from .version import APP_VERSION

HOST_NAME = "com.controlapps.descargador"
PROTOCOL = 1
CARPETA_APP = os.path.join(os.path.expanduser("~"), ".descargador")
INBOX = os.path.join(CARPETA_APP, "inbox")
LATIDO = os.path.join(CARPETA_APP, "app.alive")
LATIDO_MAX_EDAD = 6  # la app lo renueva cada ~2 s
MAX_URL = 2048
MAX_MENSAJE = 64 * 1024
MODOS = ("video", "original", "mp3")

# Extensiones autorizadas a hablar con el host. La primera es la de desarrollo
# (fijada por la "key" del manifest); al publicar en la tienda hay que sumar
# el ID que asigne.
EXTENSION_IDS = ["fgmfjdihkfngeklmoeaeknpkclllieec"]


# --- Protocolo -----------------------------------------------------------

def leer_mensaje(stream):
    """Devuelve el dict recibido, o None si el navegador cerro el pipe."""
    cabecera = stream.read(4)
    if len(cabecera) < 4:
        return None
    (largo,) = struct.unpack("<I", cabecera)
    if largo > MAX_MENSAJE:
        raise ValueError("mensaje demasiado grande")
    return json.loads(stream.read(largo).decode("utf-8"))


def escribir_mensaje(stream, mensaje):
    datos = json.dumps(mensaje, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(datos)))
    stream.write(datos)
    stream.flush()


# --- Estado de la app ------------------------------------------------------

def app_corriendo(latido=LATIDO, ahora=None):
    try:
        edad = (ahora if ahora is not None else time.time()) - os.path.getmtime(latido)
    except OSError:
        return False
    return edad < LATIDO_MAX_EDAD


def _comando_app():
    """Como lanzar la ventana principal, instalada o en desarrollo."""
    if getattr(sys, "frozen", False):
        # El host vive en <instalacion>\host\; la app, un nivel arriba.
        carpeta = os.path.dirname(os.path.dirname(sys.executable))
        return [os.path.join(carpeta, "ControlApps Descargador.exe")]
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, os.path.join(raiz, "run.py")]


def abrir_app():
    comando = _comando_app()
    flags = 0
    if sys.platform.startswith("win"):
        # Que la app sobreviva al host (y a Chrome) y no herede el pipe.
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            comando, creationflags=flags | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        subprocess.Popen(
            comando, creationflags=flags,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


# --- Pedidos ---------------------------------------------------------------

def validar_pedido(msg):
    """Devuelve (pedido_limpio, error)."""
    url = msg.get("url")
    if not isinstance(url, str) or len(url) > MAX_URL:
        return None, "url_invalida"
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None, "url_invalida"
    pedido = {"url": url.strip()}
    inicio, fin = msg.get("inicio"), msg.get("fin")
    if inicio is not None or fin is not None:
        ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (inicio, fin))
        if not ok or inicio < 0 or fin <= inicio:
            return None, "rango_invalido"
        pedido["inicio"], pedido["fin"] = int(inicio), int(fin)
    modo = msg.get("modo")
    if modo is not None:
        if modo not in MODOS:
            return None, "modo_invalido"
        pedido["modo"] = modo
    return pedido, None


def guardar_en_inbox(pedido, inbox=INBOX):
    os.makedirs(inbox, exist_ok=True)
    nombre = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
    temporal = os.path.join(inbox, nombre + ".tmp")
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(pedido, f, ensure_ascii=False)
    # Renombrar al final: la app nunca ve un archivo a medio escribir.
    os.replace(temporal, os.path.join(inbox, nombre + ".json"))


def procesar(msg, inbox=INBOX, latido=LATIDO, abrir=abrir_app):
    tipo = msg.get("type") if isinstance(msg, dict) else None
    base = {"version": APP_VERSION, "protocol": PROTOCOL}
    if tipo == "ping":
        return {"ok": True, "app_running": app_corriendo(latido), **base}
    if tipo == "add":
        pedido, error = validar_pedido(msg)
        if error:
            return {"ok": False, "error": error, **base}
        guardar_en_inbox(pedido, inbox)
        corriendo = app_corriendo(latido)
        if not corriendo:
            abrir()
        return {"ok": True, "queued": True, "app_started": not corriendo, **base}
    return {"ok": False, "error": "tipo_desconocido", **base}


def servir(entrada, salida, **kwargs):
    """Atiende mensajes hasta que el navegador cierra el pipe."""
    while True:
        try:
            msg = leer_mensaje(entrada)
        except (ValueError, UnicodeDecodeError):
            escribir_mensaje(salida, {"ok": False, "error": "mensaje_invalido"})
            return 1
        if msg is None:
            return 0
        escribir_mensaje(salida, procesar(msg, **kwargs))


# --- Registro en los navegadores ------------------------------------------

_CLAVES_NAVEGADOR = (
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
)


def construir_manifest(ruta_host, extension_ids=None):
    ids = extension_ids or EXTENSION_IDS
    return {
        "name": HOST_NAME,
        "description": "ControlApps Descargador",
        "path": ruta_host,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{i}/" for i in ids],
    }


def registrar(ruta_host, carpeta_manifest=None):
    """Escribe el manifest y lo registra (HKCU) en Chrome, Edge y Chromium."""
    import winreg
    carpeta_manifest = carpeta_manifest or os.path.dirname(ruta_host)
    ruta_manifest = os.path.join(carpeta_manifest, HOST_NAME + ".json")
    with open(ruta_manifest, "w", encoding="utf-8") as f:
        json.dump(construir_manifest(ruta_host), f, indent=2)
    for clave in _CLAVES_NAVEGADOR:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, clave + "\\" + HOST_NAME) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, ruta_manifest)
    return ruta_manifest


def desregistrar():
    import winreg
    for clave in _CLAVES_NAVEGADOR:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, clave + "\\" + HOST_NAME)
        except OSError:
            pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--register":
        if getattr(sys, "frozen", False):
            registrar(os.path.abspath(sys.executable))
        else:
            # Desarrollo: el navegador necesita un ejecutable, no un .py.
            raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            os.makedirs(CARPETA_APP, exist_ok=True)
            bat = os.path.join(CARPETA_APP, "host-dev.bat")
            with open(bat, "w", encoding="utf-8") as f:
                script = os.path.join(raiz, "host_main.py")
                f.write("@echo off\r\n" + f'"{sys.executable}" "{script}"\r\n')
            registrar(bat, CARPETA_APP)
        return 0
    if argv and argv[0] == "--unregister":
        desregistrar()
        return 0
    entrada, salida = sys.stdin.buffer, sys.stdout.buffer
    if sys.platform.startswith("win"):
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    return servir(entrada, salida)


# --- Lado de la app: leer el inbox y marcar que esta viva ------------------

def tomar_pedidos(inbox=INBOX):
    """Devuelve los pedidos validos del inbox y los borra (invalidos incluidos)."""
    try:
        nombres = sorted(n for n in os.listdir(inbox) if n.endswith(".json"))
    except OSError:
        return []
    pedidos = []
    for nombre in nombres:
        ruta = os.path.join(inbox, nombre)
        try:
            if os.path.getsize(ruta) <= MAX_MENSAJE:
                with open(ruta, encoding="utf-8") as f:
                    pedido, error = validar_pedido(json.load(f))
                if pedido and not error:
                    pedidos.append(pedido)
        except (OSError, ValueError):
            pass
        try:
            os.remove(ruta)
        except OSError:
            pass
    return pedidos


def marcar_viva(latido=LATIDO):
    try:
        os.makedirs(os.path.dirname(latido), exist_ok=True)
        with open(latido, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
