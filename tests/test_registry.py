from descargador.resolvers import get_resolver
from descargador.resolvers.base import NeedsBrowser


def test_get_resolver_mediafire():
    r = get_resolver("https://www.mediafire.com/file/abc/Juego.part01.rar/file")
    assert r is not None
    assert r.matches("https://www.mediafire.com/file/abc/x.rar/file")


def test_get_resolver_desconocido_usa_fallback_web():
    assert get_resolver("https://ejemplo-desconocido.com/x") is not None


def test_needsbrowser_guarda_url():
    e = NeedsBrowser("https://www.mediafire.com/file/abc/x.rar/file")
    assert e.page_url == "https://www.mediafire.com/file/abc/x.rar/file"


def test_get_resolver_instagram_reel():
    r = get_resolver("https://www.instagram.com/reel/DGBd7s-pnRp/?igsi=abc")
    assert r is not None
    assert r.filename("https://www.instagram.com/reel/DGBd7s-pnRp/") == "instagram_DGBd7s-pnRp"


def test_dominio_parecido_no_se_confunde_con_instagram():
    assert type(get_resolver("https://instagram.com.ejemplo.com/reel/DGBd7s-pnRp/")).__name__ == "WebMediaResolver"


def test_get_resolver_youtube():
    r = get_resolver("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert r is not None
    assert r.filename("https://youtu.be/dQw4w9WgXcQ") == "youtube_dQw4w9WgXcQ"


def test_get_resolver_rootz():
    r = get_resolver("https://www.rootz.so/d/1Ia2fg")
    assert r is not None
    assert type(r).__name__ == "RootzResolver"


def test_get_resolver_web_es_fallback_para_tiktok_y_vimeo():
    assert get_resolver("https://www.tiktok.com/@cuenta/video/123") is not None
    assert get_resolver("https://vimeo.com/123") is not None


def test_link_kind_clasifica_por_host():
    from descargador.resolvers import link_kind
    assert link_kind("https://www.youtube.com/watch?v=abc123") == "video"
    assert link_kind("https://www.instagram.com/reel/DGBd7s-pnRp/") == "video"
    assert link_kind("https://www.mediafire.com/file/abc/Juego.part01.rar/file") == "archivo"
    assert link_kind("https://megaup.net/abc/Juego.rar") == "archivo"
    assert link_kind("https://www.rootz.so/d/1Ia2fg") == "archivo"
    assert link_kind("https://ejemplo-desconocido.com/x") == "desconocido"


def test_js_runtime_usa_node_si_no_hay_deno(monkeypatch):
    from descargador.resolvers import instagram
    monkeypatch.setattr(instagram.shutil, "which", lambda n: "C:/node.exe" if n == "node" else None)
    assert instagram.opciones_js_runtime() == {"js_runtimes": {"node": {}}}
    monkeypatch.setattr(instagram.shutil, "which", lambda n: "x" if n == "deno" else "y")
    assert instagram.opciones_js_runtime() == {}
    monkeypatch.setattr(instagram.shutil, "which", lambda n: None)
    assert instagram.opciones_js_runtime() == {}
