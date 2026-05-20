"""
Tests para Ej1 — Hello-world LangGraph
Aislado: no requiere DB, fixtures externos, ni variables de entorno.
"""

import pytest
from hello_graph import graph


def test_graph_invoke_returns_expected_message():
    """
    Verifica que el grafo compilado:
    - Acepta el input sin error (compilacion correcta).
    - Retorna un estado con 'message' que contiene 'hola', 'Coach' y 'adios'.
    """
    result = graph.invoke({"name": "Coach", "message": ""})

    assert "hola" in result["message"]
    assert "Coach" in result["message"]
    assert "adios" in result["message"]
