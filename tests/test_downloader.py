import http.server
import socketserver
import threading
import functools
import pytest
from descargador.downloader import download


def _serve(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def test_download_completo(tmp_path):
    contenido = b"x" * 5000
    (tmp_path / "f.bin").write_bytes(contenido)
    httpd, port = _serve(str(tmp_path))
    try:
        dest = tmp_path / "out.bin"
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest), chunk_size=1024
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
    finally:
        httpd.shutdown()


def test_download_reanuda(tmp_path):
    contenido = b"abcdefgh" * 1000  # 8000 bytes
    (tmp_path / "f.bin").write_bytes(contenido)
    dest = tmp_path / "out.bin"
    dest.write_bytes(contenido[:3000])  # parcial
    httpd, port = _serve(str(tmp_path))
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest), chunk_size=1024
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
    finally:
        httpd.shutdown()


class RangeHandler(http.server.BaseHTTPRequestHandler):
    contenido = b""
    recibio_range = False
    servido = 0
    _lock = threading.Lock()

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = type(self).contenido
        rango = self.headers.get("Range")
        if rango:
            type(self).recibio_range = True
            partes = rango.split("=")[1].split("-")
            inicio = int(partes[0])
            fin = int(partes[1]) if len(partes) > 1 and partes[1] else len(data) - 1
            if inicio >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            fin = min(fin, len(data) - 1)
            cuerpo = data[inicio:fin + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inicio}-{fin}/{len(data)}")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            with type(self)._lock:
                type(self).servido += len(cuerpo)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            with type(self)._lock:
                type(self).servido += len(data)


def _serve_range(contenido):
    RangeHandler.contenido = contenido
    RangeHandler.recibio_range = False
    RangeHandler.servido = 0
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def test_download_reanuda_real(tmp_path):
    contenido = b"abcdefgh" * 1000  # 8000 bytes
    httpd, port = _serve_range(contenido)
    dest = tmp_path / "out.bin"
    dest.write_bytes(contenido[:3000])  # parcial
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/x.bin", str(dest), chunk_size=1024
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
        assert RangeHandler.recibio_range  # tomo el camino 206/append
        assert total == 8000
    finally:
        httpd.shutdown()


def test_download_archivo_ya_completo(tmp_path):
    contenido = b"z" * 4000
    httpd, port = _serve_range(contenido)
    dest = tmp_path / "out.bin"
    dest.write_bytes(contenido)  # ya completo -> Range devuelve 416
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/x.bin", str(dest), chunk_size=1024
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
    finally:
        httpd.shutdown()


def test_download_pausa(tmp_path):
    contenido = b"y" * 5000
    (tmp_path / "f.bin").write_bytes(contenido)
    dest = tmp_path / "out.bin"
    httpd, port = _serve(str(tmp_path))
    llamadas = {"n": 0}

    def should_pause():
        llamadas["n"] += 1
        return llamadas["n"] > 1  # pausa despues del primer chunk

    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest),
            should_pause=should_pause, chunk_size=1024,
        )
        assert not ok and motivo == "pausado"
        assert 0 < bajado < 5000
    finally:
        httpd.shutdown()


# --- Descarga segmentada (multi-conexion) ---

def test_probe_range_soporta(tmp_path):
    from descargador.downloader import _probe_range
    httpd, port = _serve_range(b"a" * 3000)
    try:
        total, soporta = _probe_range(f"http://127.0.0.1:{port}/x.bin")
        assert soporta is True
        assert total == 3000
    finally:
        httpd.shutdown()


def test_probe_range_no_soporta(tmp_path):
    from descargador.downloader import _probe_range
    (tmp_path / "f.bin").write_bytes(b"a" * 3000)
    httpd, port = _serve(str(tmp_path))
    try:
        total, soporta = _probe_range(f"http://127.0.0.1:{port}/f.bin")
        assert soporta is False
    finally:
        httpd.shutdown()


def test_download_segmentado_completo(tmp_path):
    contenido = bytes(range(256)) * 40  # 10240 bytes, patron variado
    httpd, port = _serve_range(contenido)
    dest = tmp_path / "out.bin"
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/x.bin", str(dest),
            chunk_size=1024, conexiones=4,
        )
        assert ok and motivo == "completo"
        assert total == len(contenido)
        assert dest.read_bytes() == contenido  # offsets correctos
        assert not (tmp_path / "out.bin.dlprog").exists()  # sidecar limpiado
    finally:
        httpd.shutdown()


