import os
from pathlib import Path


def browser_executable(environ=None):
    """Devuelve Chrome/Edge del sistema si esta instalado.

    En el ejecutable empaquetado los binarios descargados por Playwright no
    viajan con la app. Chrome del sistema evita depender de ese cache externo.
    """
    environ = environ or os.environ
    program_files = [environ.get("PROGRAMFILES"), environ.get("PROGRAMFILES(X86)"), environ.get("LOCALAPPDATA")]
    suffixes = (
        ("Google", "Chrome", "Application", "chrome.exe"),
        ("Microsoft", "Edge", "Application", "msedge.exe"),
    )
    for root in program_files:
        if not root:
            continue
        for suffix in suffixes:
            candidate = Path(root).joinpath(*suffix)
            if candidate.is_file():
                return str(candidate)
    return None


def resolve_with_browser(page_url, extract_from_page, destino):
    """Abre un navegador visible para que el usuario resuelva el captcha.

    Navega a page_url, espera a que extract_from_page(page, destino) devuelva
    el link directo (tras la resolucion manual del captcha) o None (si el
    propio resolver ya guardo el archivo en destino), y lo retorna.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        options = {"headless": False}
        executable = browser_executable()
        if executable:
            options["executable_path"] = executable
        browser = p.chromium.launch(**options)
        try:
            page = browser.new_page()
            page.goto(page_url)
            return extract_from_page(page, destino)
        finally:
            browser.close()
