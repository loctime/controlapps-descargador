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

    def extract_from_page(self, page, destino):
        """Extrae el link directo desde una pagina Playwright ya cargada.

        Si el resolver necesita bajar el archivo el mismo (por ejemplo,
        porque las cookies de una verificacion no son reusables via urllib),
        guarda el archivo en destino y devuelve None en vez de una URL.
        """
        raise NotImplementedError

    # Los resolvers comunes devuelven una URL directa y usan downloader.py.
    # Los que necesitan una herramienta propia (por ejemplo Instagram, que
    # puede entregar video y audio por separado) pueden implementar download.
