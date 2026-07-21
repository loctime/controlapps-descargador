import pytest

from descargador.resolvers.base import NeedsBrowser
from descargador.resolvers.megaup import extract_direct, MegaUpResolver

HTML_CON_LINK = """
<script>
var seconds = 2;
function display() {
    if (seconds == 0) {
        $('.download-timer').html("<a class='btn btn--primary' href='https://download.megaup.net/?url=TOKEN_DE_PRUEBA_123'><span class='btn__text'>DOWNLOAD / VIEW NOW</span></a>");
    }
}
</script>
"""


def test_extract_direct_encuentra_link():
    assert extract_direct(HTML_CON_LINK) == "https://download.megaup.net/?url=TOKEN_DE_PRUEBA_123"


def test_extract_direct_sin_link_devuelve_none():
    assert extract_direct("<html><body>nada aca</body></html>") is None


def test_matches():
    r = MegaUpResolver()
    assert r.matches("https://megaup.net/abc123/Juego.part01.rar")
    assert not r.matches("https://mediafire.com/file/abc/x.rar/file")


def test_filename_ultimo_segmento():
    r = MegaUpResolver()
    url = "https://megaup.net/4c313c78a3315d00f90fe290806cf634/Juego.part07.rar"
    assert r.filename(url) == "Juego.part07.rar"


def test_resolve_encuentra_link_lanza_needsbrowser(monkeypatch):
    import descargador.resolvers.megaup as megaup_mod

    class FakeResp:
        def read(self):
            return HTML_CON_LINK.encode("utf-8")

    monkeypatch.setattr(megaup_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = MegaUpResolver()
    with pytest.raises(NeedsBrowser) as exc_info:
        r.resolve("https://megaup.net/abc123/Juego.part01.rar")
    assert exc_info.value.page_url == "https://download.megaup.net/?url=TOKEN_DE_PRUEBA_123"


def test_resolve_sin_link_lanza_excepcion_comun(monkeypatch):
    import descargador.resolvers.megaup as megaup_mod

    class FakeResp:
        def read(self):
            return b"<html>nada aca</html>"

    monkeypatch.setattr(megaup_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = MegaUpResolver()
    with pytest.raises(Exception) as exc_info:
        r.resolve("https://megaup.net/abc123/Juego.part01.rar")
    assert not isinstance(exc_info.value, NeedsBrowser)
