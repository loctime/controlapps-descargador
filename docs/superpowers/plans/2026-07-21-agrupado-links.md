# Agrupado de links por release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the download queue table by release (derived from filename), let the user collapse/expand groups individually or all at once, and delete a whole group's links in one action.

**Architecture:** Grouping is computed on the fly from `Item.nombre` — no schema or persistence changes. `descargador/links.py` gets two pure functions (`group_key`, `agrupar`) that are fully unit-testable without Tkinter. `descargador/app.py`'s `ttk.Treeview` becomes two-level (group parent nodes + item child nodes); `_refrescar_tabla` rebuilds the whole tree from `self.state.items` on every change and preserves each group's open/closed state across rebuilds by reading it back from the tree before deleting.

**Tech Stack:** Python stdlib (`re`, `tkinter`/`ttk`), `pytest`. No new dependencies.

## Global Constraints

- No changes to `Item` dataclass or `state.json` schema (spec: "Sin cambios al schema de `Item`/`state.json`").
- Collapse/expand state is NOT persisted across app restarts — always starts expanded (spec: "Fuera de alcance").
- Groups are ordered by first appearance in `self.state.items`, not alphabetically (spec: "Fuera de alcance").
- Reuse the existing `_PART` regex from `links.py` for `group_key` — do not introduce a second pattern.
- Tests for `app.py` must patch `ESTADO`/`CONFIG` to a `tmp_path` before constructing `App` — never touch the real `~/.descargador/estado.json` (it holds the user's live download queue).

---

### Task 1: Grouping logic (`group_key`, `agrupar`)

**Files:**
- Modify: `descargador/links.py`
- Test: `tests/test_links.py`

**Interfaces:**
- Produces: `group_key(nombre: str) -> str` — release key derived from a filename.
- Produces: `agrupar(items: list) -> list[tuple[str, list]]` — items grouped by `group_key(it.nombre)`, preserving order of first appearance. `items` elements only need a `.nombre` attribute (duck-typed; used with `descargador.state.Item` elsewhere).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_links.py` (keep existing imports/tests, extend the import line and append these tests):

```python
from descargador.links import parse_links, sort_by_part, group_key, agrupar


def test_group_key_con_part():
    assert group_key("Juego-3717-elamigos.part03.rar") == "Juego-3717-elamigos"


def test_group_key_con_part_mayusculas():
    assert group_key("Juego.PART03.rar") == "Juego"


def test_group_key_sin_part_devuelve_nombre_completo():
    assert group_key("archivo-suelto.zip") == "archivo-suelto.zip"


def test_group_key_recorta_separadores_colgantes():
    assert group_key("Juego_part01.rar") == "Juego"
    assert group_key("Juego-part01.rar") == "Juego"
    assert group_key("Juego part01.rar") == "Juego"


def test_agrupar_preserva_orden_de_aparicion():
    class Falso:
        def __init__(self, nombre):
            self.nombre = nombre

    items = [
        Falso("B.part01.rar"),
        Falso("A.part01.rar"),
        Falso("B.part02.rar"),
        Falso("suelto.zip"),
    ]
    grupos = agrupar(items)
    assert [k for k, _ in grupos] == ["B", "A", "suelto.zip"]
    assert [it.nombre for it in grupos[0][1]] == ["B.part01.rar", "B.part02.rar"]
    assert [it.nombre for it in grupos[1][1]] == ["A.part01.rar"]
    assert [it.nombre for it in grupos[2][1]] == ["suelto.zip"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_links.py -v`
Expected: FAIL — `ImportError: cannot import name 'group_key'` (or `agrupar`).

- [ ] **Step 3: Implement `group_key` and `agrupar`**

In `descargador/links.py`, append after `sort_by_part`:

```python
def group_key(nombre):
    m = _PART.search(nombre)
    key = nombre[:m.start()] if m else nombre
    return key.rstrip(" .-_")


def agrupar(items):
    """Agrupa items por group_key(it.nombre), preservando el orden de
    primera aparicion. Devuelve lista de tuplas (key, [items])."""
    grupos = {}
    orden = []
    for it in items:
        k = group_key(it.nombre)
        if k not in grupos:
            grupos[k] = []
            orden.append(k)
        grupos[k].append(it)
    return [(k, grupos[k]) for k in orden]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_links.py -v`
Expected: PASS (all tests in the file, old and new).

- [ ] **Step 5: Commit**

```bash
git add descargador/links.py tests/test_links.py
git commit -m "feat: add group_key/agrupar for grouping links by release"
```

---

### Task 2: Grouped Treeview render

**Files:**
- Modify: `descargador/app.py:14` (import), `descargador/app.py:23-24` (constants), `descargador/app.py:56` (`__init__`), `descargador/app.py:208-233` (`_fila`, `_refrescar_tabla`)
- Test: `tests/test_app.py` (new)

**Interfaces:**
- Consumes: `agrupar` from Task 1 (`descargador.links.agrupar`).
- Produces: `App._todo_abierto: bool` instance attribute (default `True`) — read by later tasks. `App` Treeview node id scheme: group nodes use iid `"grp:" + key`; item nodes keep iid `it.url` (unchanged).

- [ ] **Step 1: Write the failing test**

Create `tests/test_app.py`:

```python
import tkinter as tk

import pytest

import descargador.app as appmod
from descargador.state import Item


@pytest.fixture(scope="session")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tmp_path, monkeypatch, tk_root):
    monkeypatch.setattr(appmod, "ESTADO", str(tmp_path / "estado.json"))
    monkeypatch.setattr(appmod, "CONFIG", str(tmp_path / "config.json"))
    a = appmod.App(tk_root)
    yield a
    for w in tk_root.winfo_children():
        w.destroy()


def test_refrescar_tabla_agrupa_por_release(app, tmp_path):
    app.state.items = [
        Item(url="http://x/1", nombre="Juego.part01.rar", estado="completo",
             bytes_bajados=100, total=100, carpeta=str(tmp_path)),
        Item(url="http://x/2", nombre="Juego.part02.rar", estado="pendiente",
             bytes_bajados=0, total=100, carpeta=str(tmp_path)),
        Item(url="http://x/3", nombre="Suelto.rar", estado="pendiente",
             bytes_bajados=0, total=0, carpeta=str(tmp_path)),
    ]

    app._refrescar_tabla()

    assert app.tree.get_children("") == ("grp:Juego", "grp:Suelto.rar")
    assert app.tree.get_children("grp:Juego") == ("http://x/1", "http://x/2")
    assert app.tree.get_children("grp:Suelto.rar") == ("http://x/3",)
    assert app.tree.item("grp:Juego", "values")[0] == "Juego  (1/2 completos)"


def test_refrescar_tabla_preserva_colapso_entre_rebuilds(app, tmp_path):
    app.state.items = [
        Item(url="http://x/1", nombre="Juego.part01.rar", carpeta=str(tmp_path)),
    ]
    app._refrescar_tabla()
    app.tree.item("grp:Juego", open=False)

    app._refrescar_tabla()

    assert not app.tree.item("grp:Juego", "open")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL — `AssertionError` (tree is still flat, no `"grp:Juego"` node exists) or `AttributeError` if `agrupar` isn't imported yet.

- [ ] **Step 3: Implement the grouped render**

In `descargador/app.py`, change line 14 from:

```python
from .links import parse_links, sort_by_part
```

to:

```python
from .links import parse_links, sort_by_part, agrupar
```

After line 24 (`CONEXIONES_DEFAULT = 4`), add:

```python
GRP_PREFIX = "grp:"
```

In `__init__`, after line 56 (`self.worker = None`), add:

```python
        self._todo_abierto = True
```

Replace the `_fila` method (lines 208-214) with:

```python
    def _fila(self, it):
        pct = int(it.bytes_bajados * 100 / it.total) if it.total else 0
        prog = f"{bar(pct)} {pct}%"
        vel = self._vel.get(it.url, {}).get("ema") if it.estado == "descargando" else None
        if vel:
            prog += f" · {humano(vel)}/s"
        return (it.nombre, humano(it.total) if it.total else "?",
                prog, it.estado)
```

Replace the `_refrescar_tabla` method (lines 230-233) with:

```python
    def _refrescar_tabla(self):
        abiertos = {iid: self.tree.item(iid, "open") for iid in self.tree.get_children("")}
        self.tree.delete(*self.tree.get_children())
        for key, items in agrupar(self.state.items):
            gid = GRP_PREFIX + key
            completos = sum(1 for it in items if it.estado == "completo")
            tam_grupo = sum(it.total for it in items if it.total)
            texto = f"{key}  ({completos}/{len(items)} completos)"
            self.tree.insert("", "end", iid=gid,
                              values=(texto, humano(tam_grupo) if tam_grupo else "?", "", ""),
                              open=abiertos.get(gid, self._todo_abierto))
            for it in items:
                self.tree.insert(gid, "end", iid=it.url, values=self._fila(it))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `python -m pytest -q`
Expected: all tests pass (existing suite + new ones). Note: `_drenar_cola` still references the old flat-tree update logic at this point and is fixed in Task 3 — it isn't exercised by these tests yet.

- [ ] **Step 6: Commit**

```bash
git add descargador/app.py tests/test_app.py
git commit -m "feat: render download queue as grouped tree by release"
```

---

### Task 3: Keep group aggregates live during downloads

**Files:**
- Modify: `descargador/app.py:235-248` (`_drenar_cola`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `App._refrescar_tabla()`, `App._actualizar_velocidad(it)` (both pre-existing/Task 2).
- Produces: no new public interface — `_drenar_cola` behavior changes from per-row incremental update to full-tree rebuild on each drained batch, so group totals (`X/N completos`, size) stay correct as items complete.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_drenar_cola_actualiza_agregado_del_grupo(app, tmp_path):
    it1 = Item(url="http://x/1", nombre="Juego.part01.rar", estado="descargando",
               bytes_bajados=0, total=100, carpeta=str(tmp_path))
    it2 = Item(url="http://x/2", nombre="Juego.part02.rar", estado="pendiente",
               total=100, carpeta=str(tmp_path))
    app.state.items = [it1, it2]
    app._refrescar_tabla()
    assert app.tree.item("grp:Juego", "values")[0] == "Juego  (0/2 completos)"

    it1.estado = "completo"
    it1.bytes_bajados = 100
    app.cola_ui.put(it1)

    app._drenar_cola()

    assert app.tree.item("grp:Juego", "values")[0] == "Juego  (1/2 completos)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py -v -k drenar_cola`
Expected: FAIL — group text still reads `"Juego  (0/2 completos)"` because `_drenar_cola` only patches the child row, not the parent group.

- [ ] **Step 3: Implement**

Replace the `_drenar_cola` method (lines 235-248) with:

```python
    def _drenar_cola(self):
        cambiado = False
        try:
            while True:
                it = self.cola_ui.get_nowait()
                self._actualizar_velocidad(it)
                cambiado = True
        except queue.Empty:
            pass
        if cambiado:
            self._refrescar_tabla()
            self.state.save()
        self.root.after(200, self._drenar_cola)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app.py -v -k drenar_cola`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add descargador/app.py tests/test_app.py
git commit -m "fix: refresh whole tree on queue drain so group totals stay accurate"
```

---

### Task 4: Delete a whole group

**Files:**
- Modify: `descargador/app.py:175-193` (`_quitar_seleccionados`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `GRP_PREFIX` (Task 2), `self.tree.get_children(gid)` (child iids == item urls, from Task 2's render).
- Produces: no new public interface — `_quitar_seleccionados` now accepts group iids in `self.tree.selection()`, not just item urls.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py`:

```python
def test_quitar_seleccionados_borra_grupo_entero(app, tmp_path):
    app.state.items = [
        Item(url="http://x/1", nombre="Juego.part01.rar", estado="completo", carpeta=str(tmp_path)),
        Item(url="http://x/2", nombre="Juego.part02.rar", estado="pendiente", carpeta=str(tmp_path)),
        Item(url="http://x/3", nombre="Otro.rar", estado="pendiente", carpeta=str(tmp_path)),
    ]
    app._refrescar_tabla()
    app.tree.selection_set("grp:Juego")

    app._quitar_seleccionados()

    assert {it.url for it in app.state.items} == {"http://x/3"}


def test_quitar_grupo_con_descarga_activa_preserva_ese_item(app, tmp_path, monkeypatch):
    monkeypatch.setattr(appmod.messagebox, "showwarning", lambda *a, **k: None)
    app.state.items = [
        Item(url="http://x/1", nombre="Juego.part01.rar", estado="descargando", carpeta=str(tmp_path)),
        Item(url="http://x/2", nombre="Juego.part02.rar", estado="pendiente", carpeta=str(tmp_path)),
    ]
    app._refrescar_tabla()
    app.tree.selection_set("grp:Juego")

    app._quitar_seleccionados()

    assert {it.url for it in app.state.items} == {"http://x/1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_app.py -v -k quitar`
Expected: FAIL — `_quitar_seleccionados` currently treats `"grp:Juego"` as a literal url, so `urls = {"grp:Juego"}` never matches any real item and nothing gets removed.

- [ ] **Step 3: Implement**

Replace the `_quitar_seleccionados` method (lines 175-193) with:

```python
    def _quitar_seleccionados(self):
        sel = self.tree.selection()
        if not sel:
            return
        urls = set()
        for iid in sel:
            if iid.startswith(GRP_PREFIX):
                urls.update(self.tree.get_children(iid))
            else:
                urls.add(iid)
        activos = [it.url for it in self.state.items
                   if it.url in urls and it.estado == "descargando"]
        if activos:
            messagebox.showwarning(
                "Descarga en curso",
                "Pausa la descarga antes de quitar el archivo que se esta bajando.")
            urls -= set(activos)
            if not urls:
                return
        # Mutamos la lista in place (no reasignar) para que el worker en curso
        # vea la baja via la referencia que ya tiene.
        self.state.items[:] = [it for it in self.state.items if it.url not in urls]
        self.state.save()
        self._refrescar_tabla()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_app.py -v -k quitar`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add descargador/app.py tests/test_app.py
git commit -m "feat: deleting a selected group removes all its links"
```

---

### Task 5: "Colapsar todo / Expandir todo" button

**Files:**
- Modify: `descargador/app.py:99-105` (bottom button bar)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `App._todo_abierto` (Task 2), `App.tree` group nodes (iid prefix `GRP_PREFIX`).
- Produces: `App.btn_colapsar: ttk.Button`, `App._toggle_colapso() -> None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_toggle_colapso_afecta_todos_los_grupos(app, tmp_path):
    app.state.items = [
        Item(url="http://x/1", nombre="A.part01.rar", carpeta=str(tmp_path)),
        Item(url="http://x/2", nombre="B.part01.rar", carpeta=str(tmp_path)),
    ]
    app._refrescar_tabla()
    assert app.btn_colapsar.cget("text") == "Colapsar todo"

    app._toggle_colapso()
    assert all(not app.tree.item(g, "open") for g in app.tree.get_children(""))
    assert app.btn_colapsar.cget("text") == "Expandir todo"

    app._toggle_colapso()
    assert all(app.tree.item(g, "open") for g in app.tree.get_children(""))
    assert app.btn_colapsar.cget("text") == "Colapsar todo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py -v -k toggle_colapso`
Expected: FAIL — `AttributeError: 'App' object has no attribute 'btn_colapsar'`

- [ ] **Step 3: Implement**

In `descargador/app.py`, after line 105 (`ttk.Button(bottom, text="Abrir carpeta", command=self._abrir_carpeta).pack(side="left", padx=6)`), add:

```python
        self.btn_colapsar = ttk.Button(bottom, text="Colapsar todo", command=self._toggle_colapso)
        self.btn_colapsar.pack(side="left", padx=6)
```

Add a new method (near `_quitar_seleccionados`, e.g. directly after it):

```python
    def _toggle_colapso(self):
        self._todo_abierto = not self._todo_abierto
        for g in self.tree.get_children(""):
            self.tree.item(g, open=self._todo_abierto)
        self.btn_colapsar.config(text="Colapsar todo" if self._todo_abierto else "Expandir todo")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app.py -v -k toggle_colapso`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add descargador/app.py tests/test_app.py
git commit -m "feat: add collapse-all/expand-all button for groups"
```

---

### Task 6: End-to-end sanity check

No code changes. This confirms the five tasks above compose correctly in the real app (automated tests use a headless `Tk` root; this step checks the actual windowed UI once).

- [ ] **Step 1: Run full test suite one more time**

Run: `python -m pytest -q`
Expected: all tests pass (original suite + Tasks 1-5 additions).

- [ ] **Step 2: Launch the app**

Run: `python run.py`

- [ ] **Step 3: Manual checklist**

- Existing `~/.descargador/estado.json` (GTA V + Sleeping Dogs items) renders as two collapsible groups instead of one flat list.
- Each group header shows `"<nombre>  (X/N completos)"` matching the real completed/total counts.
- Clicking a group's triangle collapses/expands just that group.
- "Colapsar todo" collapses every group and its label flips to "Expandir todo"; clicking again reopens all and flips back.
- Selecting a group row and pressing Delete (or "Quitar") removes every link in that group from the table and from `estado.json`.
- Selecting a group row that contains an item with estado "descargando" and deleting shows the existing "Descarga en curso" warning and leaves that one item in place.

No commit for this task (verification only).
