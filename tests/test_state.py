import json
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
