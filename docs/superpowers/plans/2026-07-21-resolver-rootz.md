# Resolver para rootz.so — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resolver for `rootz.so` links, closing out sub-project 3 of 3. Unlike MediaFire (captcha) and megaup.net (Cloudflare loop, dead end), this host's click-chain has no human-only gate, so the resolver drives it end-to-end automatically.

**Architecture:** `RootzResolver.filename()` reads the real filename from the page's server-rendered `<title>` tag via a plain HTTP GET (no browser). `resolve()` always raises `NeedsBrowser` — there's nothing extractable without JS. `extract_from_page(page, destino)` reuses the "browser owns the download, returns `None`" contract already built for megaup.net: click "Download", follow the popup through the ad chain, click "Download File" on the landing page, capture the native browser download, save it.

**Tech Stack:** Python stdlib (`re`, `urllib.request`), Playwright sync API (already a dependency), `pytest`.

## Global Constraints

- No CAPTCHA/Cloudflare-human-check exists anywhere in this host's chain (confirmed live) — do not add any human-wait step; this resolver is fully automated.
- Timeouts are 60 seconds per step (popup open, button click, download start) — much shorter than the 5-minute human-wait constant used for MediaFire/megaup.net, because nothing here is waiting on a person.
- Reuses the `Resolver.extract_from_page(page, destino) -> str | None` contract from `2026-07-21-resolver-megaup.md` — no changes to `base.py`, `browser.py`, or `engine.py` needed in this plan.
- `filename()` must have a fallback (last URL path segment) for when the `<title>` tag isn't found — same defensive pattern already used elsewhere when a resolver's primary extraction misses.

---

### Task 1: `RootzResolver` — `matches`, `filename`, `resolve`

**Files:**
- Create: `descargador/resolvers/rootz.py`
- Test: `tests/test_rootz.py` (new)

**Interfaces:**
- Produces: `RootzResolver` class with `matches(url)`, `filename(url)`, `resolve(url)` (raises `NeedsBrowser(url)` unconditionally), and `extract_title(html)` module-level helper.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rootz.py`:

```python
import pytest

from descargador.resolvers.base import NeedsBrowser
from descargador.resolvers.rootz import extract_title, RootzResolver

HTML_CON_TITLE = """
<html><head><title>Sle2epi6ngDo9g7sDe1fini4tiveE-Upd1-elamigos.part02.rar</title></head>
<body>contenido</body></html>
"""


def test_extract_title_encuentra_titulo():
    assert extract_title(HTML_CON_TITLE) == "Sle2epi6ngDo9g7sDe1fini4tiveE-Upd1-elamigos.part02.rar"


def test_extract_title_sin_titulo_devuelve_none():
    assert extract_title("<html><body>sin titulo aca</body></html>") is None


def test_matches():
    r = RootzResolver()
    assert r.matches("https://www.rootz.so/d/sG2Cm")
    assert not r.matches("https://mediafire.com/file/abc/x.rar/file")


def test_filename_usa_el_title(monkeypatch):
    import descargador.resolvers.rootz as rootz_mod

    class FakeResp:
        def read(self):
            return HTML_CON_TITLE.encode("utf-8")

    monkeypatch.setattr(rootz_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = RootzResolver()
    assert r.filename("https://www.rootz.so/d/sG2Cm") == "Sle2epi6ngDo9g7sDe1fini4tiveE-Upd1-elamigos.part02.rar"


def test_filename_fallback_sin_title(monkeypatch):
    import descargador.resolvers.rootz as rootz_mod

    class FakeResp:
        def read(self):
            return b"<html><body>nada</body></html>"

    monkeypatch.setattr(rootz_mod.urllib.request, "urlopen", lambda req, timeout=30: FakeResp())

    r = RootzResolver()
    assert r.filename("https://www.rootz.so/d/sG2Cm") == "sG2Cm"


def test_resolve_siempre_lanza_needsbrowser():
    r = RootzResolver()
    with pytest.raises(NeedsBrowser) as exc_info:
        r.resolve("https://www.rootz.so/d/sG2Cm")
    assert exc_info.value.page_url == "https://www.rootz.so/d/sG2Cm"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rootz.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'descargador.resolvers.rootz'`.

- [ ] **Step 3: Implement**

Create `descargador/resolvers/rootz.py`:

```python
import re
import urllib.request

from .base import NeedsBrowser, Resolver

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)


