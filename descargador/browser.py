def resolve_with_browser(page_url, extract_from_page):
    """Abre un navegador visible para que el usuario resuelva el captcha.

    Navega a page_url, espera a que extract_from_page(page) devuelva el link
    directo (tras la resolucion manual del captcha), y lo retorna.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.goto(page_url)
            return extract_from_page(page)
        finally:
            browser.close()
