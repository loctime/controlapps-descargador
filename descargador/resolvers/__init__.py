from .mediafire import MediaFireResolver
from .megaup import MegaUpResolver
from .instagram import InstagramResolver
from .youtube import YouTubeResolver

_RESOLVERS = [InstagramResolver(), YouTubeResolver(), MediaFireResolver(), MegaUpResolver()]


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
