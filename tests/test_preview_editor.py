from descargador.preview_editor import _tiempo


def test_tiempo_formatea_milisegundos():
    assert _tiempo(75_000) == "01:15"
    assert _tiempo(3_675_000) == "01:01:15"