def extract_title(html):
    m = _TITLE.search(html)
    return m.group(1).strip() if m else None


class RootzResolver(Resolver):
    def matches(self, url):
        return "rootz.so" in url

    def filename(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        titulo = extract_title(html)
        return titulo if titulo else url.rstrip("/").split("/")[-1]

    def resolve(self, url):
        raise NeedsBrowser(url)
```

(`extract_from_page` is added in Task 2 — leaving it unimplemented here would make `RootzResolver` an incomplete `Resolver` subclass, but nothing in this task's tests calls it, so it's fine to add it next.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rootz.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add descargador/resolvers/rootz.py tests/test_rootz.py
git commit -m "feat: add rootz.so resolver (matches/filename/resolve)"
```

---

### Task 2: `extract_from_page` — the automated click chain, and registration

**Files:**
- Modify: `descargador/resolvers/rootz.py`
- Modify: `descargador/resolvers/__init__.py`

**Interfaces:**
- Produces: `RootzResolver.extract_from_page(page, destino) -> None`. `get_resolver()` returns `RootzResolver` for `rootz.so` URLs.

- [ ] **Step 1: Implement**

In `descargador/resolvers/rootz.py`, add to `RootzResolver`:

```python
    def extract_from_page(self, page, destino):
        # Sin captcha ni Cloudflare humano en esta cadena (confirmado en
        # vivo) - los dos clicks se scriptean de punta a punta.
        with page.expect_popup(timeout=60000) as popup_info:
            page.click("text=Download")
        popup = popup_info.value
        popup.wait_for_load_state()

        with popup.expect_download(timeout=60000) as download_info:
            popup.click("text=Download File", timeout=60000)
        download = download_info.value
        download.save_as(destino)
        popup.close()
        return None
```

Update `descargador/resolvers/__init__.py`:

```python
from .mediafire import MediaFireResolver
from .megaup import MegaUpResolver
from .rootz import RootzResolver

_RESOLVERS = [MediaFireResolver(), MegaUpResolver(), RootzResolver()]
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass (no new automated tests for `extract_from_page` in this task — per the design spec, the click-chain isn't unit-testable without a real browser, same stance already taken for `MediaFireResolver.extract_from_page`).

- [ ] **Step 3: Commit**

```bash
git add descargador/resolvers/rootz.py descargador/resolvers/__init__.py
git commit -m "feat: automate rootz.so's ad-chain click-through to capture the download"
```

---

### Task 3: Verification

No code changes.

- [ ] **Step 1: Run full test suite one more time**

Run: `python -m pytest -q`
Expected: all tests pass (original suite + Task 1 additions).

- [ ] **Step 2: Live network smoke check of `filename()` and `resolve()` (no browser, read-only)**

Run a short script confirming, against the real site today: `RootzResolver().filename(<a real rootz.so url>)` returns the real filename (not the URL-fallback), and `resolve()` raises `NeedsBrowser` with `page_url` equal to the input URL.

- [ ] **Step 3: Live check of the automated click chain (browser, no human needed)**

Because this resolver needs no human interaction, its full chain CAN be verified live, unlike megaup.net's. Run the two clicks against a real `rootz.so` file page and confirm a `download` event fires on the popup with a real (non-empty) URL — this alone confirms the chain works end-to-end. Do not necessarily wait for a multi-GB `save_as` to fully complete in this check; observing the `download` event firing with a valid URL is sufficient evidence, matching what was already established during the design investigation.

No commit for this task (verification only).
