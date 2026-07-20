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
