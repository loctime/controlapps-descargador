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


def test_get_resolver_instagram_reel():
    r = get_resolver("https://www.instagram.com/reel/DGBd7s-pnRp/?igsi=abc")
    assert r is not None
    assert r.filename("https://www.instagram.com/reel/DGBd7s-pnRp/") == "instagram_DGBd7s-pnRp"


def test_instagram_no_acepta_dominio_parecido():
    assert get_resolver("https://instagram.com.ejemplo.com/reel/DGBd7s-pnRp/") is None


def test_get_resolver_youtube():
    r = get_resolver("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert r is not None
    assert r.filename("https://youtu.be/dQw4w9WgXcQ") == "youtube_dQw4w9WgXcQ"
