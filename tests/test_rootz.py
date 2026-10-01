import pytest

from descargador.resolvers.base import NeedsBrowser
from descargador.resolvers.rootz import RootzResolver, extract_title, proxy_url, short_id


def test_matches_only_rootz_hosts():
    resolver = RootzResolver()
    assert resolver.matches("https://www.rootz.so/d/1Ia2fg")
    assert resolver.matches("https://rootz.so/d/oEBLE")
    assert not resolver.matches("https://rootz.so.ejemplo.com/d/1Ia2fg")


def test_title_decodes_real_filename():
    assert extract_title("<title>Juego &amp; DLC.part01.rar</title>") == "Juego & DLC.part01.rar"
    assert extract_title("<html>sin titulo</html>") is None


def test_proxy_url_uses_short_id():
    assert short_id("https://www.rootz.so/d/1Ia2fg?x=1") == "1Ia2fg"
    assert proxy_url("https://www.rootz.so/d/oEBLE") == "https://www.rootz.so/api/files/proxy-download/oEBLE"
    with pytest.raises(ValueError):
        short_id("https://rootz.so.ejemplo.com/d/1Ia2fg")


def test_filename_reads_title_and_falls_back_to_short_id(monkeypatch):
    import descargador.resolvers.rootz as rootz_mod

    class Response:
        def read(self):
            return b"<title>archivo.part08.rar</title>"

    monkeypatch.setattr(rootz_mod.urllib.request, "urlopen", lambda request, timeout=30: Response())
    resolver = RootzResolver()
    assert resolver.filename("https://www.rootz.so/d/1Ia2fg") == "archivo.part08.rar"

    monkeypatch.setattr(rootz_mod.urllib.request, "urlopen", lambda request, timeout=30: (_ for _ in ()).throw(OSError()))
    assert resolver.filename("https://www.rootz.so/d/1Ia2fg") == "1Ia2fg"


def test_resolve_uses_browser_session():
    resolver = RootzResolver()
    with pytest.raises(NeedsBrowser) as error:
        resolver.resolve("https://www.rootz.so/d/1Ia2fg")
    assert error.value.page_url == "https://www.rootz.so/d/1Ia2fg"
