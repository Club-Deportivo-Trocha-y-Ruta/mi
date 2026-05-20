# Conceptos clave — Ej1 Hello-world LangGraph

Este ejercicio introduce los bloques fundamentales de LangGraph a traves de un grafo determinista
(sin LLM). Los mismos patrones aparecen en el pipeline real de race-results-v2.

---

## 1. `StateGraph` y por que `TypedDict` en vez de `dict`

`StateGraph` es el constructor principal de LangGraph. Recibe un *esquema* de estado que describe
que datos viajan entre nodos. Se usa `TypedDict` (no `dict` plano) por tres razones concretas:

- **Tipado estatico**: los type checkers (mypy, pyright) detectan si un nodo intenta leer un
  campo que no existe en el estado.
- **Autocompletado en el IDE**: al escribir `state["name"]` el editor sabe el tipo esperado.
- **Documentacion viva**: el `TypedDict` actua como contrato explícito — cualquier dev nuevo
  puede leerlo y entender que datos maneja el grafo sin abrir cada nodo.

En el pipeline real, `RaceAnalystState` sera un `TypedDict` con ~15 campos (athlete_id, metrics,
draft_analysis, errors, etc.).

---

## 2. Nodos como funciones puras `state -> dict_partial`

Cada nodo recibe el estado completo y devuelve **solo los campos que modifica** (un dict parcial).
LangGraph hace el merge del resultado con el estado existente automaticamente.

```python
def enrich(state: GraphState) -> dict:
    return {"message": f"{state['message']}, {state['name']}"}
    # No devuelve 'name' porque no lo modifica. LangGraph lo conserva igual.
```

Beneficio: los nodos son testeables de forma aislada con un simple `assert enrich({"name": "x",
"message": "hola"}) == {"message": "hola, x"}`. No hace falta levantar el grafo completo.

---

## 3. Edges — `START`, `END` y tipos de conexion

Los edges definen el flujo de ejecucion:

- `add_edge(A, B)` — edge **simple**: siempre va de A a B.
- `add_conditional_edges(A, router_fn)` — edge **condicional**: `router_fn` recibe el estado y
  devuelve el nombre del proximo nodo. Asi se implementan loops y branches (usado en HITL).
- `START` y `END` son constantes de LangGraph — marcan entrada y salida del grafo.

En Ej1 todos los edges son simples: `START -> greet -> enrich -> farewell -> END`.
En Ej2 aparecera el primer edge condicional con `interrupt()`.

---

## 4. `.compile()` — separacion entre definicion y ejecucion

`graph_builder.compile()` transforma la *definicion* del grafo (nodos + edges) en un objeto
`CompiledGraph` que implementa la interfaz `Runnable` de LangChain.

Por que existe esta separacion:

- Permite adjuntar un **checkpointer** en compile (ej: `compile(checkpointer=MemorySaver())`),
  que guarda el estado despues de cada nodo para poder reanudar tras un crash o un HITL gate.
- Permite configurar **retry policies** por nodo antes de ejecutar.
- Hace que el grafo sea serializable e inspeccionable (`.get_graph().draw_mermaid()`).

El objeto resultante (`graph`) es el que se invoca — la definicion en `graph_builder` no
ejecuta nada por si sola.

---

## 5. `.invoke()` vs `.stream()`

| Metodo | Que devuelve | Cuando usarlo |
|---|---|---|
| `graph.invoke(input)` | Estado final completo | Cuando solo necesitas el resultado, no el progreso |
| `graph.stream(input)` | Generador de eventos por nodo | Para SSE, debugging, UX de progreso en tiempo real |

En `stream`, cada evento incluye que nodo acaba de correr y el delta del estado en ese momento.
El pipeline de race-results-v2 usara `stream` en el endpoint SSE para que el coach vea en la
UI como avanza el analisis nodo a nodo.

```python
# stream — ver cada paso
for event in graph.stream({"name": "Coach", "message": ""}):
    print(event)
# {"greet": {"message": "hola"}}
# {"enrich": {"message": "hola, Coach"}}
# {"farewell": {"message": "hola, Coach! adios"}}
```

---

## Proximo paso

**Ej2**: agrega un gate HITL al grafo usando `interrupt()`. El grafo se detiene despues de
`enrich`, espera confirmacion del coach, y luego continua hacia `farewell` con un
`Command(resume=...)`. Es el mismo patron que el nodo `hitl_gate_review` del pipeline real.
