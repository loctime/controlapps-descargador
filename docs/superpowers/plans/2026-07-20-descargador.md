# Descargador Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un gestor de descargas propio con GUI (tipo mini-JDownloader) que baja archivos de MediaFire de a uno, con cola persistente, reanudación, y fallback a navegador visible cuando hay captcha.

**Architecture:** Módulos separados por responsabilidad. Utilidades puras (`format`, `links`) y lógica de negocio (`state`, `resolvers`, `downloader`, `engine`) se desarrollan con TDD. El fallback de navegador (`browser`) y la GUI (`app`) llevan código completo + verificación manual. Un `Engine` en un thread worker orquesta resolver → (browser si hace falta) → download, comunicándose con la GUI Tkinter vía `queue` + `root.after()`.

**Tech Stack:** Python 3.8+, Tkinter (stdlib), urllib (stdlib), Playwright (solo para el fallback de captcha), pytest (tests).

## Global Constraints

- Plataforma: **Windows 11**. Rutas con backslash en la práctica, pero usar `os.path.join` en el código.
- Python **3.8+** (usa `dataclasses` y `Range` de `http.server`, ambos disponibles desde 3.7).
- **1 sola descarga simultánea** (procesamiento secuencial de la cola).
- Solo stdlib, **excepto Playwright** (fallback de captcha) y **pytest** (tests).
- Textos de la interfaz en **español rioplatense**, sin signos de apertura `¿` `¡` (solo los de cierre).
- El proyecto vive en `C:\Users\User\Desktop\Proyectos\Descargador\`.
- Nunca romper la reanudación: las descargas siempre usan header `Range` cuando el archivo destino ya existe parcialmente.

---

## File Structure

```
Descargador/
├── run.py                       # Entry point: arranca la GUI
├── Descargador.bat              # Lanzador de doble clic
├── requirements.txt             # playwright, pytest
├── descargador/
│   ├── __init__.py
│   ├── format.py                # humano(n), bar(pct, width)
│   ├── links.py                 # parse_links(text), sort_by_part(links)
│   ├── state.py                 # Item (dataclass), State (persistencia estado.json)
│   ├── downloader.py            # download(...) con reanudación y pausa
│   ├── engine.py                # Engine: orquesta resolver→browser→download en un thread
│   ├── browser.py               # resolve_with_browser(page_url, extract_from_page) con Playwright
│   ├── app.py                   # GUI Tkinter
│   └── resolvers/
│       ├── __init__.py          # get_resolver(url) — registry
│       ├── base.py              # Resolver (base), NeedsBrowser (excepción)
│       └── mediafire.py         # MediaFireResolver, extract_direct(html)
└── tests/
    ├── test_format.py
    ├── test_links.py
    ├── test_state.py
    ├── test_registry.py
    ├── test_mediafire.py
    ├── test_downloader.py
    └── test_engine.py
```

---

### Task 1: Scaffold del proyecto + utilidades de formato

**Files:**
- Create: `descargador/__init__.py` (vacío)
- Create: `descargador/format.py`
- Create: `requirements.txt`
- Test: `tests/test_format.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `humano(n: int) -> str` — formatea bytes a "1.5MB", "2.0GB", etc.
  - `bar(pct: int, width: int = 10) -> str` — barra de progreso de bloques unicode, ej. `bar(60, 10) == "██████░░░░"`.

- [ ] **Step 1: Crear el paquete y el requirements**

Crear `descargador/__init__.py` vacío. Crear `requirements.txt`:

```
playwright
pytest
```

- [ ] **Step 2: Escribir el test que falla**

`tests/test_format.py`:

```python
from descargador.format import humano, bar


def test_humano_bytes():
    assert humano(500) == "500.0B"


def test_humano_mega():
    assert humano(1024 * 1024 * 2) == "2.0MB"


def test_bar_medio():
    assert bar(60, 10) == "██████░░░░"


def test_bar_cero():
    assert bar(0, 5) == "░░░░░"


def test_bar_lleno():
    assert bar(100, 5) == "█████"
```

