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
