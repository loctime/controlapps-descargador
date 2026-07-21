import re
import urllib.request
from .base import Resolver, NeedsBrowser

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_DIRECT = re.compile(r'https://download[0-9]+\.mediafire\.com[^"\']+')


def extract_direct(html):
    m = _DIRECT.search(html)
    return m.group(0) if m else None


class MediaFireResolver(Resolver):
    def matches(self, url):
        return "mediafire.com" in url

    def filename(self, url):
        return url.rstrip("/").split("/")[-2]

    def resolve(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        directo = extract_direct(html)
        if not directo:
            raise NeedsBrowser(url)
        return directo

    def extract_from_page(self, page, destino):
        # Tras resolver el captcha, MediaFire muestra el boton con el link directo.
        page.wait_for_selector("a#downloadButton", timeout=300000)
        return page.get_attribute("a#downloadButton", "href")
