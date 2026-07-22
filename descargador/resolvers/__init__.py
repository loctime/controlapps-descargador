from .mediafire import MediaFireResolver
from .megaup import MegaUpResolver

_RESOLVERS = [MediaFireResolver(), MegaUpResolver()]


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
