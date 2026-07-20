import os
import json
import time
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CHUNK = 1 << 20  # 1 MB


def download(direct_url, destino, on_progress=None, should_pause=None,
             chunk_size=CHUNK, conexiones=1):
    """Descarga direct_url a destino.

    conexiones=1 -> una sola conexion (camino simple, con reanudacion por Range).
    conexiones>1 -> descarga segmentada: parte el archivo en N rangos y los baja
    en paralelo (mucho mas rapido si el servidor limita por conexion). Si el
    servidor no soporta Range, cae automaticamente a una sola conexion.

    Devuelve (ok, bytes_bajados, total, motivo). motivo in
    {"completo", "pausado", "disco_lleno", "error"}.
    """
    on_progress = on_progress or (lambda bajado, total: None)
    should_pause = should_pause or (lambda: False)

    if conexiones and conexiones > 1:
        total, soporta = _probe_range(direct_url)
        if soporta and total > 0:
            return _download_segmentado(
                direct_url, destino, total, on_progress, should_pause,
                chunk_size, conexiones)

    return _download_simple(direct_url, destino, on_progress, should_pause, chunk_size)


def _download_simple(direct_url, destino, on_progress, should_pause, chunk_size):
    ya = os.path.getsize(destino) if os.path.exists(destino) else 0
    headers = {"User-Agent": UA}
    if ya:
        headers["Range"] = f"bytes={ya}-"

    req = urllib.request.Request(direct_url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416:  # Range Not Satisfiable -> ya estaba completo
            return (True, ya, ya, "completo")
        raise

    if resp.status == 206:
        total = int(resp.headers.get("Content-Range", "/0").split("/")[-1] or 0)
        modo = "ab"
    else:
        ya = 0
        modo = "wb"
        total = int(resp.headers.get("Content-Length", 0))

    if ya and total and ya >= total:
        return (True, ya, total, "completo")

    bajado = ya
    with open(destino, modo) as f:
        while True:
            if should_pause():
                return (False, bajado, total, "pausado")
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            try:
                f.write(chunk)
            except OSError as e:
                if getattr(e, "errno", None) == 28:  # No space left on device
                    return (False, bajado, total, "disco_lleno")
                raise
            bajado += len(chunk)
            on_progress(bajado, total)

    return (True, bajado, total, "completo")


def _probe_range(direct_url):
    """Una sola request para saber (total, soporta_range).

    Pide bytes=0-0: si el server responde 206 con Content-Range, soporta Range
    y de ahi sacamos el total. Si responde 200, no soporta.
    """
    headers = {"User-Agent": UA, "Range": "bytes=0-0"}
    req = urllib.request.Request(direct_url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        if resp.status == 206:
            cr = resp.headers.get("Content-Range", "")  # "bytes 0-0/12345"
            total = int(cr.split("/")[-1]) if "/" in cr else 0
            return total, total > 0
        total = int(resp.headers.get("Content-Length", 0))
        return total, False
    except Exception:
        return 0, False


def _sidecar(destino):
    return destino + ".dlprog"


def _cargar_o_crear_segmentos(destino, total, conexiones):
    """Lista de segmentos {inicio, fin, done} (fin exclusivo).

    Si hay un sidecar valido (mismo total y misma cantidad de segmentos) lo
    reanuda; si no, parte de cero.
    """
    prog = _sidecar(destino)
    if os.path.exists(prog):
        try:
            with open(prog, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("total") == total and len(data.get("segs", [])) == conexiones:
                return data["segs"]
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    base = total // conexiones
    segs = []
    for i in range(conexiones):
        inicio = i * base
        fin = total if i == conexiones - 1 else (i + 1) * base
        segs.append({"inicio": inicio, "fin": fin, "done": 0})
    return segs


def _preasignar(destino, total):
    """Asegura que destino existe con el tamano total (para escribir por offset)."""
    if not os.path.exists(destino) or os.path.getsize(destino) != total:
        with open(destino, "wb") as f:
            f.truncate(total)


def _download_segmentado(direct_url, destino, total, on_progress, should_pause,
                         chunk_size, conexiones):
    prog = _sidecar(destino)
    segs = _cargar_o_crear_segmentos(destino, total, conexiones)
    _preasignar(destino, total)

    lock = threading.Lock()
    estado = {"pausado": False, "disco_lleno": False, "error": None}
    ultimo_save = [0.0]

    def total_done():
        return sum(s["done"] for s in segs)

    def guardar_prog():
        try:
            with open(prog, "w", encoding="utf-8") as f:
                json.dump({"total": total, "segs": segs}, f)
        except OSError:
            pass

    def bajar_segmento(s):
        inicio = s["inicio"] + s["done"]
        fin = s["fin"]  # exclusivo
        if inicio >= fin:
            return  # segmento ya completo
        if estado["pausado"] or estado["disco_lleno"] or estado["error"]:
            return
        esperado = fin - inicio
        headers = {"User-Agent": UA, "Range": f"bytes={inicio}-{fin - 1}"}
        req = urllib.request.Request(direct_url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            leido = 0
            with open(destino, "r+b") as f:
                f.seek(inicio)
                while leido < esperado:
                    if should_pause():
                        with lock:
                            estado["pausado"] = True
                        return
                    # nunca leer mas alla del propio segmento
                    chunk = resp.read(min(chunk_size, esperado - leido))
                    if not chunk:
                        break
                    try:
                        f.write(chunk)
                    except OSError as e:
                        if getattr(e, "errno", None) == 28:
                            with lock:
                                estado["disco_lleno"] = True
                            return
                        raise
                    leido += len(chunk)
                    with lock:
                        s["done"] += len(chunk)
                        on_progress(total_done(), total)
                        ahora = time.time()
                        if ahora - ultimo_save[0] >= 2:
                            ultimo_save[0] = ahora
                            guardar_prog()
        except Exception as e:
            with lock:
                if estado["error"] is None:
                    estado["error"] = e

    with ThreadPoolExecutor(max_workers=conexiones) as ex:
        list(ex.map(bajar_segmento, segs))

    bajado = total_done()

    if estado["disco_lleno"]:
        guardar_prog()
        return (False, bajado, total, "disco_lleno")
    if estado["pausado"]:
        guardar_prog()
        return (False, bajado, total, "pausado")
    if estado["error"] is not None:
        guardar_prog()
        return (False, bajado, total, "error")

    # completo: limpiamos el sidecar
    try:
        if os.path.exists(prog):
            os.remove(prog)
    except OSError:
        pass
    return (True, total, total, "completo")
