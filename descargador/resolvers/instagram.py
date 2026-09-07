import glob
import os
import re
import sys
from urllib.parse import urlparse

from .base import Resolver


class DownloadPaused(Exception):
    """Corta yt-dlp desde un progress hook cuando la cola se pausa."""


class InstagramResolver(Resolver):
    """Descarga reels y publicaciones publicas mediante yt-dlp.

    Instagram suele separar video y audio, por eso no alcanza con entregar una
    URL directa al downloader comun: yt-dlp baja y fusiona los formatos.
    """

    _PATH = re.compile(r"^/(?:reel|p|tv|stories)/([^/?#]+)", re.IGNORECASE)

    def matches(self, url):
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return (host == "instagram.com" or host.endswith(".instagram.com")) and bool(
            self._PATH.match(parsed.path)
        )

    def _id(self, url):
        match = self._PATH.match(urlparse(url).path)
        return match.group(1) if match else "publicacion"

    def filename(self, url):
        # La extension real se conoce recien cuando yt-dlp inspecciona el post.
        return f"instagram_{self._id(url)}"

    def resolve(self, url):
        raise NotImplementedError("Instagram se descarga con yt-dlp")

    def download(self, url, destino, on_progress=None, should_pause=None, clip=None):
        """Devuelve (ok, bajado, total, motivo, nombre_final)."""
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("Falta yt-dlp. Ejecuta: pip install -r requirements.txt") from exc

        on_progress = on_progress or (lambda bajado, total: None)
        should_pause = should_pause or (lambda: False)
        progreso = {"bajado": 0, "total": 0}

        def hook(data):
            if should_pause():
                raise DownloadPaused()
            if data.get("status") == "downloading":
                progreso["bajado"] = data.get("downloaded_bytes", 0)
                progreso["total"] = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                on_progress(progreso["bajado"], progreso["total"])

        opciones = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": destino + ".%(ext)s",
            "continuedl": True,
            "progress_hooks": [hook],
            "windowsfilenames": True,
        }
        if clip:
            inicio, fin = clip["inicio"], clip["fin"]

            def rangos(info, ydl):
                yield {"start_time": inicio, "end_time": fin}

            opciones["download_ranges"] = rangos
            opciones["force_keyframes_at_cuts"] = True
        # En la version instalable, FFmpeg viaja junto al ejecutable dentro de
        # PyInstaller. yt-dlp lo necesita para unir video y audio de los reels.
        carpeta_empaquetada = getattr(sys, "_MEIPASS", None)
        nombre_ffmpeg = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
        if carpeta_empaquetada and os.path.exists(os.path.join(carpeta_empaquetada, nombre_ffmpeg)):
            opciones["ffmpeg_location"] = carpeta_empaquetada
        try:
            with yt_dlp.YoutubeDL(opciones) as ydl:
                ydl.download([url])
        except DownloadPaused:
            return False, progreso["bajado"], progreso["total"], "pausado", None
        except Exception:
            return False, progreso["bajado"], progreso["total"], "error", None

        archivos = [
            path for path in glob.glob(destino + ".*")
            if os.path.isfile(path) and not path.endswith((".part", ".ytdl"))
        ]
        if not archivos:
            return False, progreso["bajado"], progreso["total"], "error", None

        final = max(archivos, key=os.path.getmtime)
        total = os.path.getsize(final)
        on_progress(total, total)
        return True, total, total, "completo", os.path.basename(final)
