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
