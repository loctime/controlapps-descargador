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
