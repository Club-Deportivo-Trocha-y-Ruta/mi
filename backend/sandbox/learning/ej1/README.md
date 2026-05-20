# Ej1 — Hello-world LangGraph

Sandbox de aprendizaje aislado. No toca codigo de produccion.

## Que es este ejercicio

Un grafo determinista de 3 nodos lineales que construye un mensaje paso a paso.
No usa LLM, no usa base de datos, no llama APIs externas.
El objetivo es internalizar los conceptos basicos de LangGraph antes de tocar
el pipeline real de race-results-v2.

## Estructura

```
ej1/
├── hello_graph.py       # Implementacion: StateGraph + 3 nodos + compile + invoke
├── test_hello_graph.py  # 1 test pytest verificando compilacion y output
├── CONCEPTS.md          # Explicacion pedagogica de los 5 conceptos clave
├── requirements.txt     # Solo langgraph>=1.2,<2.0
└── README.md            # Este archivo
```

## Como instalar

Tienes dos opciones. Elige la que prefieras:

**Opcion A — usar el venv de produccion (mas rapido, menos limpio):**

```bash
source backend/.venv/bin/activate
pip install -r backend/sandbox/learning/ej1/requirements.txt
```

**Opcion B — venv dedicado para el sandbox (recomendado si quieres aislar completamente):**

```bash
python3 -m venv backend/sandbox/.venv-sandbox
source backend/sandbox/.venv-sandbox/bin/activate
pip install -r backend/sandbox/learning/ej1/requirements.txt
```

## Como correr

```bash
# Desde la raiz del proyecto, con el venv activo:
python backend/sandbox/learning/ej1/hello_graph.py
# Output esperado:
# {'name': 'Coach', 'message': 'hola, Coach! adios'}
```

## Como correr los tests

```bash
# Desde el directorio ej1/ (para que pytest encuentre hello_graph.py):
cd backend/sandbox/learning/ej1
pytest test_hello_graph.py -v
```

## Que aprender

Lee `CONCEPTS.md` antes o despues de correr el script. Cubre:

1. `StateGraph` y por que `TypedDict`
2. Nodos como funciones puras
3. Edges simples vs condicionales
4. `.compile()` — separacion definicion/ejecucion
5. `.invoke()` vs `.stream()`

## Proximo paso

Ej2 — agrega un gate HITL con `interrupt()` para aprender como el grafo
se pausa y reanuda. Es el patron del nodo `hitl_gate_review` en el pipeline real.