- [ ] **Step 3: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_format.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'descargador.format'`

- [ ] **Step 4: Escribir la implementación mínima**

`descargador/format.py`:

```python
def humano(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def bar(pct, width=10):
    pct = max(0, min(100, pct))
    llenos = round(pct / 100 * width)
    return "█" * llenos + "░" * (width - llenos)
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `python -m pytest tests/test_format.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add descargador/__init__.py descargador/format.py requirements.txt tests/test_format.py
git commit -m "feat: utilidades de formato (humano, bar)"
```

---

### Task 2: Parseo y ordenamiento de links

**Files:**
- Create: `descargador/links.py`
- Test: `tests/test_links.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `parse_links(text: str) -> list[str]` — extrae URLs (líneas que empiezan con `http`), sin espacios.
  - `sort_by_part(links: list[str]) -> list[str]` — ordena por número de parte (`part01`, `part02`, …); los que no matchean van con clave 0.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_links.py`:

```python
from descargador.links import parse_links, sort_by_part


def test_parse_ignora_vacias_y_no_http():
    texto = "  https://a.com/1  \n\nno-es-link\nhttps://a.com/2\n"
    assert parse_links(texto) == ["https://a.com/1", "https://a.com/2"]


def test_sort_por_numero_de_parte():
    links = [
        "https://x/file/id/Juego.part03.rar/file",
        "https://x/file/id/Juego.part01.rar/file",
        "https://x/file/id/Juego.part02.rar/file",
    ]
    ordenado = sort_by_part(links)
    assert ordenado[0].endswith("part01.rar/file")
    assert ordenado[1].endswith("part02.rar/file")
    assert ordenado[2].endswith("part03.rar/file")


def test_sort_estable_con_dos_digitos():
    links = [
        "https://x/Juego.part10.rar/file",
        "https://x/Juego.part02.rar/file",
    ]
    ordenado = sort_by_part(links)
    assert ordenado[0].endswith("part02.rar/file")
    assert ordenado[1].endswith("part10.rar/file")
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_links.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'descargador.links'`

- [ ] **Step 3: Escribir la implementación mínima**

`descargador/links.py`:

```python
import re

_PART = re.compile(r"part0*(\d+)", re.IGNORECASE)


def parse_links(text):
    return [l.strip() for l in text.splitlines() if l.strip().lower().startswith("http")]


def sort_by_part(links):
    def clave(l):
        m = _PART.search(l)
        return int(m.group(1)) if m else 0
    return sorted(links, key=clave)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `python -m pytest tests/test_links.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add descargador/links.py tests/test_links.py
git commit -m "feat: parseo y ordenamiento de links por parte"
```

---

### Task 3: Persistencia de la cola (estado.json)

**Files:**
- Create: `descargador/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `Item` (dataclass): campos `url: str`, `nombre: str`, `estado: str = "pendiente"`, `bytes_bajados: int = 0`, `total: int = 0`, `carpeta: str = ""`. Estados válidos: `pendiente`, `descargando`, `completo`, `fallido`, `pausado`.
  - `State(path: str)` con métodos:
    - `load() -> list[Item]` — carga desde `path` (lista vacía si no existe).
    - `save() -> None` — persiste `self.items` a `path` en JSON.
    - `add(url, nombre, carpeta) -> Item | None` — agrega evitando duplicados por `url`; devuelve el `Item` nuevo o `None` si ya existía.
    - atributo `items: list[Item]`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_state.py`:

```python
from descargador.state import State, Item


def test_add_y_dedup(tmp_path):
    st = State(str(tmp_path / "estado.json"))
    item = st.add("https://x/a.rar/file", "a.rar", str(tmp_path))
    assert isinstance(item, Item)
    assert st.add("https://x/a.rar/file", "a.rar", str(tmp_path)) is None
    assert len(st.items) == 1


def test_save_y_load_roundtrip(tmp_path):
    ruta = str(tmp_path / "estado.json")
    st = State(ruta)
    it = st.add("https://x/a.rar/file", "a.rar", str(tmp_path))
    it.estado = "completo"
    it.bytes_bajados = 123
    st.save()

    st2 = State(ruta)
    items = st2.load()
    assert len(items) == 1
    assert items[0].nombre == "a.rar"
    assert items[0].estado == "completo"
    assert items[0].bytes_bajados == 123


def test_load_sin_archivo_devuelve_vacio(tmp_path):
    st = State(str(tmp_path / "no-existe.json"))
    assert st.load() == []
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'descargador.state'`

- [ ] **Step 3: Escribir la implementación mínima**

`descargador/state.py`:

```python
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
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `python -m pytest tests/test_state.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add descargador/state.py tests/test_state.py
git commit -m "feat: cola persistente en estado.json"
```

---

### Task 4: Base de resolvers + registry

**Files:**
- Create: `descargador/resolvers/__init__.py`
- Create: `descargador/resolvers/base.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `NeedsBrowser(Exception)` con atributo `page_url: str`.
  - `Resolver` (base) con métodos `matches(url) -> bool`, `resolve(url) -> str`, `filename(url) -> str`, `extract_from_page(page) -> str` (todos `NotImplementedError` en la base).
  - `get_resolver(url: str) -> Resolver | None` en `resolvers/__init__.py` — devuelve el primer resolver registrado cuyo `matches(url)` es `True`, o `None`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_registry.py`:

```python
from descargador.resolvers import get_resolver
from descargador.resolvers.base import NeedsBrowser


def test_get_resolver_mediafire():
    r = get_resolver("https://www.mediafire.com/file/abc/Juego.part01.rar/file")
    assert r is not None
    assert r.matches("https://www.mediafire.com/file/abc/x.rar/file")


def test_get_resolver_desconocido_devuelve_none():
    assert get_resolver("https://ejemplo-desconocido.com/x") is None


def test_needsbrowser_guarda_url():
    e = NeedsBrowser("https://www.mediafire.com/file/abc/x.rar/file")
    assert e.page_url == "https://www.mediafire.com/file/abc/x.rar/file"
```

Nota: este test depende del `MediaFireResolver` de la Task 5 estando registrado. Si se ejecuta antes de la Task 5, registrar temporalmente un resolver dummy. Para mantener el orden TDD limpio, implementar primero el registry con lista vacía (Steps 3), correr solo `test_needsbrowser_guarda_url`, y completar el registro del `MediaFireResolver` en la Task 5.

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_registry.py::test_needsbrowser_guarda_url -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'descargador.resolvers'`

- [ ] **Step 3: Escribir la implementación mínima**

`descargador/resolvers/base.py`:

```python
class NeedsBrowser(Exception):
    """El resolver no pudo obtener el link directo automáticamente (captcha/bloqueo)."""

    def __init__(self, page_url):
        self.page_url = page_url
        super().__init__(f"Necesita navegador: {page_url}")


class Resolver:
    """Base para resolvers de hosts."""

    def matches(self, url):
        raise NotImplementedError

    def resolve(self, url):
        """Devuelve el link directo. Lanza NeedsBrowser si no puede."""
        raise NotImplementedError

    def filename(self, url):
        """Nombre de archivo destino derivado de la URL de la página."""
        raise NotImplementedError

    def extract_from_page(self, page):
        """Extrae el link directo desde una página Playwright ya cargada."""
        raise NotImplementedError
```

`descargador/resolvers/__init__.py`:

```python
_RESOLVERS = []


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
```

- [ ] **Step 4: Correr el test parcial para verificar que pasa**

Run: `python -m pytest tests/test_registry.py::test_needsbrowser_guarda_url -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add descargador/resolvers/base.py descargador/resolvers/__init__.py tests/test_registry.py
git commit -m "feat: base de resolvers y registry vacio"
```

---

### Task 5: Resolver de MediaFire

**Files:**
- Create: `descargador/resolvers/mediafire.py`
- Modify: `descargador/resolvers/__init__.py` (registrar `MediaFireResolver`)
- Test: `tests/test_mediafire.py`

**Interfaces:**
- Consumes: `Resolver`, `NeedsBrowser` de `resolvers/base.py`.
- Produces:
  - `extract_direct(html: str) -> str | None` — busca el link directo `https://download<N>.mediafire.com/...` en el HTML; `None` si no está.
  - `MediaFireResolver(Resolver)`:
    - `matches(url)` — `True` si `"mediafire.com"` está en la URL.
    - `filename(url)` — penúltimo segmento de la ruta (`.../file/<id>/<NOMBRE>/file` → `<NOMBRE>`).
    - `resolve(url)` — descarga el HTML, aplica `extract_direct`; si no hay link, lanza `NeedsBrowser(url)`.
    - `extract_from_page(page)` — espera el botón de descarga y devuelve su `href`.
  - Queda registrado en `resolvers/__init__.py` (`test_get_resolver_mediafire` pasa).

- [ ] **Step 1: Escribir el test que falla**

`tests/test_mediafire.py`:

```python
from descargador.resolvers.mediafire import extract_direct, MediaFireResolver
from descargador.resolvers.base import NeedsBrowser
import pytest


def test_extract_direct_encuentra_link():
    html = '<a id="downloadButton" href="https://download1234.mediafire.com/abc/x.rar">bajar</a>'
    assert extract_direct(html) == "https://download1234.mediafire.com/abc/x.rar"


def test_extract_direct_sin_link_devuelve_none():
    html = "<html><body>captcha aca, no hay link</body></html>"
    assert extract_direct(html) is None


def test_filename_penultimo_segmento():
    r = MediaFireResolver()
    url = "https://www.mediafire.com/file/abc123/Juego.part01.rar/file"
    assert r.filename(url) == "Juego.part01.rar"


def test_matches():
    r = MediaFireResolver()
    assert r.matches("https://www.mediafire.com/file/abc/x.rar/file")
    assert not r.matches("https://mega.nz/file/abc")
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_mediafire.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'descargador.resolvers.mediafire'`

- [ ] **Step 3: Escribir la implementación**

`descargador/resolvers/mediafire.py`:

```python
import re
import urllib.request
from .base import Resolver, NeedsBrowser

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_DIRECT = re.compile(r'https://download[0-9]+\.mediafire\.com[^"\']+')


def extract_direct(html):
    m = _DIRECT.search(html)
    return m.group(0) if m else None


class MediaFireResolver(Resolver):
    def matches(self, url):
        return "mediafire.com" in url

    def filename(self, url):
        return url.rstrip("/").split("/")[-2]

    def resolve(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        directo = extract_direct(html)
        if not directo:
            raise NeedsBrowser(url)
        return directo

    def extract_from_page(self, page):
        # Tras resolver el captcha, MediaFire muestra el boton con el link directo.
        page.wait_for_selector("a#downloadButton", timeout=300000)
        return page.get_attribute("a#downloadButton", "href")
```

- [ ] **Step 4: Registrar el resolver**

Modificar `descargador/resolvers/__init__.py`:

```python
from .mediafire import MediaFireResolver

_RESOLVERS = [MediaFireResolver()]


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
```

- [ ] **Step 5: Correr todos los tests de resolvers para verificar que pasan**

Run: `python -m pytest tests/test_mediafire.py tests/test_registry.py -v`
Expected: PASS (7 passed en total)

- [ ] **Step 6: Commit**

```bash
git add descargador/resolvers/mediafire.py descargador/resolvers/__init__.py tests/test_mediafire.py
git commit -m "feat: resolver de MediaFire con deteccion de captcha"
```

---

### Task 6: Motor de descarga con reanudación y pausa

**Files:**
- Create: `descargador/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `download(direct_url, destino, on_progress=None, should_pause=None, chunk_size=CHUNK) -> tuple[bool, int, int, str]`
    - `on_progress(bajado: int, total: int)` — callback opcional de progreso.
    - `should_pause() -> bool` — callback opcional; si devuelve `True`, corta y devuelve motivo `"pausado"`.
    - Devuelve `(ok, bytes_bajados, total, motivo)`. `motivo` ∈ `{"completo", "pausado", "disco_lleno"}`.
    - Usa header `Range` si `destino` ya existe (reanudación).
  - Constante `CHUNK = 1 << 20` (1 MB).

- [ ] **Step 1: Escribir el test que falla**

`tests/test_downloader.py`:

```python
import http.server
import socketserver
import threading
import functools
import pytest
from descargador.downloader import download


def _serve(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def test_download_completo(tmp_path):
    contenido = b"x" * 5000
    (tmp_path / "f.bin").write_bytes(contenido)
    httpd, port = _serve(str(tmp_path))
    try:
        dest = tmp_path / "out.bin"
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest), chunk_size=1024
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
    finally:
        httpd.shutdown()


def test_download_reanuda(tmp_path):
    contenido = b"abcdefgh" * 1000  # 8000 bytes
    (tmp_path / "f.bin").write_bytes(contenido)
    dest = tmp_path / "out.bin"
    dest.write_bytes(contenido[:3000])  # parcial
    httpd, port = _serve(str(tmp_path))
    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest), chunk_size=1024
        )
        assert ok and motivo == "completo"
        assert dest.read_bytes() == contenido
    finally:
        httpd.shutdown()


