from .mediafire import MediaFireResolver

_RESOLVERS = [MediaFireResolver()]


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
