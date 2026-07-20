class NeedsBrowser(Exception):
    """El resolver no pudo obtener el link directo automáticamente (captcha/bloqueo)."""

    def __init__(self, page_url):
        self.page_url = page_url
        super().__init__(f"Necesita navegador: {page_url}")


class Resolver:
    """Base para resolvers de hosts."""

    def matches(self, url):
        raise NotImplementedError

    def resolve(self, url):
        """Devuelve el link directo. Lanza NeedsBrowser si no puede."""
        raise NotImplementedError

    def filename(self, url):
        """Nombre de archivo destino derivado de la URL de la página."""
        raise NotImplementedError

    def extract_from_page(self, page):
        """Extrae el link directo desde una página Playwright ya cargada."""
        raise NotImplementedError
