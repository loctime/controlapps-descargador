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

    MAX_INTENTOS = 3

    def extract_from_page(self, page, destino):
        # Sin captcha ni Cloudflare humano en esta cadena (confirmado en
        # vivo), pero la red de ads rota ofertas: a veces el popup lleva
        # directo a la pagina real con el boton "Download File", a veces
        # lleva a algo que no es y hay que cerrar y volver a intentar
        # (mismo comportamiento que haria una persona a mano).
        ultimo_error = None
        for _ in range(self.MAX_INTENTOS):
            popup = None
            try:
                with page.expect_popup(timeout=60000) as popup_info:
                    page.click("text=Download")
                popup = popup_info.value
                popup.wait_for_load_state()

                with popup.expect_download(timeout=15000) as download_info:
                    popup.click("text=Download File", timeout=15000)
                download = download_info.value
                download.save_as(destino)
                popup.close()
                return None
            except Exception as e:
                ultimo_error = e
                if popup is not None:
                    try:
                        popup.close()
                    except Exception:
                        pass
        raise ultimo_error
