import os

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


def test_load_json_corrupto_no_crashea(tmp_path):
    ruta = str(tmp_path / "estado.json")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("{ esto no es json")

    st = State(ruta)
    items = st.load()

    assert items == []
    assert st.items == []
    assert os.path.exists(ruta + ".corrupto")
