import playwright.sync_api

from descargador.browser import resolve_with_browser


def test_resolve_with_browser_pasa_destino_a_extract_from_page(monkeypatch):
    llamadas = {}

    class FakePage:
        def goto(self, url):
            llamadas["goto"] = url

    class FakeBrowser:
        def new_page(self):
            return FakePage()

        def close(self):
            llamadas["closed"] = True

    class FakeChromium:
        def launch(self, headless=False):
            return FakeBrowser()

    class FakePlaywrightCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        chromium = FakeChromium()

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: FakePlaywrightCtx())

    def extract_from_page(page, destino):
        llamadas["page"] = page
        llamadas["destino"] = destino
        return "resultado"

    resultado = resolve_with_browser("http://x/pagina", extract_from_page, "/tmp/destino.rar")

    assert resultado == "resultado"
    assert llamadas["goto"] == "http://x/pagina"
    assert llamadas["destino"] == "/tmp/destino.rar"
    assert isinstance(llamadas["page"], FakePage)
    assert llamadas["closed"] is True
