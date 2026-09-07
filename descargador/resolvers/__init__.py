from .mediafire import MediaFireResolver
from .megaup import MegaUpResolver
from .instagram import InstagramResolver
from .youtube import YouTubeResolver
from .web import WebMediaResolver

_RESOLVERS = [InstagramResolver(), YouTubeResolver(), MediaFireResolver(), MegaUpResolver(), WebMediaResolver()]


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
