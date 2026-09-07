import re
from urllib.parse import urlparse

from .instagram import InstagramResolver


class YouTubeResolver(InstagramResolver):
    """YouTube comparte el motor yt-dlp de Instagram, incluido el recorte."""

    _ID = re.compile(r"^[A-Za-z0-9_-]{6,}$")

    def matches(self, url):
        host = (urlparse(url).hostname or "").lower()
        return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

    def _id(self, url):
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname.lower() == "youtu.be":
            return parsed.path.strip("/") or "video"
        # No necesitamos validar el id aqui: yt-dlp muestra el error correcto
        # para enlaces validos pero no disponibles.
        for part in parsed.query.split("&"):
            if part.startswith("v="):
                return part[2:] or "video"
        parts = [p for p in parsed.path.split("/") if p]
        return parts[-1] if parts else "video"

    def filename(self, url):
        return f"youtube_{self._id(url)}"
