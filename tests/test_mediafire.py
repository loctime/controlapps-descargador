from descargador.resolvers.mediafire import extract_direct, MediaFireResolver
from descargador.resolvers.base import NeedsBrowser
import pytest


def test_extract_direct_encuentra_link():
    html = '<a id="downloadButton" href="https://download1234.mediafire.com/abc/x.rar">bajar</a>'
    assert extract_direct(html) == "https://download1234.mediafire.com/abc/x.rar"


def test_extract_direct_sin_link_devuelve_none():
    html = "<html><body>captcha aca, no hay link</body></html>"
    assert extract_direct(html) is None


def test_filename_penultimo_segmento():
    r = MediaFireResolver()
    url = "https://www.mediafire.com/file/abc123/Juego.part01.rar/file"
    assert r.filename(url) == "Juego.part01.rar"


def test_matches():
    r = MediaFireResolver()
    assert r.matches("https://www.mediafire.com/file/abc/x.rar/file")
    assert not r.matches("https://mega.nz/file/abc")
