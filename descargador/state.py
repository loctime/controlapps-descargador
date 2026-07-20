import os
import json
import threading
from dataclasses import dataclass, asdict


@dataclass
class Item:
    url: str
    nombre: str
    estado: str = "pendiente"
    bytes_bajados: int = 0
    total: int = 0
    carpeta: str = ""


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

    def add(self, url, nombre, carpeta):
        if any(i.url == url for i in self.items):
            return None
        item = Item(url=url, nombre=nombre, carpeta=carpeta)
        self.items.append(item)
        return item
