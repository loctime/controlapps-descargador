# Resolver para megaup.net — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resolver for `megaup.net` links so the mirrors already sitting inert in `mirrors[]` (see `2026-07-21-mirrors-failover.md`) start working, following the same human-solves-the-challenge pattern already used for MediaFire's captcha.

**Architecture:** `MegaUpResolver.resolve()` extracts the real `download.megaup.net/?url=...` link from the file page's HTML via a plain HTTP GET + regex (no browser needed for this part — confirmed live), then always raises `NeedsBrowser` with that link, because it's permanently gated behind an interactive Cloudflare Turnstile checkbox a human must click. The `Resolver.extract_from_page` contract grows a `destino` parameter and a `None`-return convention: returning `None` means "I already saved the file to `destino` myself" (the browser's own native download, captured via Playwright), which `Engine.process_one` treats as an immediate `"completo"` — skipping the normal `download_fn` (urllib) path entirely, since the Cloudflare-cleared cookies aren't portable to a plain HTTP client.

**Tech Stack:** Python stdlib (`re`, `urllib.request`), Playwright sync API (already a project dependency), `pytest`.

## Global Constraints

- Do not attempt to script past the Cloudflare Turnstile checkbox — a human must click it. This is a hard line, not a technical shortcut to optimize away.
- No resume-by-Range, no segmented multi-connection, no live progress, no mid-flight pause for `megaup.net` — the browser downloads the file in one shot. Documented limitation, not a bug to fix here.
- `Resolver.extract_from_page` signature changes project-wide from `(self, page)` to `(self, page, destino)` — every implementation (existing `MediaFireResolver` included) and every caller (`browser.py`, `engine.py`) must be updated together so nothing is left out of sync.
- Timeout for the human to act is 5 minutes (`300000`ms) — same value already used for MediaFire's captcha wait, kept consistent rather than inventing a new constant.

---

### Task 1: `Resolver` contract change — `extract_from_page(page, destino)` + browser-owns-download path in `Engine`

**Files:**
- Modify: `descargador/resolvers/base.py`
- Modify: `descargador/resolvers/mediafire.py`
- Modify: `descargador/browser.py`
- Modify: `descargador/engine.py:23-66` (`process_one`)
- Modify: `tests/test_engine.py` (update `test_process_one_captcha_usa_browser`, add new test)
- Test: `tests/test_browser.py` (new)

**Interfaces:**
- Produces: `Resolver.extract_from_page(self, page, destino) -> str | None` (contract change — `None` means "saved to `destino` myself"). `resolve_with_browser(page_url, extract_from_page, destino) -> str | None` (adds `destino`, passes it through). `Engine.process_one` now computes `destino` before the `NeedsBrowser` handling and short-circuits to `"completo"` when `browser_resolve` returns `None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_engine.py`, change the existing `browser_resolve` stub inside `test_process_one_captcha_usa_browser` from:

```python
    def browser_resolve(page_url, extract_from_page):
        usados["page_url"] = page_url
        return "http://directo-via-browser/x.rar"
```

to:

```python
    def browser_resolve(page_url, extract_from_page, destino):
        usados["page_url"] = page_url
        usados["destino"] = destino
        return "http://directo-via-browser/x.rar"
```

and add an assertion after the existing ones in that test:

```python
    assert usados["destino"] == str(tmp_path / "a.rar")
```

Then add a new test to the same file:

```python
def test_process_one_browser_resolve_none_marca_completo_sin_download_fn(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path))
    llamadas = {"download_fn": 0}

    def browser_resolve(page_url, extract_from_page, destino):
        return None

    def download_fn(**k):
        llamadas["download_fn"] += 1
        return (True, 1, 1, "completo")

    eng = Engine(
        get_resolver=lambda u: ResolverCaptcha(),
        download_fn=download_fn,
        browser_resolve=browser_resolve,
    )
    motivo = eng.process_one(item)
    assert motivo == "completo"
    assert item.estado == "completo"
    assert llamadas["download_fn"] == 0
```

Create `tests/test_browser.py`:

```python
import playwright.sync_api

from descargador.browser import resolve_with_browser


def test_resolve_with_browser_pasa_destino_a_extract_from_page(monkeypatch):
    llamadas = {}

    class FakePage:
        def goto(self, url):
            llamadas["goto"] = url

    class FakeBrowser:
        def new_page(self):
            return FakePage()

        def close(self):
            llamadas["closed"] = True

    class FakeChromium:
        def launch(self, headless=False):
            return FakeBrowser()

    class FakePlaywrightCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        chromium = FakeChromium()

    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: FakePlaywrightCtx())

    def extract_from_page(page, destino):
        llamadas["page"] = page
        llamadas["destino"] = destino
        return "resultado"

    resultado = resolve_with_browser("http://x/pagina", extract_from_page, "/tmp/destino.rar")

    assert resultado == "resultado"
    assert llamadas["goto"] == "http://x/pagina"
    assert llamadas["destino"] == "/tmp/destino.rar"
    assert isinstance(llamadas["page"], FakePage)
    assert llamadas["closed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py tests/test_browser.py -v`
Expected: FAIL — `test_process_one_captcha_usa_browser` fails with `TypeError: browser_resolve() takes 2 positional arguments but 3 were given` (today's `engine.py` still calls it with 2 args); `test_process_one_browser_resolve_none_marca_completo_sin_download_fn` fails because `download_fn` still gets called (`llamadas["download_fn"] == 1`, not `0`); `tests/test_browser.py` fails with `ModuleNotFoundError` or `ImportError` — no, it fails because `resolve_with_browser` doesn't accept a third `destino` argument yet.

- [ ] **Step 3: Implement**

In `descargador/resolvers/base.py`, replace the `extract_from_page` method:

```python
    def extract_from_page(self, page, destino):
        """Extrae el link directo desde una pagina Playwright ya cargada.

        Si el resolver necesita bajar el archivo el mismo (por ejemplo,
        porque las cookies de una verificacion no son reusables via urllib),
        guarda el archivo en destino y devuelve None en vez de una URL.
        """
        raise NotImplementedError
```

In `descargador/resolvers/mediafire.py`, change:

```python
    def extract_from_page(self, page):
```

to:

```python
    def extract_from_page(self, page, destino):
```

(body unchanged — `destino` is unused here, MediaFire always returns a URL).

Replace `descargador/browser.py` in full:

```python
def resolve_with_browser(page_url, extract_from_page, destino):
    """Abre un navegador visible para que el usuario resuelva el captcha.

    Navega a page_url, espera a que extract_from_page(page, destino) devuelva
    el link directo (tras la resolucion manual del captcha) o None (si el
    propio resolver ya guardo el archivo en destino), y lo retorna.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.goto(page_url)
            return extract_from_page(page, destino)
        finally:
            browser.close()
```

Replace `Engine.process_one` in `descargador/engine.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py tests/test_browser.py -v`
Expected: PASS — all tests in both files.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add descargador/resolvers/base.py descargador/resolvers/mediafire.py descargador/browser.py descargador/engine.py tests/test_engine.py tests/test_browser.py
git commit -m "feat: let a resolver's browser step own the download (extract_from_page gains destino)"
```

---

### Task 2: `MegaUpResolver`

**Files:**
- Create: `descargador/resolvers/megaup.py`
- Modify: `descargador/resolvers/__init__.py`
- Test: `tests/test_megaup.py` (new)

**Interfaces:**
- Consumes: `Resolver`, `NeedsBrowser` (`descargador.resolvers.base`, Task 1 signature).
- Produces: `MegaUpResolver` class, registered in `_RESOLVERS` so `get_resolver()` returns it for `megaup.net` URLs.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_megaup.py`:

```python
import pytest

from descargador.resolvers.base import NeedsBrowser
from descargador.resolvers.megaup import extract_direct, MegaUpResolver

HTML_CON_LINK = """
<script>
var seconds = 2;
function display() {
    if (seconds == 0) {
        $('.download-timer').html("<a class='btn btn--primary' href='https://download.megaup.net/?url=TOKEN_DE_PRUEBA_123'><span class='btn__text'>DOWNLOAD / VIEW NOW</span></a>");
    }
}
</script>
"""


def test_extract_direct_encuentra_link():
    assert extract_direct(HTML_CON_LINK) == "https://download.megaup.net/?url=TOKEN_DE_PRUEBA_123"


def test_extract_direct_sin_link_devuelve_none():
    assert extract_direct("<html><body>nada aca</body></html>") is None


def test_matches():
    r = MegaUpResolver()
    assert r.matches("https://megaup.net/abc123/Juego.part01.rar")
    assert not r.matches("https://mediafire.com/file/abc/x.rar/file")


def test_filename_ultimo_segmento():
    r = MegaUpResolver()
    url = "https://megaup.net/4c313c78a3315d00f90fe290806cf634/Juego.part07.rar"
    assert r.filename(url) == "Juego.part07.rar"


def test_resolve_encuentra_link_lanza_needsbrowser(monkeypatch):
    import descargador.resolvers.megaup as megaup_mod

    class FakeResp:
        def read(self):
            return HTML_CON_LINK.encode("utf-8")

    monkeypatch.setattr(megaup_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = MegaUpResolver()
    with pytest.raises(NeedsBrowser) as exc_info:
        r.resolve("https://megaup.net/abc123/Juego.part01.rar")
    assert exc_info.value.page_url == "https://download.megaup.net/?url=TOKEN_DE_PRUEBA_123"


def test_resolve_sin_link_lanza_excepcion_comun(monkeypatch):
    import descargador.resolvers.megaup as megaup_mod

    class FakeResp:
        def read(self):
            return b"<html>nada aca</html>"

    monkeypatch.setattr(megaup_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = MegaUpResolver()
    with pytest.raises(Exception) as exc_info:
        r.resolve("https://megaup.net/abc123/Juego.part01.rar")
    assert not isinstance(exc_info.value, NeedsBrowser)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_megaup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'descargador.resolvers.megaup'`.

- [ ] **Step 3: Implement**

Create `descargador/resolvers/megaup.py`:

```python
import re
import urllib.request

from .base import NeedsBrowser, Resolver

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_DIRECT = re.compile(r"href='(https://download\.megaup\.net/\?url=[^']+)'")


def extract_direct(html):
    m = _DIRECT.search(html)
    return m.group(1) if m else None


class MegaUpResolver(Resolver):
    def matches(self, url):
        return "megaup.net" in url

    def filename(self, url):
        return url.rstrip("/").split("/")[-1]

    def resolve(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        directo = extract_direct(html)
        if not directo:
            raise RuntimeError("no se encontro el link directo de megaup.net")
        raise NeedsBrowser(directo)

    def extract_from_page(self, page, destino):
        # download.megaup.net esta detras de un Cloudflare Turnstile
        # interactivo: esperamos a que la persona clickee el check y el
        # navegador dispare su descarga nativa, y la guardamos nosotros.
        with page.expect_download(timeout=300000) as download_info:
            pass
        download = download_info.value
        download.save_as(destino)
        return None
```

Update `descargador/resolvers/__init__.py`:

```python
from .mediafire import MediaFireResolver
from .megaup import MegaUpResolver

_RESOLVERS = [MediaFireResolver(), MegaUpResolver()]


def get_resolver(url):
    for r in _RESOLVERS:
        if r.matches(url):
            return r
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_megaup.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add descargador/resolvers/megaup.py descargador/resolvers/__init__.py tests/test_megaup.py
git commit -m "feat: add megaup.net resolver"
```

---

### Task 3: Verification

No code changes.

- [ ] **Step 1: Run full test suite one more time**

Run: `python -m pytest -q`
Expected: all tests pass (original suite + Tasks 1-2 additions).

- [ ] **Step 2: Live network smoke check of `resolve()` (no browser, read-only)**

Run a short script confirming `MegaUpResolver().resolve(<a real megaup.net url>)` still raises `NeedsBrowser` with a `page_url` starting with `https://download.megaup.net/?url=` against the live site today (catches "the site changed its HTML since the design spec was written" before it becomes a confusing runtime bug report).

- [ ] **Step 3: Note what still needs a human, and who does it**

The full browser-download path (Cloudflare checkbox click → native browser download → `save_as`) cannot be verified by an agent — it requires an actual person clicking the Turnstile checkbox in the visible browser window `resolve_with_browser` opens. This step is NOT run as part of this plan. Tell the user: next time a `megaup.net` mirror is retried from the real app, a browser window will open on `download.megaup.net`; click the "Verifique que es un ser humano" checkbox, and the file should start downloading and land in the configured `carpeta` under its `nombre`. Report back if it doesn't, with whatever the window showed.

No commit for this task (verification only).