def test_download_pausa(tmp_path):
    contenido = b"y" * 5000
    (tmp_path / "f.bin").write_bytes(contenido)
    dest = tmp_path / "out.bin"
    httpd, port = _serve(str(tmp_path))
    llamadas = {"n": 0}

    def should_pause():
        llamadas["n"] += 1
        return llamadas["n"] > 1  # pausa despues del primer chunk

    try:
        ok, bajado, total, motivo = download(
            f"http://127.0.0.1:{port}/f.bin", str(dest),
            should_pause=should_pause, chunk_size=1024,
        )
        assert not ok and motivo == "pausado"
        assert 0 < bajado < 5000
    finally:
        httpd.shutdown()
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_downloader.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'descargador.downloader'`

- [ ] **Step 3: Escribir la implementación**

`descargador/downloader.py`:

```python
import os
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CHUNK = 1 << 20  # 1 MB


def download(direct_url, destino, on_progress=None, should_pause=None, chunk_size=CHUNK):
    on_progress = on_progress or (lambda bajado, total: None)
    should_pause = should_pause or (lambda: False)

    ya = os.path.getsize(destino) if os.path.exists(destino) else 0
    headers = {"User-Agent": UA}
    if ya:
        headers["Range"] = f"bytes={ya}-"

    req = urllib.request.Request(direct_url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=60)

    if resp.status == 206:
        total = int(resp.headers.get("Content-Range", "/0").split("/")[-1] or 0)
        modo = "ab"
    else:
        ya = 0
        modo = "wb"
        total = int(resp.headers.get("Content-Length", 0))

    if ya and total and ya >= total:
        return (True, ya, total, "completo")

    bajado = ya
    with open(destino, modo) as f:
        while True:
            if should_pause():
                return (False, bajado, total, "pausado")
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            try:
                f.write(chunk)
            except OSError as e:
                if getattr(e, "errno", None) == 28:  # No space left on device
                    return (False, bajado, total, "disco_lleno")
                raise
            bajado += len(chunk)
            on_progress(bajado, total)

    return (True, bajado, total, "completo")
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `python -m pytest tests/test_downloader.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add descargador/downloader.py tests/test_downloader.py
git commit -m "feat: motor de descarga con reanudacion y pausa"
```

