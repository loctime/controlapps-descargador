from descargador.links import parse_links, sort_by_part, group_key, agrupar


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


def test_parse_varios_links_en_una_misma_linea():
    texto = "https://a.com/1 https://a.com/2\thttps://a.com/3"
    assert parse_links(texto) == ["https://a.com/1", "https://a.com/2", "https://a.com/3"]


def test_parse_links_separados_por_coma_o_punto_y_coma():
    texto = "https://a.com/1, https://a.com/2;https://a.com/3"
    assert parse_links(texto) == ["https://a.com/1", "https://a.com/2", "https://a.com/3"]


def test_parse_links_con_texto_alrededor_y_saltos_windows():
    texto = "Parte 1: https://a.com/1\r\nParte 2: (https://a.com/2)\r\n"
    assert parse_links(texto) == ["https://a.com/1", "https://a.com/2"]


def test_parse_acepta_http_en_mayusculas():
    assert parse_links("HTTPS://A.com/1") == ["HTTPS://A.com/1"]
