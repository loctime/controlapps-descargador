import re
import urllib.request

from .base import NeedsBrowser, Resolver

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_DIRECT = re.compile(r"href='(https://download\.megaup\.net/\?url=[^']+)'")


def extract_direct(html):
    m = _DIRECT.search(html)
    return m.group(1) if m else None


class MegaUpResolver(Resolver):
    def matches(self, url):
        return "megaup.net" in url

    def filename(self, url):
        return url.rstrip("/").split("/")[-1]

    def resolve(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        directo = extract_direct(html)
        if not directo:
            raise RuntimeError("no se encontro el link directo de megaup.net")
        raise NeedsBrowser(directo)

    def extract_from_page(self, page, destino):
        # download.megaup.net esta detras de un Cloudflare Turnstile
        # interactivo: esperamos a que la persona clickee el check y el
        # navegador dispare su descarga nativa, y la guardamos nosotros.
        with page.expect_download(timeout=300000) as download_info:
            pass
        download = download_info.value
        download.save_as(destino)
        return None
