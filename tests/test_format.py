from descargador.format import humano, bar, velocidad_ema


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


def test_velocidad_ema_primera_muestra():
    # sin EMA previa, devuelve la velocidad instantanea tal cual
    v = velocidad_ema(prev_ts=0, prev_bytes=0, prev_ema=None,
                       ts=1.0, bytes_bajados=1000)
    assert v == 1000


def test_velocidad_ema_suaviza_hacia_la_instantanea():
    # con EMA previa baja y una instantanea alta, el resultado queda entre medio
    v = velocidad_ema(prev_ts=0, prev_bytes=0, prev_ema=100,
                       ts=1.0, bytes_bajados=1000)
    assert 100 < v < 1000


def test_velocidad_ema_dt_chico_no_actualiza():
    # updates casi simultaneos (descarga segmentada) no deben generar picos
    v = velocidad_ema(prev_ts=10.0, prev_bytes=500, prev_ema=250,
                       ts=10.01, bytes_bajados=600)
    assert v == 250
