# Mirrors por item con failover automático

## Problema

Cuando un link muere (ej. 404 de MediaFire, ver `2026-07-20`-ish debugging session), el item queda "fallido" para siempre salvo reintento manual, aunque exista un link alternativo (otro host) para el mismo archivo. Hoy, pegar ese link alternativo crea una fila nueva separada — duplica el item en vez de darle una segunda chance al mismo.

Este es el primero de 3 sub-proyectos relacionados (los otros dos son resolvers nuevos para `megaup.net` y `rootz.so`, fuera de este spec). Este sub-proyecto es host-agnóstico: funciona con cualquier host que ya tenga resolver, y queda listo para los hosts nuevos en cuanto existan sus resolvers.

## Objetivo

Un item de la cola puede tener varias URLs candidatas para el mismo archivo. Si la que se está usando falla, se prueba automáticamente la siguiente en la misma pasada, antes de marcar el item como fallido.

## Diseño

### Modelo de datos

`descargador/state.py`, `Item` suma:

```python
mirrors: list[str] = field(default_factory=list)
```

`url` sigue siendo la identidad primaria del item (iid del Treeview, clave de dedup). `mirrors` son URLs alternativas adicionales para el mismo archivo. Campo con default → `state.json` viejo (sin `mirrors`) carga bien, sin migración.

### Merge al agregar (`State.add`)

Clave de merge: `(nombre, carpeta)`.

- Si ya existe un item con mismo `(nombre, carpeta)` y la `url` nueva es distinta de la existente y no está ya en `mirrors`: se agrega a `mirrors` del item existente. No se crea fila nueva.
- Si no hay match por `(nombre, carpeta)`: se crea un `Item` nuevo como hoy (`url` = primaria, `mirrors = []`).
- Dedup exacto de `url` (ya existente hoy) se mantiene: no agregar si `url` ya es la primaria o ya está en `mirrors`.

**Limitación conocida (no se resuelve en este spec):** `_agregar_links` en `app.py` obtiene el `nombre` vía `resolver.filename(url)` si hay resolver para ese host, o con el fallback `url.rstrip("/").split("/")[-1]` si no lo hay. Para hosts sin resolver instalado (ej. rootz.so hoy), ese fallback no da el nombre real del archivo, así que un mirror de ese host no va a mergear correctamente hasta que exista su resolver. Para megaup.net el fallback ya da el nombre correcto porque está literalmente en el path de la URL — no hace falta resolver para el merge en ese caso particular.

Un mirror de un host sin resolver instalado igual se guarda en `mirrors` (si por casualidad mergeó bien, o como item nuevo si no) — queda inerte hasta que el resolver de ese host exista, sin necesidad de repegar el link.

### Failover en `Engine.process_one`

Reemplaza la lógica actual de un solo intento por un loop sobre `candidatos = [item.url] + item.mirrors`, en orden, dentro de la misma llamada:

- `get_resolver(candidato)` devuelve `None` → sin resolver para ese host, se salta al siguiente candidato.
- `resolver.resolve(candidato)` explota (excepción no `NeedsBrowser`), o `download_fn(...)` devuelve `motivo == "error"` o el flujo termina en `"sin_resolver"` → ese candidato falló, se prueba el siguiente.
- `motivo` es `"pausado"` o `"disco_lleno"` → se corta ahí y se devuelve tal cual, sin probar más candidatos (no es un fallo del mirror: es el usuario pausando o el disco lleno; cambiar de mirror no ayuda).
- `motivo == "completo"` → se devuelve tal cual, listo.
- Se agotan todos los candidatos sin `"completo"`/`"pausado"`/`"disco_lleno"` → recién ahí el item queda `"fallido"`.

`NeedsBrowser` sigue manejándose igual que hoy (por candidato): si el resolver de ese candidato la levanta, se usa `browser_resolve` para ese candidato puntual antes de decidir si siguió o no.

### `download.py`

Sin cambios. El resume por `Range` ya funciona igual sin importar qué mirror escribió los bytes previos — mismo archivo, mismo `destino` (mismo `nombre`), mismo tamaño total esperado.

## Fuera de alcance

- Resolver para `megaup.net` (sub-proyecto 2).
- Resolver para `rootz.so` (sub-proyecto 3).
- UI: no hay indicación visual de "este item tiene N mirrors" ni orden manual de prioridad entre mirrors — se prueban en el orden en que se pegaron.
- No se resuelve el gotcha de nombre-sin-resolver para hosts nuevos (documentado arriba, se resuelve naturalmente cuando el resolver de ese host exista).

## Testing

- `tests/test_state.py`: `State.add()` mergea por `(nombre, carpeta)` en vez de crear item nuevo cuando corresponde; no duplica si la url ya está en `mirrors`; sigue sin duplicar por url exacta.
- `tests/test_engine.py`: casos de failover — primer candidato falla (excepción en resolver, o `sin_resolver` por falta de resolver) y el segundo completa → `"completo"`; todos los candidatos fallan → `"fallido"`; `"pausado"`/`"disco_lleno"` en el primer candidato corta sin probar el segundo.