---

### Task 7: Orquestación (Engine)

**Files:**
- Create: `descargador/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `NeedsBrowser` de `resolvers/base.py`; el patrón de `download` (Task 6); `Item` (Task 3).
- Produces:
  - `Engine(get_resolver, download_fn, browser_resolve=None, on_update=None, should_pause=None)`:
    - `get_resolver(url) -> Resolver | None`
    - `download_fn(direct, destino, on_progress, should_pause) -> (ok, bajado, total, motivo)` (misma firma que `download`)
    - `browser_resolve(page_url, extract_from_page) -> str` (link directo obtenido vía navegador)
    - `on_update(item)` — callback tras cada cambio de estado del ítem.
    - `should_pause() -> bool`
    - `process_one(item) -> str` — procesa un ítem; devuelve motivo (`"completo"`, `"pausado"`, `"disco_lleno"`, `"error"`, `"sin_resolver"`). Muta `item.estado`, `item.bytes_bajados`, `item.total`.
    - `run_queue(items)` — recorre la lista; corta si `should_pause()` o si un ítem devuelve `"pausado"`/`"disco_lleno"`; saltea los `"completo"`.

- [ ] **Step 1: Escribir el test que falla**

`tests/test_engine.py`:

```python
from descargador.engine import Engine
from descargador.state import Item
from descargador.resolvers.base import Resolver, NeedsBrowser


