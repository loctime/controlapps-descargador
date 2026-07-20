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
