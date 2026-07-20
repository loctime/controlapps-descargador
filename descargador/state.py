import os
import json
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

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.items = [Item(**d) for d in data]
        else:
            self.items = []
        return self.items

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([asdict(i) for i in self.items], f, ensure_ascii=False, indent=2)

    def add(self, url, nombre, carpeta):
        if any(i.url == url for i in self.items):
            return None
        item = Item(url=url, nombre=nombre, carpeta=carpeta)
        self.items.append(item)
        return item
