import os
from .resolvers.base import NeedsBrowser


class Engine:
    def __init__(self, get_resolver, download_fn, browser_resolve=None,
                 on_update=None, should_pause=None, get_conexiones=None):
        self.get_resolver = get_resolver
        self.download_fn = download_fn
        self.browser_resolve = browser_resolve
        self.on_update = on_update or (lambda item: None)
        self._should_pause = should_pause or (lambda: False)
        self._get_conexiones = get_conexiones or (lambda: 1)

    def _notify(self, item):
        self.on_update(item)

    def _progress(self, item, bajado, total):
        item.bytes_bajados = bajado
        item.total = total
        self.on_update(item)

    def process_one(self, item):
        item.estado = "descargando"
        self._notify(item)

        candidatos = [item.url] + item.mirrors
        motivo_final = "sin_resolver"
        for candidato in candidatos:
            try:
                resolver = self.get_resolver(candidato)
                if resolver is None:
                    continue
                motivo_final = "error"

                destino = os.path.join(item.carpeta, item.nombre)
                try:
                    direct = resolver.resolve(candidato)
                except NeedsBrowser as e:
                    direct = self.browser_resolve(e.page_url, resolver.extract_from_page, destino)
                    if direct is None:
                        item.estado = "completo"
                        self._notify(item)
                        return "completo"

                ok, bajado, total, motivo = self.download_fn(
                    direct,
                    destino,
                    on_progress=lambda b, t: self._progress(item, b, t),
                    should_pause=self._should_pause,
                    conexiones=self._get_conexiones(),
                )
                item.bytes_bajados = bajado
                item.total = total

                if motivo == "completo":
                    item.estado = "completo"
                    self._notify(item)
                    return motivo
                if motivo in ("pausado", "disco_lleno"):
                    item.estado = "pausado"
                    self._notify(item)
                    return motivo
                # motivo == "error": probamos el proximo candidato
            except Exception:
                motivo_final = "error"

        item.estado = "fallido"
        self._notify(item)
        return motivo_final

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
