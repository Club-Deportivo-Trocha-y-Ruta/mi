"""
Ej1 — Hello-world LangGraph
Un grafo determinista de 3 nodos lineales. Sin LLM. Sin DB.
Objetivo: comprender StateGraph, nodos como funciones puras y el ciclo compile→invoke.
"""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# ---------------------------------------------------------------------------
# 1. ESTADO DEL GRAFO
# TypedDict define el "contrato" de qué datos viajan entre nodos.
# Cada nodo recibe el estado completo y devuelve solo los campos que modifica.
# ---------------------------------------------------------------------------
class GraphState(TypedDict):
    name: str
    message: str


# ---------------------------------------------------------------------------
# 2. NODOS
# Cada nodo es una función pura: recibe el estado actual, devuelve un dict
# con los campos que cambia. LangGraph hace el merge automáticamente.
# ---------------------------------------------------------------------------
def greet(state: GraphState) -> dict:
    # Primer nodo: inicia el mensaje con un saludo genérico.
    return {"message": "hola"}


def enrich(state: GraphState) -> dict:
    # Segundo nodo: lee name del estado y lo incorpora al mensaje existente.
    return {"message": f"{state['message']}, {state['name']}"}


def farewell(state: GraphState) -> dict:
    # Tercer nodo: cierra el mensaje con despedida.
    return {"message": f"{state['message']}! adios"}


# ---------------------------------------------------------------------------
# 3. CONSTRUCCIÓN Y COMPILACIÓN DEL GRAFO
# StateGraph recibe el TypedDict como "esquema" del estado.
# .compile() convierte la definición en un objeto invocable (Runnable).
# ---------------------------------------------------------------------------
graph_builder = StateGraph(GraphState)

graph_builder.add_node("greet", greet)
graph_builder.add_node("enrich", enrich)
graph_builder.add_node("farewell", farewell)

graph_builder.add_edge(START, "greet")
graph_builder.add_edge("greet", "enrich")
graph_builder.add_edge("enrich", "farewell")
graph_builder.add_edge("farewell", END)

graph = graph_builder.compile()


# ---------------------------------------------------------------------------
# 4. PUNTO DE ENTRADA
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    initial_state = {"name": "Coach", "message": ""}
    final_state = graph.invoke(initial_state)
    print(final_state)
