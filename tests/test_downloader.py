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

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = type(self).contenido
        rango = self.headers.get("Range")
        if rango:
            type(self).recibio_range = True
            inicio = int(rango.split("=")[1].split("-")[0])
            if inicio >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.end_headers()
                return
            cuerpo = data[inicio:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inicio}-{len(data)-1}/{len(data)}")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


def _serve_range(contenido):
    RangeHandler.contenido = contenido
    RangeHandler.recibio_range = False
    httpd = socketserver.TCPServer(("127.0.0.1", 0), RangeHandler)
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
