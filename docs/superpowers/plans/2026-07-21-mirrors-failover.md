# Mirrors por item con failover automático — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a queue item hold multiple candidate URLs (mirrors) for the same file; when the URL in use fails, automatically try the next one in the same pass before marking the item "fallido".

**Architecture:** `Item` gets a `mirrors: list[str]` field (default `[]`, backward-compatible with existing `state.json`). `State.add()` merges a newly-pasted URL into an existing item's `mirrors` when it matches an existing item's `(nombre, carpeta)`, instead of creating a duplicate row. `Engine.process_one` loops over `[item.url] + item.mirrors`, trying each candidate until one completes, pauses (disk-full/user-pause), or all are exhausted.

**Tech Stack:** Python stdlib (`dataclasses`), `pytest`. No new dependencies.

## Global Constraints

- `Item.mirrors` defaults to `[]` via `field(default_factory=list)` — old `state.json` files (no `"mirrors"` key) must load without migration.
- Merge key for `State.add()` is `(nombre, carpeta)` — not `nombre` alone (spec: avoid merging same-named files destined for different folders).
- `"pausado"` and `"disco_lleno"` are not per-candidate failures — they must stop the failover loop immediately, not trigger the next mirror.
- `process_one` must return `"sin_resolver"` only when every candidate cleanly had no resolver (`get_resolver` returned `None`); any candidate that got a resolver and then failed (exception or download `"error"`) makes the final return `"error"` instead — this preserves the existing distinction the test suite already relies on.
- This plan does not touch `download.py`, and does not add resolvers for any new host (separate, later plans).

---

### Task 1: `Item.mirrors` + merge-on-add

**Files:**
- Modify: `descargador/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces: `Item.mirrors: list[str]` (new field, default `[]`). `State.add(url, nombre, carpeta) -> Item | None` — same signature as today, but now returns the existing item (with `url` appended to its `mirrors`) instead of `None` when it matches an existing item's `(nombre, carpeta)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_state.py` (add `import json` to the existing `import os` line at the top):

```python
def test_add_mergea_como_mirror_por_nombre_y_carpeta(tmp_path):
    st = State(str(tmp_path / "estado.json"))
    original = st.add("https://mediafire.com/a", "Juego.part01.rar", str(tmp_path))

    resultado = st.add("https://megaup.net/b", "Juego.part01.rar", str(tmp_path))

    assert resultado is original
    assert len(st.items) == 1
    assert original.mirrors == ["https://megaup.net/b"]


def test_add_no_duplica_mirror_ya_agregado(tmp_path):
    st = State(str(tmp_path / "estado.json"))
    original = st.add("https://mediafire.com/a", "Juego.part01.rar", str(tmp_path))
    st.add("https://megaup.net/b", "Juego.part01.rar", str(tmp_path))

    assert st.add("https://megaup.net/b", "Juego.part01.rar", str(tmp_path)) is None
    assert original.mirrors == ["https://megaup.net/b"]


def test_add_no_mergea_si_carpeta_distinta(tmp_path):
    st = State(str(tmp_path / "estado.json"))
    st.add("https://mediafire.com/a", "Juego.part01.rar", str(tmp_path / "carpetaA"))
    st.add("https://megaup.net/b", "Juego.part01.rar", str(tmp_path / "carpetaB"))

    assert len(st.items) == 2


def test_save_y_load_roundtrip_con_mirrors(tmp_path):
    ruta = str(tmp_path / "estado.json")
    st = State(ruta)
    st.add("https://mediafire.com/a", "Juego.part01.rar", str(tmp_path))
    st.add("https://megaup.net/b", "Juego.part01.rar", str(tmp_path))
    st.save()

    st2 = State(ruta)
    items = st2.load()
    assert items[0].mirrors == ["https://megaup.net/b"]


def test_load_estado_viejo_sin_mirrors(tmp_path):
    ruta = str(tmp_path / "estado.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump([{"url": "https://x/a", "nombre": "a.rar", "estado": "completo",
                    "bytes_bajados": 1, "total": 1, "carpeta": "c"}], f)

    st = State(ruta)
    items = st.load()

    assert items[0].mirrors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL — `TypeError: Item.__init__() got an unexpected keyword argument` is NOT what happens (mirrors doesn't exist yet so nothing passes it at construction); instead `test_add_mergea_como_mirror_por_nombre_y_carpeta` fails with `AssertionError` (merge doesn't happen, `len(st.items) == 2`) and `test_load_estado_viejo_sin_mirrors` fails with `AttributeError: 'Item' object has no attribute 'mirrors'`.

- [ ] **Step 3: Implement**

In `descargador/state.py`, change the import line:

```python
from dataclasses import dataclass, asdict
```

to:

```python
from dataclasses import dataclass, asdict, field
```

Change the `Item` dataclass:

```python
@dataclass
class Item:
    url: str
    nombre: str
    estado: str = "pendiente"
    bytes_bajados: int = 0
    total: int = 0
    carpeta: str = ""
    mirrors: list = field(default_factory=list)
```

