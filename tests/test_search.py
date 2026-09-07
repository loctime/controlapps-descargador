from descargador.search import buscar_youtube


def test_buscar_youtube_normaliza_resultados(monkeypatch):
    class FakeYDL:
        def __init__(self, opciones):
            assert opciones["extract_flat"] is True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, consulta, download):
            assert consulta == "ytsearch12:musica libre"
            assert download is False
            return {"entries": [
                {"id": "abc123", "title": "Tema", "channel": "Canal", "duration": 75},
                None,
            ]}

    monkeypatch.setattr("descargador.search.yt_dlp.YoutubeDL", FakeYDL)

    assert buscar_youtube("musica libre") == [{
        "title": "Tema",
        "url": "https://www.youtube.com/watch?v=abc123",
        "channel": "Canal",
        "duration": 75,
    }]
