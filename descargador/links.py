import re

_PART = re.compile(r"part0*(\d+)", re.IGNORECASE)


_URL = re.compile(r"https?://[^\s<>\"',;]+", re.IGNORECASE)


def parse_links(text):
    """Extrae todas las URLs http(s) del texto, sin importar si vienen una
    por linea, separadas por espacios/comas o mezcladas con otro texto."""
    return [u.rstrip(").") for u in _URL.findall(text)]


def sort_by_part(links):
    def clave(l):
        m = _PART.search(l)
        return int(m.group(1)) if m else 0
    return sorted(links, key=clave)


def group_key(nombre):
    m = _PART.search(nombre)
    key = nombre[:m.start()] if m else nombre
    return key.rstrip(" .-_")


def agrupar(items):
    """Agrupa items por group_key(it.nombre), preservando el orden de
    primera aparicion. Devuelve lista de tuplas (key, [items])."""
    grupos = {}
    orden = []
    for it in items:
        k = group_key(it.nombre)
        if k not in grupos:
            grupos[k] = []
            orden.append(k)
        grupos[k].append(it)
    return [(k, grupos[k]) for k in orden]
