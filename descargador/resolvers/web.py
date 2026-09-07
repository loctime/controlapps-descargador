from urllib.parse import urlparse

from .instagram import InstagramResolver


class WebMediaResolver(InstagramResolver):
    """Fallback multimedia: yt-dlp detecta TikTok, Vimeo, Twitch, etc."""

    def matches(self, url):
        return urlparse(url).scheme in {"http", "https"}

    def filename(self, url):
        host = (urlparse(url).hostname or "web").replace("www.", "").replace(".", "_")
        return f"media_{host}"
