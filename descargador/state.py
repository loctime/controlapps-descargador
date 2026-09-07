import os
import json
import threading
from dataclasses import dataclass, asdict, field


@dataclass
class Item:
    url: str
    nombre: str
    estado: str = "pendiente"
    bytes_bajados: int = 0
    total: int = 0
    carpeta: str = ""
    mirrors: list = field(default_factory=list)
    clip: dict = field(default_factory=dict)
    audio_format: str = ""


class State:
    def __init__(self, path):
        self.path = path
        self.items = []
        self._lock = threading.Lock()

    def load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                self.items = [Item(**d) for d in data]
            else:
                self.items = []
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            try:
                if os.path.exists(self.path):
                    os.replace(self.path, self.path + ".corrupto")
            except OSError:
                pass
            self.items = []
        return self.items

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([asdict(i) for i in self.items], f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def add(self, url, nombre, carpeta, clip=None, audio_format=""):
        clip = clip or {}
        if any((url == it.url or url in it.mirrors) and clip == it.clip and audio_format == it.audio_format for it in self.items):
            return None
        for it in self.items:
            if it.nombre == nombre and it.carpeta == carpeta and clip == it.clip and audio_format == it.audio_format:
                it.mirrors.append(url)
                return it
        item = Item(url=url, nombre=nombre, carpeta=carpeta, clip=clip, audio_format=audio_format)
        self.items.append(item)
        return item
