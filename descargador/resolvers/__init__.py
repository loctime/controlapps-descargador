from .mediafire import MediaFireResolver
from .megaup import MegaUpResolver
from .rootz import RootzResolver

_RESOLVERS = [MediaFireResolver(), MegaUpResolver(), RootzResolver()]


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