Replace `State.add`:

```python
    def add(self, url, nombre, carpeta):
        if any(url == it.url or url in it.mirrors for it in self.items):
            return None
        for it in self.items:
            if it.nombre == nombre and it.carpeta == carpeta:
                it.mirrors.append(url)
                return it
        item = Item(url=url, nombre=nombre, carpeta=carpeta)
        self.items.append(item)
        return item
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_state.py -v`
Expected: PASS (all tests in the file, old and new).

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `python -m pytest -q`
Expected: all pass. Note: `Engine` still does single-candidate resolution at this point (fixed in Task 2) — `item.mirrors` existing but unused by `Engine` is fine, no other code reads it yet.

- [ ] **Step 6: Commit**

```bash
git add descargador/state.py tests/test_state.py
git commit -m "feat: merge same-file links into mirrors instead of duplicate items"
```

---

### Task 2: Failover loop in `Engine.process_one`

**Files:**
- Modify: `descargador/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `Item.mirrors` (Task 1).
- Produces: no new public interface — `Engine.process_one(item) -> str` keeps its signature and existing return vocabulary (`"completo"`, `"pausado"`, `"disco_lleno"`, `"error"`, `"sin_resolver"`), but now tries `[item.url] + item.mirrors` before settling on a terminal reason.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine.py`:

```python
def test_process_one_failover_primer_mirror_explota_segundo_completa(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path),
                mirrors=["http://y/a.rar/file"])

    def get_resolver(url):
        if url == item.url:
            raise RuntimeError("boom")
        return ResolverOK()

    eng = Engine(
        get_resolver=get_resolver,
        download_fn=lambda direct, destino, on_progress, should_pause, conexiones=None: (True, 100, 100, "completo"),
    )
    motivo = eng.process_one(item)
    assert motivo == "completo"
    assert item.estado == "completo"


def test_process_one_failover_todos_los_candidatos_fallan(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path),
                mirrors=["http://y/a.rar/file"])

    def get_resolver(url):
        return None if url == item.url else ResolverOK()

    eng = Engine(
        get_resolver=get_resolver,
        download_fn=lambda direct, destino, on_progress, should_pause, conexiones=None: (False, 0, 0, "error"),
    )
    motivo = eng.process_one(item)
    assert motivo == "error"
    assert item.estado == "fallido"


def test_process_one_pausado_no_prueba_siguiente_mirror(tmp_path):
    item = Item(url="http://x/a.rar/file", nombre="a.rar", carpeta=str(tmp_path),
                mirrors=["http://y/a.rar/file"])
    intentos = []

    def get_resolver(url):
        intentos.append(url)
        return ResolverOK()

    eng = Engine(
        get_resolver=get_resolver,
        download_fn=lambda direct, destino, on_progress, should_pause, conexiones=None: (False, 10, 100, "pausado"),
    )
    motivo = eng.process_one(item)
    assert motivo == "pausado"
    assert item.estado == "pausado"
    assert intentos == ["http://x/a.rar/file"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -v -k failover_or_pausado_no_prueba`
Expected: FAIL — with today's single-candidate `process_one`, the first test never reaches the second (working) mirror (`get_resolver` raises immediately and nothing catches it at that point the way the new design requires... today's code DOES wrap the whole body in `try/except Exception`, so today it would actually return `"error"` without ever trying `item.mirrors`, since `mirrors` isn't consulted at all yet). Concretely: FAIL on `assert motivo == "completo"` (today returns `"error"`, `mirrors` is never read).

- [ ] **Step 3: Implement**

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

                try:
                    direct = resolver.resolve(candidato)
                except NeedsBrowser as e:
                    direct = self.browser_resolve(e.page_url, resolver.extract_from_page)

                destino = os.path.join(item.carpeta, item.nombre)
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

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS — all tests in the file, old (5 pre-existing) and new (3 added).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add descargador/engine.py tests/test_engine.py
git commit -m "feat: automatic mirror failover in Engine.process_one"
```

---

### Task 3: End-to-end sanity check

No code changes. Confirms Tasks 1-2 compose correctly.

- [ ] **Step 1: Run full test suite one more time**

Run: `python -m pytest -q`
Expected: all tests pass (original suite + Tasks 1-2 additions).

- [ ] **Step 2: Manual check with the real app (read-only, no destructive action on real state)**

Run: `python run.py`. With `~/.descargador/estado.json` loaded (real GTA V + Sleeping Dogs data), confirm:
- App still opens and renders the grouped tree exactly as before (mirrors is inert with today's single-URL items — no visible change expected).
- Do NOT click "Reintentar fallidos" against the real Sleeping Dogs items in this check — mirror-based recovery for those specific items depends on Tasks from the separate `2026-07-21-mirrors-failover-design.md` follow-ups (resolvers for `megaup.net`/`rootz.so`), which don't exist yet; retrying now would just re-fail them the same way as before, no regression but no fix either.

No commit for this task (verification only).