class ResolverOK(Resolver):
    def matches(self, url):
        return True

    def resolve(self, url):
        return "http://directo/x.rar"

    def filename(self, url):
        return "x.rar"


class ResolverCaptcha(Resolver):
    def matches(self, url):
        return True

    def resolve(self, url):
        raise NeedsBrowser(url)

    def extract_from_page(self, page):
        return "no-usado"


def test_process_one_completo(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path))
    eng = Engine(
        get_resolver=lambda u: ResolverOK(),
        download_fn=lambda direct, destino, on_progress, should_pause: (True, 100, 100, "completo"),
    )
    motivo = eng.process_one(item)
    assert motivo == "completo"
    assert item.estado == "completo"
    assert item.bytes_bajados == 100


def test_process_one_captcha_usa_browser(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path))
    usados = {}

    def browser_resolve(page_url, extract_from_page):
        usados["page_url"] = page_url
        return "http://directo-via-browser/x.rar"

    def download_fn(direct, destino, on_progress, should_pause):
        usados["direct"] = direct
        return (True, 50, 50, "completo")

    eng = Engine(
        get_resolver=lambda u: ResolverCaptcha(),
        download_fn=download_fn,
        browser_resolve=browser_resolve,
    )
    motivo = eng.process_one(item)
    assert motivo == "completo"
    assert usados["page_url"] == "http://x/a.rar/file"
    assert usados["direct"] == "http://directo-via-browser/x.rar"


