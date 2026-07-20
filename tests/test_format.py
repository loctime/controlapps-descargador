from descargador.format import humano, bar


def test_humano_bytes():
    assert humano(500) == "500.0B"


def test_humano_mega():
    assert humano(1024 * 1024 * 2) == "2.0MB"


def test_bar_medio():
    assert bar(60, 10) == "██████░░░░"


def test_bar_cero():
    assert bar(0, 5) == "░░░░░"


def test_bar_lleno():
    assert bar(100, 5) == "█████"
