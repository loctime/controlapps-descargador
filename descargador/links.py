import re

_PART = re.compile(r"part0*(\d+)", re.IGNORECASE)


def parse_links(text):
    return [l.strip() for l in text.splitlines() if l.strip().lower().startswith("http")]


def sort_by_part(links):
    def clave(l):
        m = _PART.search(l)
        return int(m.group(1)) if m else 0
    return sorted(links, key=clave)
