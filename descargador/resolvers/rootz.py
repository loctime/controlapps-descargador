import re
import urllib.request

from .base import NeedsBrowser, Resolver

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)


def extract_title(html):
    m = _TITLE.search(html)
    return m.group(1).strip() if m else None


class RootzResolver(Resolver):
    def matches(self, url):
        return "rootz.so" in url

    def filename(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        titulo = extract_title(html)
        return titulo if titulo else url.rstrip("/").split("/")[-1]

    def resolve(self, url):
        raise NeedsBrowser(url)

    def extract_from_page(self, page, destino):
        # Sin captcha ni Cloudflare humano en esta cadena (confirmado en
        # vivo) - los dos clicks se scriptean de punta a punta.
        with page.expect_popup(timeout=60000) as popup_info:
            page.click("text=Download")
        popup = popup_info.value
        popup.wait_for_load_state()

        with popup.expect_download(timeout=60000) as download_info:
            popup.click("text=Download File", timeout=60000)
        download = download_info.value
        download.save_as(destino)
        popup.close()
        return None
