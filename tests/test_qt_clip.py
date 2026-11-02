from descargador.qt_app import DescargadorQt
from descargador.state import State


class _VentanaFalsa:
    def __init__(self, tmp_path, modo):
        self.carpeta = str(tmp_path)
        self.modo = modo
        self.state = State(str(tmp_path / "estado.json"))
        self.refresco = 0

    def _refresh(self):
        self.refresco += 1


def test_recorte_conserva_el_modo_audio_elegido(tmp_path):
    ventana = _VentanaFalsa(tmp_path, "mp3")

    DescargadorQt.add_clip(ventana, "https://www.youtube.com/watch?v=abc", 10, 25)

    item = ventana.state.items[0]
    assert item.clip == {"inicio": 10, "fin": 25}
    assert item.audio_format == "mp3"
    assert ventana.refresco == 1


def test_parse_tiempo_acepta_segundos_mmss_y_hhmmss():
    from descargador.app import _parse_tiempo
    assert _parse_tiempo("90") == 90
    assert _parse_tiempo("10:00") == 600
    assert _parse_tiempo(" 1:02:03 ") == 3723
    assert _parse_tiempo("") is None
    assert _parse_tiempo("abc") is None
    assert _parse_tiempo("1:2:3:4") is None
    assert _parse_tiempo("-5") is None


def test_preview_solo_se_recodifica_si_no_es_h264_aac_mp4():
    from descargador.qt_app import _preview_es_compatible
    assert _preview_es_compatible({"vcodec": "avc1.64001f", "acodec": "mp4a.40.2"}, "p.mp4")
    assert _preview_es_compatible({"vcodec": "avc1.64001f", "acodec": "none"}, "p.mp4")
    assert not _preview_es_compatible({"vcodec": "vp09.00.40.08", "acodec": "mp4a.40.2"}, "p.mp4")
    assert not _preview_es_compatible({"vcodec": "avc1.64001f", "acodec": "opus"}, "p.mp4")
    assert not _preview_es_compatible({"vcodec": "avc1.64001f", "acodec": "mp4a.40.2"}, "p.mkv")
    assert not _preview_es_compatible({}, "p.mp4")
