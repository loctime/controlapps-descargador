from descargador.resolvers import get_resolver
from descargador.resolvers.base import NeedsBrowser


def test_get_resolver_mediafire():
    r = get_resolver("https://www.mediafire.com/file/abc/Juego.part01.rar/file")
    assert r is not None
    assert r.matches("https://www.mediafire.com/file/abc/x.rar/file")


def test_get_resolver_desconocido_devuelve_none():
    assert get_resolver("https://ejemplo-desconocido.com/x") is None


def test_needsbrowser_guarda_url():
    e = NeedsBrowser("https://www.mediafire.com/file/abc/x.rar/file")
    assert e.page_url == "https://www.mediafire.com/file/abc/x.rar/file"
