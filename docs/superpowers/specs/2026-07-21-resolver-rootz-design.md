# Resolver para rootz.so

## Problema

`rootz.so` es el sub-proyecto 3 de 3 (mirrors + failover, resolver megaup.net, este). Es el host más complicado: Next.js renderizado 100% client-side, sin URL directa embebida en el HTML servido — a diferencia de MediaFire y megaup.net, acá no hay nada que un simple regex pueda sacar.

## Investigación (resumen)

Probado en vivo con Playwright:

- La página del archivo (`rootz.so/d/<shortId>`) tiene un botón "Download" que abre un **popup**. Ese popup pasa por una cadena de redirects de una red de ads (dominios `*.b9u4wpt.shop`, subdominio random en cada visita) y aterriza en una página tipo "WeUpload" (parte de la misma red de ads, no es un host real) con un botón "Download File".
- Clickear ese botón dispara un evento de descarga **nativo del navegador** (`blob:` URL) — confirmado con Playwright, sin ninguna intervención humana.
- **No hay Cloudflare Turnstile ni ningún check que solo un humano pueda resolver en ningún punto de la cadena** (a diferencia de megaup.net). Los únicos hits a Cloudflare son beacons de analytics (RUM), no challenges. Esto significa que la cadena completa se puede scriptear de punta a punta — no es bypasear seguridad, es solo click-through de ads, algo que cualquier persona haría igual.
- El endpoint API interno (`/api/files/download-by-short?shortId=...`) devuelve el nombre real del archivo en JSON, pero rechaza requests sin sesión de navegador (403 vía urllib plano, con o sin `Referer`). En cambio, el `<title>` de la página SÍ viene renderizado server-side en el HTML crudo y es exactamente el nombre del archivo — confirmado con un GET plano, sin navegador.

## Objetivo

Agregar `RootzResolver`, resolviendo la cadena de clicks de punta a punta sin esperar acción humana (no hay nada que solo un humano pueda resolver acá), reusando el contrato `extract_from_page(page, destino) -> None` ya construido para megaup.net.

## Diseño

### `matches()` / `filename()` / `resolve()`

`descargador/resolvers/rootz.py`, `RootzResolver`:

- `matches(url)`: `"rootz.so" in url`.
- `filename(url)`: GET plano (urllib) a la página del archivo, extrae el `<title>` del HTML con regex — coincide exactamente con el nombre real (confirmado en la investigación). Fallback al último segmento de la URL si el tag no aparece (mismo criterio defensivo que los otros resolvers cuando algo no matchea).
- `resolve(url)`: no hay nada que extraer sin navegador — lanza `NeedsBrowser(url)` directo, con la página original de rootz.so como `page_url` (a diferencia de megaup.net, acá no se resuelve nada de antemano).

Con `filename()` devolviendo el nombre real, el gotcha documentado en `2026-07-21-mirrors-failover-design.md` (mirrors de rootz.so no mergeaban por nombre por falta de resolver) queda resuelto: de acá en más, un mirror de rootz.so va a mergear correctamente con el item existente del mismo archivo.

### `extract_from_page(page, destino)`

1. Click en el botón "Download" de la página ya cargada (`page_url` es la página de rootz.so, navegada por `resolve_with_browser` antes de llamar a este método). Espera el popup que se abre (`page.expect_popup`).
2. En el popup (la página final de la cadena de ads), click en "Download File" — Playwright espera automáticamente a que el elemento exista y sea clickeable (sin sleeps fijos). Esa acción dispara el evento `download` nativo del navegador.
3. `download.save_as(destino)`, cierra el popup, devuelve `None` (mismo contrato que megaup.net: "ya guardé el archivo yo mismo").

Timeout: 60 segundos para cada espera (popup, botón, descarga) — mucho menor que los 5 minutos usados para MediaFire/megaup.net, porque acá no hay un humano al que darle tiempo de reaccionar; si algo tarda más que eso es que el sitio cambió de estructura, no que alguien se está demorando.

Si cualquier paso de la cadena falla (popup no abre, botón no aparece, sin descarga), se deja propagar la excepción — el engine ya sabe tratar eso como candidato fallido y probar el siguiente mirror (sin cambios ahí).

## Fuera de alcance

- Mismas limitaciones que megaup.net: sin resume por Range, sin segmentado, sin progreso en vivo, sin pausa a mitad de descarga (la baja el navegador de punta a punta).
- No se investiga por qué la red de ads (`b9u4wpt.shop`) usa subdominios random ni qué contienen exactamente los payloads intermedios en base64 — no hace falta, el flujo funciona clickeando los botones visibles, no hace falta decodificar nada a mano.

## Testing

- `tests/test_rootz.py` (nuevo, seguir convención de `test_megaup.py`): `matches()`, `filename()` extrae el `<title>` de un HTML de ejemplo (fixture, sin URLs/tokens reales de producción) y usa el fallback cuando no hay `<title>`, `resolve()` lanza `NeedsBrowser` siempre con la url original como `page_url`.
- No hay test automatizado del click-chain completo (`extract_from_page`) contra Playwright real — mismo criterio que `browser.py` hoy: se testea con stubs si el contrato lo amerita, no abriendo un navegador de verdad en la suite.