def test_process_one_sin_resolver_falla(tmp_path):
    item = Item(url="http://desconocido/x", nombre="x", carpeta=str(tmp_path))
    eng = Engine(
        get_resolver=lambda u: None,
        download_fn=lambda **k: (True, 0, 0, "completo"),
    )
    motivo = eng.process_one(item)
    assert motivo == "sin_resolver"
    assert item.estado == "fallido"


def test_run_queue_corta_en_pausa(tmp_path):
    items = [
        Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path)),
        Item(url="http://x/b.rar/file", nombre="b.rar", carpeta=str(tmp_path)),
    ]
    procesados = []

    def download_fn(direct, destino, on_progress, should_pause):
        procesados.append(destino)
        return (False, 10, 100, "pausado")

    eng = Engine(
        get_resolver=lambda u: ResolverOK(),
        download_fn=download_fn,
    )
    eng.run_queue(items)
    assert len(procesados) == 1  # corta despues del primero (pausado)
    assert items[0].estado == "pausado"
    assert items[1].estado == "pendiente"
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'descargador.engine'`

- [ ] **Step 3: Escribir la implementación**

`descargador/engine.py`:

```python
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

        resolver = self.get_resolver(item.url)
        if resolver is None:
            item.estado = "fallido"
            self._notify(item)
            return "sin_resolver"

        try:
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
        for item in items:
            if self._should_pause():
                return
            if item.estado == "completo":
                continue
            motivo = self.process_one(item)
            if motivo in ("pausado", "disco_lleno"):
                return
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Correr toda la suite para verificar que no se rompió nada**

Run: `python -m pytest -v`
Expected: PASS (todos)

- [ ] **Step 6: Commit**

```bash
git add descargador/engine.py tests/test_engine.py
git commit -m "feat: orquestacion resolver->browser->download (Engine)"
```

---

### Task 8: Fallback de navegador con Playwright

**Files:**
- Create: `descargador/browser.py`

**Interfaces:**
- Consumes: `extract_from_page` de cada resolver (Task 5).
- Produces:
  - `resolve_with_browser(page_url: str, extract_from_page) -> str` — abre Chromium **visible**, navega a `page_url`, deja que el usuario resuelva el captcha, y devuelve el link directo vía `extract_from_page(page)`.

**Nota:** este módulo maneja un navegador real con interacción humana; no lleva test automatizado. Se verifica manualmente en la Task 9 con un link real de MediaFire que dispare captcha (o forzando el fallback).

- [ ] **Step 1: Instalar Playwright y el navegador**

Run:
```bash
pip install playwright
python -m playwright install chromium
```
Expected: descarga e instala Chromium para Playwright sin errores.

- [ ] **Step 2: Escribir la implementación**

`descargador/browser.py`:

```python
def resolve_with_browser(page_url, extract_from_page):
    """Abre un navegador visible para que el usuario resuelva el captcha.

    Navega a page_url, espera a que extract_from_page(page) devuelva el link
    directo (tras la resolucion manual del captcha), y lo retorna.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.goto(page_url)
            return extract_from_page(page)
        finally:
            browser.close()
```

- [ ] **Step 3: Smoke test manual del import**

Run: `python -c "from descargador.browser import resolve_with_browser; print('ok')"`
Expected: imprime `ok` sin errores de import.

- [ ] **Step 4: Commit**

```bash
git add descargador/browser.py
git commit -m "feat: fallback de captcha con navegador Playwright"
```

---

### Task 9: GUI Tkinter + entry point + lanzador

**Files:**
- Create: `descargador/app.py`
- Create: `run.py`
- Create: `Descargador.bat`

**Interfaces:**
- Consumes: `State`, `Item` (Task 3); `Engine` (Task 7); `download` (Task 6); `get_resolver` (Tasks 4-5); `resolve_with_browser` (Task 8); `parse_links`, `sort_by_part` (Task 2); `humano`, `bar` (Task 1).
- Produces: `App` (clase Tkinter) y `main()` en `run.py`.

**Diseño de la GUI:**
- Ventana con tres zonas (usar `ttk`):
  - **Arriba:** `Text` para pegar links + botón "Agregar"; botón "Cargar .txt"; label con la carpeta destino + botón "Elegir carpeta".
  - **Medio:** `ttk.Treeview` con columnas: Nombre, Tamaño, Progreso (barra unicode + %), Estado.
  - **Abajo:** botones "Pausar" / "Reanudar" (toggle), "Reintentar fallidos", "Abrir carpeta".
