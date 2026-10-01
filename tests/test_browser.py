from descargador.browser import browser_executable


def test_browser_executable_prefiere_chrome(monkeypatch, tmp_path):
    chrome = tmp_path / "Program Files" / "Google" / "Chrome" / "Application"
    chrome.mkdir(parents=True)
    executable = chrome / "chrome.exe"
    executable.touch()

    monkeypatch.setattr("descargador.browser.Path.is_file", lambda path: path == executable)
    assert browser_executable({"PROGRAMFILES": str(tmp_path / "Program Files")}) == str(executable)


def test_browser_executable_none_sin_navegador(monkeypatch):
    monkeypatch.setattr("descargador.browser.Path.is_file", lambda path: False)
    assert browser_executable({"PROGRAMFILES": "C:/inexistente"}) is None
