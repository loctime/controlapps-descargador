import pytest

from descargador.resolvers.base import NeedsBrowser
from descargador.resolvers.rootz import extract_title, RootzResolver

HTML_CON_TITLE = """
<html><head><title>Sle2epi6ngDo9g7sDe1fini4tiveE-Upd1-elamigos.part02.rar</title></head>
<body>contenido</body></html>
"""


def test_extract_title_encuentra_titulo():
    assert extract_title(HTML_CON_TITLE) == "Sle2epi6ngDo9g7sDe1fini4tiveE-Upd1-elamigos.part02.rar"


def test_extract_title_sin_titulo_devuelve_none():
    assert extract_title("<html><body>sin titulo aca</body></html>") is None


def test_matches():
    r = RootzResolver()
    assert r.matches("https://www.rootz.so/d/sG2Cm")
    assert not r.matches("https://mediafire.com/file/abc/x.rar/file")


def test_filename_usa_el_title(monkeypatch):
    import descargador.resolvers.rootz as rootz_mod

    class FakeResp:
        def read(self):
            return HTML_CON_TITLE.encode("utf-8")

    monkeypatch.setattr(rootz_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = RootzResolver()
    assert r.filename("https://www.rootz.so/d/sG2Cm") == "Sle2epi6ngDo9g7sDe1fini4tiveE-Upd1-elamigos.part02.rar"


def test_filename_fallback_sin_title(monkeypatch):
    import descargador.resolvers.rootz as rootz_mod

    class FakeResp:
        def read(self):
            return b"<html><body>nada</body></html>"

    monkeypatch.setattr(rootz_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = RootzResolver()
    assert r.filename("https://www.rootz.so/d/sG2Cm") == "sG2Cm"


def test_resolve_siempre_lanza_needsbrowser():
    r = RootzResolver()
    with pytest.raises(NeedsBrowser) as exc_info:
        r.resolve("https://www.rootz.so/d/sG2Cm")
    assert exc_info.value.page_url == "https://www.rootz.so/d/sG2Cm"
