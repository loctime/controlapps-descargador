from descargador.engine import Engine
from descargador.state import Item
from descargador.resolvers.base import Resolver, NeedsBrowser


class ResolverOK(Resolver):
    def matches(self, url):
        return True

    def resolve(self, url):
        return "http://directo/x.rar"

    def filename(self, url):
        return "x.rar"


class ResolverCaptcha(Resolver):
    def matches(self, url):
        return True

    def resolve(self, url):
        raise NeedsBrowser(url)

    def extract_from_page(self, page):
        return "no-usado"


def test_process_one_completo(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path))
    eng = Engine(
        get_resolver=lambda u: ResolverOK(),
        download_fn=lambda direct, destino, on_progress, should_pause: (True, 100, 100, "completo"),
    )
    motivo = eng.process_one(item)
    assert motivo == "completo"
    assert item.estado == "completo"
    assert item.bytes_bajados == 100


def test_process_one_captcha_usa_browser(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path))
    usados = {}

    def browser_resolve(page_url, extract_from_page):
        usados["page_url"] = page_url
        return "http://directo-via-browser/x.rar"

    def download_fn(direct, destino, on_progress, should_pause):
        usados["direct"] = direct
        return (True, 50, 50, "completo")

    eng = Engine(
        get_resolver=lambda u: ResolverCaptcha(),
        download_fn=download_fn,
        browser_resolve=browser_resolve,
    )
    motivo = eng.process_one(item)
    assert motivo == "completo"
    assert usados["page_url"] == "http://x/a.rar/file"
    assert usados["direct"] == "http://directo-via-browser/x.rar"


def test_process_one_sin_resolver_falla(tmp_path):
    item = Item(url="http://desconocido/x", nombre="x", carpeta=str(tmp_path))
    eng = Engine(
        get_resolver=lambda u: None,
        download_fn=lambda **k: (True, 0, 0, "completo"),
    )
    motivo = eng.process_one(item)
    assert motivo == "sin_resolver"
    assert item.estado == "fallido"


def test_run_queue_corta_en_pausa(tmp_path):
    items = [
        Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path)),
        Item(url="http://x/b.rar/file", nombre="b.rar", carpeta=str(tmp_path)),
    ]
    procesados = []

    def download_fn(direct, destino, on_progress, should_pause):
        procesados.append(destino)
        return (False, 10, 100, "pausado")

    eng = Engine(
        get_resolver=lambda u: ResolverOK(),
        download_fn=download_fn,
    )
    motivo = eng.run_queue(items)
    assert motivo == "pausado"
    assert len(procesados) == 1  # corta despues del primero (pausado)
    assert items[0].estado == "pausado"
    assert items[1].estado == "pendiente"


def test_process_one_resolver_explota(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path))

    def bad_get_resolver(url):
        raise RuntimeError("boom")

    eng = Engine(
        get_resolver=bad_get_resolver,
        download_fn=lambda **k: (True, 0, 0, "completo"),
    )
    motivo = eng.process_one(item)
    assert motivo == "error"
    assert item.estado == "fallido"