def test_download_segmentado_reanuda(tmp_path):
    import json
    contenido = bytes(range(256)) * 40  # 10240
    total = len(contenido)
    conexiones = 4
    base = total // conexiones  # 2560
    dest = tmp_path / "out.bin"
    with open(dest, "wb") as f:
        f.truncate(total)
    segs = []
    with open(dest, "r+b") as f:
        for i in range(conexiones):
            inicio = i * base
            fin = total if i == conexiones - 1 else (i + 1) * base
            done = (fin - inicio) // 2  # mitad ya bajada
            f.seek(inicio)
            f.write(contenido[inicio:inicio + done])
            segs.append({"inicio": inicio, "fin": fin, "done": done})
    (tmp_path / "out.bin.dlprog").write_text(json.dumps({"total": total, "segs": segs}))

    httpd, port = _serve_range(contenido)
    try:
        ok, bajado, total_r, motivo = download(
            f"http://127.0.0.1:{port}/x.bin", str(dest),
            chunk_size=1024, conexiones=4,
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
        assert RangeHandler.servido < total  # reanudo, no redescargo todo
        assert not (tmp_path / "out.bin.dlprog").exists()
    finally:
        httpd.shutdown()


def test_download_conexiones_fallback_una_sola(tmp_path):
    # SimpleHTTPRequestHandler ignora Range -> probe ve 200 -> cae a 1 conexion
    contenido = b"w" * 6000
    (tmp_path / "f.bin").write_bytes(contenido)
    httpd, port = _serve(str(tmp_path))
    dest = tmp_path / "out.bin"
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest),
            chunk_size=1024, conexiones=4,
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
        assert not (tmp_path / "out.bin.dlprog").exists()  # nunca segmento
    finally:
        httpd.shutdown()


# --- Casos de corrupcion detectados en review adversarial ---

class ShortHandler(http.server.BaseHTTPRequestHandler):
    """206 pero manda solo la mitad de cada rango (short read sin excepcion)."""
    contenido = b""

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = type(self).contenido
        partes = self.headers["Range"].split("=")[1].split("-")
        inicio = int(partes[0])
        fin = int(partes[1]) if len(partes) > 1 and partes[1] else len(data) - 1
        fin = min(fin, len(data) - 1)
        pedido = data[inicio:fin + 1]
        cuerpo = pedido if len(pedido) <= 1 else pedido[:len(pedido) // 2]
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {inicio}-{fin}/{len(data)}")
        self.send_header("Content-Length", str(len(cuerpo)))  # short pero consistente
        self.end_headers()
        self.wfile.write(cuerpo)


class MirrorHandler(http.server.BaseHTTPRequestHandler):
    """206 al probe (1 byte) pero 200 con el archivo entero a los segmentos."""
    contenido = b""

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = type(self).contenido
        partes = self.headers["Range"].split("=")[1].split("-")
        inicio = int(partes[0])
        fin = int(partes[1]) if len(partes) > 1 and partes[1] else len(data) - 1
        if fin - inicio <= 1:  # probe
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inicio}-{fin}/{len(data)}")
            self.send_header("Content-Length", str(fin - inicio + 1))
            self.end_headers()
            self.wfile.write(data[inicio:fin + 1])
            return
        self.send_response(200)  # ignora Range
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _serve_handler(handler_cls, contenido):
    handler_cls.contenido = contenido
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def test_segmentado_short_read_es_error_no_completo(tmp_path):
    # C1: un segmento corto -> NO se declara completo, se preserva el sidecar
    contenido = bytes(range(256)) * 40
    httpd, port = _serve_handler(ShortHandler, contenido)
    dest = tmp_path / "out.bin"
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/x", str(dest), chunk_size=1024, conexiones=4)
        assert not ok and motivo == "error"
        assert bajado < total
        assert (tmp_path / "out.bin.dlprog").exists()  # reanudable
    finally:
        httpd.shutdown()


def test_segmentado_mirror_200_es_error_no_corrompe(tmp_path):
    # C3: un mirror que ignora Range (200) no debe escribir bytes equivocados
    contenido = bytes(range(256)) * 40
    httpd, port = _serve_handler(MirrorHandler, contenido)
    dest = tmp_path / "out.bin"
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/x", str(dest), chunk_size=1024, conexiones=4)
        assert not ok and motivo == "error"
    finally:
        httpd.shutdown()


def test_una_conexion_no_toma_ceros_preasignados_como_completo(tmp_path):
    # C2: archivo full-size en ceros + sidecar, bajando a 1 conexion -> redescarga
    import json
    contenido = b"Q" * 6000
    (tmp_path / "f.bin").write_bytes(contenido)
    httpd, port = _serve(str(tmp_path))
    dest = tmp_path / "out.bin"
    dest.write_bytes(b"\x00" * len(contenido))  # simula crash de segmentada
    (tmp_path / "out.bin.dlprog").write_text(json.dumps(
        {"total": len(contenido), "segs": [{"inicio": 0, "fin": len(contenido), "done": 0}]}))
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest), chunk_size=1024, conexiones=1)
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido  # redescargo, no tomo los ceros
        assert not (tmp_path / "out.bin.dlprog").exists()
    finally:
        httpd.shutdown()


def test_segmentado_sidecar_sin_archivo_redescarga_de_cero(tmp_path):
    # C4: sidecar con done>0 pero el archivo no existe -> no confiar, bajar todo
    import json
    contenido = bytes(range(256)) * 40
    total = len(contenido)
    dest = tmp_path / "out.bin"
    (tmp_path / "out.bin.dlprog").write_text(json.dumps({"total": total, "segs": [
        {"inicio": 0, "fin": total // 2, "done": total // 2},
        {"inicio": total // 2, "fin": total, "done": total // 2},
    ]}))
    httpd, port = _serve_range(contenido)
    try:
        ok, bajado, total_r, motivo = download(
            f"http://127.0.0.1:{port}/x", str(dest), chunk_size=1024, conexiones=2)
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido  # sin huecos
    finally:
        httpd.shutdown()
