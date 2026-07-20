# Descargador — Diseño

**Fecha:** 2026-07-20
**Estado:** Aprobado, listo para plan de implementación

## Objetivo

Un gestor de descargas propio, liviano, tipo mini-JDownloader. Reemplaza los
scripts sueltos (`Descargar_Links.py`) por una app con interfaz gráfica,
persistencia de cola, y arquitectura pensada para sumar más hosts en el futuro.

Primer host soportado: **MediaFire**. La arquitectura permite agregar Mega,
Google Drive, etc. sin reescribir el resto.

## Alcance

**Incluye (v1):**
- GUI Tkinter con lista de descargas y barra de progreso por ítem.
- 1 descarga simultánea (secuencial).
- Reanudación por `Range` (a nivel archivo y a nivel cola).
- Cola persistente en `estado.json`: sobrevive al cierre de la app.
- Cargar links: pegar en cuadro de texto + botón "Cargar .txt".
- Resolver de MediaFire vía `urllib` (rápido).
- Fallback a navegador Playwright **visible** cuando hay captcha, para que el
  usuario lo resuelva a mano.
- Controles: Pausar/Reanudar global, Reintentar fallidos, Abrir carpeta.
- Selector de carpeta destino que recuerda la última usada.

**No incluye (futuro):**
- Otros hosts (Mega, Drive, etc.) — la interfaz queda lista, pero no se
  implementan en v1.
- Pausar/cancelar una descarga individual (solo pausa global en v1).
- Descargas en paralelo (queda en 1 a la vez).
- Resolución automática de captcha (siempre manual vía navegador).

## Stack

- **Python 3** + **Tkinter** (GUI, viene con Python).
- **urllib** (descarga y resolución rápida de links).
- **Playwright** (fallback de captcha; ya instalado en la máquina).

## Ubicación

`C:\Users\User\Desktop\Proyectos\Descargador\`

## Arquitectura

Separación por responsabilidad para que sumar hosts sea de bajo costo:

### `resolvers/` — un módulo por host
Cada resolver sabe dos cosas:
- `matches(url) -> bool` — si la URL le pertenece a este host.
- `resolve(url) -> str` — devuelve el link directo de descarga (rápido, urllib).
  Si no lo encuentra (captcha/bloqueo), lanza `NeedsBrowser`.

Un **registry** recorre los resolvers registrados y elige el que hace match.
v1 incluye solo `mediafire.py`. Agregar un host nuevo = crear un módulo con esa
interfaz y registrarlo.

### `browser.py` — fallback Playwright (común a todos los hosts)
Cuando un resolver lanza `NeedsBrowser`:
1. Abre Playwright en modo **visible** (headed) en la página del host.
2. El usuario resuelve el captcha en el navegador real.
3. El script extrae el link directo de esa sesión ya cargada.
4. Cierra el navegador y sigue la descarga.

### `downloader.py` — motor de descarga
- Descarga **secuencial** (1 archivo a la vez).
- Reanudación por header `Range: bytes=N-`.
- Lee en chunks de 1 MB, reporta progreso vía callback.
- Corre en un **thread worker** aparte para no congelar la GUI.
- Maneja disco lleno (errno 28): pausa todo y avisa.

### `estado.json` — cola persistente
Lista de ítems, cada uno con:
- `url` (página del host)
- `nombre` (archivo destino)
- `estado`: `pendiente` | `descargando` | `completo` | `fallido` | `pausado`
- `bytes_bajados`
- `carpeta` destino

Se guarda ante cada cambio de estado. Al abrir la app, se recarga la cola.

### `app.py` — GUI Tkinter
Layout:
- **Arriba:** cuadro de texto para pegar links + botón "Agregar";
  botón "Cargar .txt"; selector de carpeta destino (recuerda la última).
- **Medio:** tabla de descargas (nombre, tamaño, %, estado) con barra de
  progreso por ítem.
- **Abajo:** botones Pausar/Reanudar (global), Reintentar fallidos,
  Abrir carpeta.

## Modelo de threading

- La GUI corre en el hilo principal de Tkinter.
- Un **worker thread** hace las descargas.
- Comunicación worker → GUI vía `queue.Queue` + `root.after()` polling
  (patrón estándar de Tkinter; nunca se tocan widgets desde otro hilo).

## Flujo de datos

1. El usuario agrega links (pegados o desde .txt).
2. Se parsean, se detecta el host, se **ordenan por número de parte**
   (`part01`, `part02`, …) y se agregan a la cola + `estado.json`.
3. El worker toma el próximo `pendiente`:
   - `resolver.resolve(url)` → link directo.
   - Si lanza `NeedsBrowser` → `browser.py` abre el navegador → usuario
     resuelve captcha → link directo.
   - Descarga con reanudación → callback de progreso actualiza la GUI.
   - Marca `completo` o `fallido` en `estado.json`.
4. **Pausar** setea un flag; el worker corta el chunk actual y frena.
   **Reanudar** sigue desde los bytes ya bajados.

## Detección de captcha

En el resolver de MediaFire: si el regex del link directo
(`https://download[0-9]+\.mediafire\.com...`) **no matchea** en el HTML, se
asume captcha/bloqueo y se lanza `NeedsBrowser`. Simple y robusto: cualquier
caso donde no se pueda resolver automáticamente cae al navegador manual.

## Manejo de errores

- **Disco lleno** (errno 28): pausa toda la cola, avisa en la GUI.
- **Timeout / error de red**: marca el ítem como `fallido`, reintentable con el
  botón "Reintentar fallidos".
- **Captcha**: no es error; dispara el navegador.

## Testing

- **Resolvers**: testeables con fixtures de HTML (página con link / página con
  captcha).
- **Downloader**: testeable contra un servidor HTTP local que soporte `Range`.
- **GUI**: prueba manual.

## Migración de lo existente

Los scripts actuales (`Descargar_Links.py`, `Descargar_MK11.py`,
`dlc_decrypt.py`) quedan como referencia. La lógica de resolución de MediaFire y
reanudación se reutiliza dentro de la nueva estructura modular. `dlc_decrypt.py`
(desencriptar archivos `.dlc` de JDownloader) puede sumarse más adelante como
otra forma de importar links, pero no es parte de v1.
