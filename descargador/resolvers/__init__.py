from .mediafire import MediaFireResolver
from .megaup import MegaUpResolver
from .rootz import RootzResolver
from .instagram import InstagramResolver
from .youtube import YouTubeResolver
from .web import WebMediaResolver

_RESOLVERS = [InstagramResolver(), YouTubeResolver(), MediaFireResolver(), MegaUpResolver(), RootzResolver(), WebMediaResolver()]


def link_kind(url):
    resolver = get_resolver(url)
    return resolver.kind if resolver else "archivo"


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