- **Threading:** el `Engine` corre `run_queue` en un `threading.Thread`. El callback `on_update` del Engine **no toca widgets**: pone el `Item` en una `queue.Queue`. La GUI hace `root.after(200, self._drenar_cola)` para refrescar el Treeview desde el hilo principal.
- La carpeta destino se guarda en `estado_config.json` (junto a `estado.json`) para recordar la última usada.
- **Progreso por ítem:** columna "Progreso" muestra `bar(pct) + " " + pct%` usando `format.bar`.

- [ ] **Step 1: Escribir la GUI**

`descargador/app.py`:

```python
import os
import queue
import threading
import json
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .state import State
from .engine import Engine
from .downloader import download
from .browser import resolve_with_browser
from .resolvers import get_resolver
from .links import parse_links, sort_by_part
from .format import humano, bar

CARPETA_APP = os.path.join(os.path.expanduser("~"), ".descargador")
os.makedirs(CARPETA_APP, exist_ok=True)
ESTADO = os.path.join(CARPETA_APP, "estado.json")
CONFIG = os.path.join(CARPETA_APP, "config.json")


def _cargar_carpeta_destino():
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f).get("carpeta", "")
    return ""


def _guardar_carpeta_destino(carpeta):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"carpeta": carpeta}, f, ensure_ascii=False)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Descargador")
        self.root.geometry("760x460")

        self.state = State(ESTADO)
        self.state.load()
        self.carpeta = _cargar_carpeta_destino()
        self.cola_ui = queue.Queue()
        self.pausado = threading.Event()  # set = pausado
        self.pausado.set()  # arranca en pausa hasta que el usuario le da play
        self.worker = None

        self.engine = Engine(
            get_resolver=get_resolver,
            download_fn=download,
            browser_resolve=resolve_with_browser,
            on_update=lambda item: self.cola_ui.put(item),
            should_pause=lambda: self.pausado.is_set(),
        )

        self._construir_ui()
        self._refrescar_tabla()
        self.root.after(200, self._drenar_cola)

    def _construir_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        self.txt = tk.Text(top, height=4, width=70)
        self.txt.grid(row=0, column=0, columnspan=4, sticky="we")
        ttk.Button(top, text="Agregar", command=self._agregar_pegados).grid(row=1, column=0, pady=4, sticky="w")
        ttk.Button(top, text="Cargar .txt", command=self._cargar_txt).grid(row=1, column=1, pady=4, sticky="w")
        ttk.Button(top, text="Elegir carpeta", command=self._elegir_carpeta).grid(row=1, column=2, pady=4, sticky="w")
        self.lbl_carpeta = ttk.Label(top, text=self.carpeta or "(sin carpeta)")
        self.lbl_carpeta.grid(row=1, column=3, pady=4, sticky="w")

        cols = ("nombre", "tam", "prog", "estado")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=12)
        for c, t, w in (("nombre", "Nombre", 300), ("tam", "Tamaño", 90),
                        ("prog", "Progreso", 200), ("estado", "Estado", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=8)

        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.btn_play = ttk.Button(bottom, text="Reanudar", command=self._toggle_pausa)
        self.btn_play.pack(side="left")
        ttk.Button(bottom, text="Reintentar fallidos", command=self._reintentar).pack(side="left", padx=6)
        ttk.Button(bottom, text="Abrir carpeta", command=self._abrir_carpeta).pack(side="left")

    def _agregar_links(self, urls):
        if not self.carpeta:
            messagebox.showwarning("Falta carpeta", "Elegi primero una carpeta destino.")
            return
        for url in sort_by_part(urls):
            r = get_resolver(url)
            nombre = r.filename(url) if r else url.rstrip("/").split("/")[-1]
            self.state.add(url, nombre, self.carpeta)
        self.state.save()
        self._refrescar_tabla()

    def _agregar_pegados(self):
        urls = parse_links(self.txt.get("1.0", "end"))
        self.txt.delete("1.0", "end")
        self._agregar_links(urls)

    def _cargar_txt(self):
        ruta = filedialog.askopenfilename(filetypes=[("Texto", "*.txt")])
        if not ruta:
            return
        with open(ruta, encoding="utf-8") as f:
            self._agregar_links(parse_links(f.read()))

    def _elegir_carpeta(self):
        c = filedialog.askdirectory()
        if c:
            self.carpeta = c
            _guardar_carpeta_destino(c)
            self.lbl_carpeta.config(text=c)

    def _toggle_pausa(self):
        if self.pausado.is_set():
            self.pausado.clear()
            self.btn_play.config(text="Pausar")
            self._arrancar_worker()
        else:
            self.pausado.set()
            self.btn_play.config(text="Reanudar")

    def _arrancar_worker(self):
        if self.worker and self.worker.is_alive():
            return

        def correr():
            self.engine.run_queue(self.state.items)
            self.state.save()

        self.worker = threading.Thread(target=correr, daemon=True)
        self.worker.start()

    def _reintentar(self):
        for it in self.state.items:
            if it.estado == "fallido":
                it.estado = "pendiente"
        self.state.save()
        self._refrescar_tabla()
        if not self.pausado.is_set():
            self._arrancar_worker()

    def _abrir_carpeta(self):
        if self.carpeta and os.path.isdir(self.carpeta):
            os.startfile(self.carpeta)  # Windows

    def _fila(self, it):
        pct = int(it.bytes_bajados * 100 / it.total) if it.total else 0
        return (it.nombre, humano(it.total) if it.total else "?",
                f"{bar(pct)} {pct}%", it.estado)

    def _refrescar_tabla(self):
        self.tree.delete(*self.tree.get_children())
        for it in self.state.items:
            self.tree.insert("", "end", iid=it.url, values=self._fila(it))

    def _drenar_cola(self):
        cambiado = False
        try:
            while True:
                it = self.cola_ui.get_nowait()
                if self.tree.exists(it.url):
                    self.tree.item(it.url, values=self._fila(it))
                cambiado = True
        except queue.Empty:
            pass
        if cambiado:
            self.state.save()
        self.root.after(200, self._drenar_cola)
```

