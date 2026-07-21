# Resolver para megaup.net

## Problema

Los 9 mirrors de `megaup.net` agregados a la cola (fusionados en `mirrors[]` de los items existentes, ver `2026-07-21-mirrors-failover-design.md`) están inertes: `get_resolver()` devuelve `None` para ese host porque no existe resolver. Este es el sub-proyecto 2 de 3 (el otro pendiente es `rootz.so`, más complejo — Next.js renderizado 100% por JS, sin URL directa embebida en el HTML).

## Investigación (resumen)

Probado en vivo (GET plano + Playwright real, sin bypass de nada):

- El link real de descarga (`https://download.megaup.net/?url=<token>`) está **embebido en el HTML** de la página del archivo, dentro de un `<script>` — no hace falta esperar el timer de 2 seg que se ve en pantalla ni ejecutar JS para conseguirlo. Un GET + regex alcanza, igual que MediaFire.
- Ese link de `download.megaup.net` está protegido por un **Cloudflare Turnstile interactivo** ("Verifique que es un ser humano", checkbox). Probado con navegador real (Playwright, headed) sin interacción: no pasa solo después de 11+ segundos. Requiere click humano — no se intentó ni se va a intentar automatizar ese click.

## Objetivo

Agregar `MegaUpResolver` siguiendo el mismo patrón humano-en-el-loop que ya existe para el captcha de MediaFire (navegador visible, la persona resuelve, la app continúa), adaptado a que acá el navegador termina bajando el archivo él mismo en vez de devolver una URL.

## Diseño

### `resolve()` — extracción del link directo

`descargador/resolvers/megaup.py`, `MegaUpResolver`:

- `matches(url)`: `"megaup.net" in url`.
- `filename(url)`: nombre está en el path de la URL (`.../<hash>/<nombre>.rar`) — mismo approach que el fallback que ya usa `_agregar_links` en `app.py` hoy para hosts sin resolver.
- `resolve(url)`: GET plano (urllib, mismo patrón que `MediaFireResolver.resolve`) a la página del archivo, regex sobre el HTML para sacar `href='(https://download\.megaup\.net/\?url=[^']+)'`. Como ese link SIEMPRE requiere el checkbox de Cloudflare (no hay excepción posible, confirmado en la investigación), `resolve()` no intenta bajarlo — lanza `NeedsBrowser(direct)` directo con el link ya resuelto como `page_url`. Si el regex no matchea (página cambió o el archivo ya no existe), deja propagar una excepción común (`RuntimeError`) — el engine ya sabe tratar eso como candidato fallido y probar el siguiente mirror (sin cambios ahí, ya construido en el sub-proyecto de mirrors).

### Cambio de contrato: `Resolver.extract_from_page`

Firma pasa de `extract_from_page(self, page)` a `extract_from_page(self, page, destino)`. Actualiza `descargador/resolvers/base.py` (docstring/firma) y `descargador/resolvers/mediafire.py` (acepta el parámetro nuevo, lo ignora, sigue devolviendo el href como hoy).

Contrato de retorno:
- Devuelve un `str` (URL) → como hoy, el engine sigue bajándolo con `download_fn` (urllib).
- Devuelve `None` → significa "ya guardé el archivo en `destino` yo mismo". El engine no llama a `download_fn`; marca el item `"completo"` directo.

`descargador/browser.py`, `resolve_with_browser(page_url, extract_from_page, destino)` — suma el parámetro `destino` y se lo pasa a `extract_from_page`.

`descargador/engine.py`, `Engine.process_one` — mueve el cálculo de `destino` antes del bloque `try/except NeedsBrowser` (hoy se calcula después), y tras `browser_resolve`, si el resultado es `None`, marca `item.estado = "completo"`, notifica, devuelve `"completo"` sin pasar por `download_fn`.

### `MegaUpResolver.extract_from_page(page, destino)`

Abre `page_url` (que ya es el link de `download.megaup.net`, no la página del archivo). Espera hasta 5 minutos (mismo timeout que ya usa `MediaFireResolver.extract_from_page` para el captcha, `page.wait_for_selector(..., timeout=300000)`) a que el navegador dispare su evento nativo `download` — eso solo pasa una vez que la persona clickeó el checkbox y Cloudflare deja pasar la respuesta real (`Content-Disposition: attachment`). Al evento, `download.save_as(destino)`, espera a que termine de escribirse, devuelve `None`.

## Fuera de alcance

- Sin resume por `Range`, sin descarga segmentada multi-conexión, sin progreso en vivo (bytes_bajados salta de 0 a total al terminar), sin pausa a mitad de descarga — todo eso es exclusivo del camino urllib (`download.py`), que este resolver no usa. Limitación conocida de este host puntual, no se resuelve acá.
- Si el humano no clickea el checkbox en 5 min, timeout — se trata como candidato fallido (prueba el siguiente mirror si hay, si no `"fallido"`), mismo comportamiento que ya existe hoy con el timeout del captcha de MediaFire.
- Resolver para `rootz.so` (sub-proyecto 3, spec aparte).

## Testing

- `tests/test_resolvers` (nuevo o extendido, seguir convención de `test_mediafire.py`): `MegaUpResolver.matches()`, `filename()`, `resolve()` extrae el link correcto de un HTML de ejemplo (fixture con el `<script>` real, sin pegar tokens reales de producción) y lanza `NeedsBrowser` con ese link; `resolve()` sobre HTML sin el patrón lanza excepción común (no `NeedsBrowser`).
- `tests/test_engine.py`: `process_one` cuando `extract_from_page` devuelve `None` (vía un resolver fake tipo `ResolverCaptcha` de los tests existentes) marca el item `"completo"` sin invocar `download_fn`.
- `tests/test_browser.py` (si no existe, crear): `resolve_with_browser` pasa `destino` a `extract_from_page` — con un stub, no con Playwright real (evitar tests que abran navegador de verdad).
