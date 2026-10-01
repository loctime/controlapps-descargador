"""Resolver para enlaces de rootz.so.

Rootz sirve el archivo desde su endpoint ``proxy-download``.  El boton de la
pagina publica tambien puede abrir publicidad, por lo que el navegador se
manda directamente a ese endpoint en vez de simular un click.
"""

import html
import re
import urllib.request
from urllib.parse import urlparse

from .base import NeedsBrowser, Resolver

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)


def extract_title(page_html):
    """Obtiene el nombre del archivo que Rootz renderiza en ``<title>``."""
    match = _TITLE.search(page_html)
    return html.unescape(match.group(1)).strip() if match else None


def short_id(url):
    """Devuelve el identificador de una pagina ``rootz.so/d/<id>``."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname not in {"rootz.so", "www.rootz.so"} or len(parts) < 2 or parts[0] != "d":
        raise ValueError("Enlace de Rootz invalido")
    return parts[1]


def proxy_url(url):
    return f"https://www.rootz.so/api/files/proxy-download/{short_id(url)}"


class RootzResolver(Resolver):
    def matches(self, url):
        return (urlparse(url).hostname or "").lower() in {"rootz.so", "www.rootz.so"}

    def filename(self, url):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            page_html = urllib.request.urlopen(request, timeout=30).read().decode("utf-8", "ignore")
            return extract_title(page_html) or short_id(url)
        except Exception:
            return short_id(url)

    def resolve(self, url):
        # El proxy funciona en la sesion Chromium que Rootz/DDoS-Guard valida.
        # urllib puede ser bloqueado aunque la pagina publica cargue bien.
        raise NeedsBrowser(url)

    def extract_from_page(self, page, destino):
        # No hacemos click en el boton publico: Rootz inserta una pestaña de
        # publicidad en algunos casos. Navegar al proxy dispara el download
        # nativo correcto, dentro de la misma sesion ya validada.
        with page.expect_download(timeout=300000) as download_info:
            page.goto(proxy_url(page.url), wait_until="commit")
        download_info.value.save_as(destino)
        return None