- [ ] **Step 2: Escribir el entry point**

`run.py`:

```python
import tkinter as tk
from descargador.app import App


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Escribir el lanzador .bat**

`Descargador.bat`:

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo No se encontro Python en el PATH.
  echo Instalalo desde https://python.org y marca "Add Python to PATH".
  pause
  exit /b
)
python "run.py"
```

- [ ] **Step 4: Verificación manual — arranque de la GUI**

Run: `python run.py`
Expected: abre la ventana con las tres zonas. Sin errores en consola.

- [ ] **Step 5: Verificación manual — flujo completo**

Checklist (marcar cada uno):
1. Elegir carpeta destino → el label muestra la ruta.
2. Pegar 2-3 links de MediaFire en el `Text` → "Agregar" → aparecen ordenados por parte en la tabla, estado "pendiente".
3. "Reanudar" → el primero pasa a "descargando", la barra de progreso avanza, el `.rar` aparece en la carpeta.
4. "Pausar" → la descarga frena; el archivo parcial queda en disco.
5. "Reanudar" de nuevo → continúa desde donde quedó (no reinicia de cero).
6. Cerrar la app con una descarga a medias y volver a abrir → la cola sigue ahí con el progreso guardado.
7. Si un link dispara captcha → se abre el navegador visible; al resolverlo, la descarga continúa.
8. Forzar un fallo (link roto) → estado "fallido" → "Reintentar fallidos" lo vuelve a "pendiente".
9. "Abrir carpeta" → abre el explorador en la carpeta destino.

- [ ] **Step 6: Commit**

```bash
git add descargador/app.py run.py Descargador.bat
git commit -m "feat: GUI Tkinter, entry point y lanzador"
```

---

## Notas de implementación

- **Orden de ejecución:** las Tasks 1-7 son TDD puro y se pueden verificar automáticamente. Las Tasks 8-9 (navegador y GUI) requieren verificación manual porque manejan un navegador real y una interfaz gráfica.
- **Desviación menor respecto del spec:** el spec pedía "barra de progreso por ítem". En lugar de incrustar un widget `Progressbar` por fila (que Treeview no soporta bien), se usa una barra de bloques unicode (`bar()`) dentro de una columna de texto. Es visual y stdlib-only. Si más adelante se quiere una barra gráfica real, se puede migrar a otra librería de tabla.
- **Extensibilidad (hosts futuros):** agregar un host nuevo = crear `resolvers/<host>.py` con la interfaz `Resolver` (matches/resolve/filename/extract_from_page) y registrarlo en `resolvers/__init__.py`. Nada más cambia. El fallback de navegador y el engine ya son genéricos.
```
