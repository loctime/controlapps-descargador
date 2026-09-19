from unittest.mock import MagicMock

from descargador.qt_app import DescargadorQt
from descargador.state import State

MEDIAFIRE = "https://www.mediafire.com/file/abc/Juego.part01.rar/file"
YOUTUBE = "https://www.youtube.com/watch?v=abc123"
DESCONOCIDO = "https://ejemplo-desconocido.com/x"


class _VentanaFalsa:
    def __init__(self, texto, modo="video", tmp_path=None):
        self.urls = MagicMock()
        self.urls.toPlainText.return_value = texto
        self.mode = MagicMock()
        self.crop_page = MagicMock()
        self._preview_url = None
        self._confirmed_url = None
        self.modo = modo
        self.carpeta = str(tmp_path) if tmp_path else ""
        self.state = State(str(tmp_path / "estado.json")) if tmp_path else None
        self.auto_iniciar = False
        self._refresh = MagicMock()

    _video_confirmed = DescargadorQt._video_confirmed


def test_archivo_no_muestra_miniatura_ni_modo():
    v = _VentanaFalsa(MEDIAFIRE)
    DescargadorQt._inspect_link(v)
    v.crop_page.show_thumbnail.assert_not_called()
    v.crop_page.hide_preview.assert_called_once()
    v.mode.hide.assert_called_once()


def test_video_muestra_miniatura_y_modo():
    v = _VentanaFalsa(f"{MEDIAFIRE}\n{YOUTUBE}")
    DescargadorQt._inspect_link(v)
    v.crop_page.show_thumbnail.assert_called_once_with(YOUTUBE, reveal=True)
    v.mode.setVisible.assert_called_with(True)


def test_desconocido_espera_confirmacion_de_ytdlp():
    v = _VentanaFalsa(DESCONOCIDO)
    DescargadorQt._inspect_link(v)
    v.crop_page.show_thumbnail.assert_called_once_with(DESCONOCIDO, reveal=False)
    v.mode.setVisible.assert_called_with(False)

    v._video_confirmed(DESCONOCIDO)
    v.mode.show.assert_called_once()
    v.crop_page.show.assert_called_once()


def test_confirmacion_de_un_link_viejo_se_ignora():
    v = _VentanaFalsa(DESCONOCIDO)
    DescargadorQt._inspect_link(v)
    v._video_confirmed("https://otro.com/y")
    v.mode.show.assert_not_called()


def test_texto_vacio_oculta_todo_y_permite_repegar_el_mismo_link():
    v = _VentanaFalsa(YOUTUBE)
    DescargadorQt._inspect_link(v)
    v.urls.toPlainText.return_value = ""
    DescargadorQt._inspect_link(v)
    v.mode.hide.assert_called()
    assert v._preview_url is None
    v.urls.toPlainText.return_value = YOUTUBE
    DescargadorQt._inspect_link(v)
    assert v.crop_page.show_thumbnail.call_count == 2


def test_archivo_no_hereda_el_modo_audio(tmp_path):
    v = _VentanaFalsa(f"{MEDIAFIRE}\n{YOUTUBE}", modo="mp3", tmp_path=tmp_path)
    DescargadorQt._add_urls(v)
    por_url = {it.url: it for it in v.state.items}
    assert por_url[MEDIAFIRE].audio_format == ""
    assert por_url[YOUTUBE].audio_format == "mp3"
