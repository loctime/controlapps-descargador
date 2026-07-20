import os
from .resolvers.base import NeedsBrowser


class Engine:
    def __init__(self, get_resolver, download_fn, browser_resolve=None,
                 on_update=None, should_pause=None):
        self.get_resolver = get_resolver
        self.download_fn = download_fn
        self.browser_resolve = browser_resolve
        self.on_update = on_update or (lambda item: None)
        self._should_pause = should_pause or (lambda: False)

    def _notify(self, item):
        self.on_update(item)

    def _progress(self, item, bajado, total):
        item.bytes_bajados = bajado
        item.total = total
        self.on_update(item)

    def process_one(self, item):
        item.estado = "descargando"
        self._notify(item)

        try:
            resolver = self.get_resolver(item.url)
            if resolver is None:
                item.estado = "fallido"
                self._notify(item)
                return "sin_resolver"

            try:
                direct = resolver.resolve(item.url)
            except NeedsBrowser as e:
                direct = self.browser_resolve(e.page_url, resolver.extract_from_page)

            destino = os.path.join(item.carpeta, item.nombre)
            ok, bajado, total, motivo = self.download_fn(
                direct,
                destino,
                on_progress=lambda b, t: self._progress(item, b, t),
                should_pause=self._should_pause,
            )
            item.bytes_bajados = bajado
            item.total = total

            if motivo == "completo":
                item.estado = "completo"
            elif motivo in ("pausado", "disco_lleno"):
                item.estado = "pausado"
            else:
                item.estado = "fallido"
            self._notify(item)
            return motivo

        except Exception:
            item.estado = "fallido"
            self._notify(item)
            return "error"

    def run_queue(self, items):
        # Iteramos sobre una copia para no rompernos si la GUI quita items
        # de la lista original mientras el worker corre; y salteamos los que
        # ya fueron quitados.
        for item in list(items):
            if self._should_pause():
                return None
            if item not in items:
                continue
            if item.estado == "completo":
                continue
            motivo = self.process_one(item)
            if motivo in ("pausado", "disco_lleno"):
                return motivo
        return None
