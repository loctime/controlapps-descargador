# Agrupado de links por release

## Problema

`estado.json` mezcla items de releases distintas en una sola lista plana (ej. partes de GTA V y de Sleeping Dogs intercaladas). No hay forma de ver de un vistazo qué release está completa, ni de borrar todas las partes de una release fallida de una sola vez.

## Objetivo

Agrupar los items de la tabla por release, poder colapsar/expandir cada grupo (o todos a la vez), y borrar un grupo entero seleccionándolo.

## Diseño

### Agrupado (derivado, no persistido)

No se toca el schema de `Item` ni `state.json`. El grupo se calcula al vuelo a partir de `nombre`, reusando el regex `_PART` que ya existe para `sort_by_part`.

Nueva función en `descargador/links.py`:

```python
def group_key(nombre):
    m = _PART.search(nombre)
    key = nombre[:m.start()] if m else nombre
    return key.rstrip(" .-_")
```

- Con `part0*NN` en el nombre → key es el prefijo antes de esa parte, sin separadores colgantes.
- Sin `part0*NN` → key es el nombre completo → el item queda como grupo de 1 (mismo trato visual que un grupo real).

`app.py` agrupa `self.state.items` por `group_key(it.nombre)` preservando el orden de primera aparición. No hay cambios en `State.add()` / `State.save()` / `State.load()`.

### UI: Treeview jerárquico

La tabla pasa de lista plana a árbol de dos niveles:

- **Nodo padre (grupo)**: iid = `"grp:" + key` (evita colisión con iid de items, que siguen siendo la url). Columna nombre = `"<key>  (X/N completos)"` donde X = items con `estado == "completo"`, N = total de items del grupo. Columna tamaño = suma de `total` de los items que ya lo conocen (`total > 0`). Resto de columnas vacío.
- **Nodo hijo (item)**: igual que hoy — iid = url, misma `_fila()`.

Colapso/expansión individual es gratis vía comportamiento nativo de `ttk.Treeview` (flechita en el nodo padre).

**Botón "Colapsar todo / Expandir todo"** en la barra inferior (toggle): itera los nodos de grupo de nivel superior y aplica `self.tree.item(iid, open=<bool>)` a todos.

**Borrado extendido**: `_quitar_seleccionados` sigue funcionando sobre urls. Antes de filtrar, expande la selección: si un iid seleccionado empieza con `"grp:"`, se reemplaza por las urls de todos sus hijos. El guard existente de "no borrar si hay una descarga en curso" se evalúa igual, sobre el conjunto ya expandido.

`_refrescar_tabla` y `_drenar_cola` reconstruyen el árbol completo (agrupar + insertar padres + insertar hijos) en cada refresh — sigue siendo barato porque solo corre cuando hay cambios en cola (cada 200ms, no-op si no hay updates).

### Fuera de alcance

- No se persiste el estado colapsado/expandido entre reinicios de la app (siempre arranca expandido).
- No hay edición manual de a qué grupo pertenece un item — el agrupado es 100% automático por nombre.
- Orden de grupos = orden de primera aparición en `state.items`, no alfabético.

## Testing

Agregar a `tests/test_links.py`: casos para `group_key()` — con `partNN`/`part0N` en distintas posiciones y mayúsculas/minúsculas, sin part (nombre completo como key), separadores colgantes (`.`, `-`, `_`, espacio) recortados correctamente.

Agregar a `tests/` (nuevo `test_app.py` o similar si ya no existe cobertura de UI-logic): la función de expansión de selección grupo→urls, y el cálculo de `X/N completos` por grupo, como funciones puras extraídas si hace falta para poder testearlas sin instanciar Tkinter.
