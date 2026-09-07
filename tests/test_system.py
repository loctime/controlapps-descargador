import descargador.system as system


def test_abrir_ruta_en_linux_usa_xdg_open(monkeypatch):
    llamadas = []
    monkeypatch.setattr(system.sys, "platform", "linux")
    monkeypatch.setattr(system.subprocess, "Popen", lambda args: llamadas.append(args))

    system.abrir_ruta("/tmp/archivo.mp4")

    assert llamadas == [["xdg-open", "/tmp/archivo.mp4"]]


def test_abrir_ruta_en_macos_usa_open(monkeypatch):
    llamadas = []
    monkeypatch.setattr(system.sys, "platform", "darwin")
    monkeypatch.setattr(system.subprocess, "Popen", lambda args: llamadas.append(args))

    system.abrir_ruta("/tmp/archivo.mp4")

    assert llamadas == [["open", "/tmp/archivo.mp4"]]
