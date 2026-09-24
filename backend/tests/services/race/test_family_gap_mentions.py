"""Tests puros de ``family_gap_mentions`` (feature 045, T030, FR-022).

Sólo texto ficticio: ningún nombre, fecha ni dato real de menores.

Cubre:
- Detección positiva por categoría (líder, ganador, podio, P1/P3, primer/tercer
  lugar, "al primero"/"del tercero", "top 3").
- Insensibilidad a mayúsculas y tildes (incluida la forma NFD).
- Negativos: palabras temporales/ordinales que NO son una mención
  ("primera vuelta", "tercera válida", "liderazgo", "ganó 3 posiciones").
- Límites: máximo 3 snippets de ≤80 caracteres.
- Extracción de los campos visibles para la familia del payload HITL.
"""

from __future__ import annotations

import unicodedata

import pytest

from app.services.race.family_gap_mentions import (
    MAX_SNIPPET_CHARS,
    MAX_SNIPPETS,
    family_visible_texts,
    find_family_gap_mentions,
    with_family_gap_mentions,
)

# ---------------------------------------------------------------------------
# Positivos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        # líder
        ("La brecha fue de 9.4% al líder de la categoría.", "líder"),
        ("Se quedó lejos de los líderes en la primera subida.", "líderes"),
        ("Le faltó ritmo para seguir a la lideresa.", "lideresa"),
        ("Rodó en cabeza de carrera durante dos vueltas.", "cabeza de carrera"),
        # ganador / ganadora / vencedor / campeón
        ("Terminó a 2 minutos de la ganadora.", "ganadora"),
        ("El ganador cruzó la meta con ventaja amplia.", "ganador"),
        ("Se comparó con el vencedor de la válida.", "vencedor"),
        ("Se midió frente a la campeona de la copa.", "campeona"),
        # podio
        ("Está cerca de pelear por el podio.", "podio"),
        ("Todavía le falta para la zona de podios.", "podios"),
        # P1 / P3
        ("Terminó a 45 segundos del P3.", "P3"),
        ("La distancia al P1 fue de 3 minutos.", "P1"),
        ("Quedó lejos de p-3 en tiempo total.", "p-3"),
        # primer / tercer lugar, en sus variantes
        ("Nadie alcanzó el primer lugar sin ese ritmo.", "primer lugar"),
        ("Aspira al primer puesto de la categoría.", "primer puesto"),
        ("Miraba la primera posición con respeto.", "primera posición"),
        ("Pelea el tercer lugar en cada válida.", "tercer lugar"),
        ("Ocupó la tercera posición en la general.", "tercera posición"),
        ("Se acerca al tercer puesto de la serie.", "tercer puesto"),
        ("Fue 1.º lugar en su tanda de calentamiento.", "1.º lugar"),
        ("Fue 3.er puesto en la clasificación parcial.", "3.er puesto"),
        ("Se ubicó en el puesto 3 de la clasificación.", "puesto 3"),
        ("Aspira a la posición 1 de la serie.", "posición 1"),
        # standalone "al primero" / "del tercero"
        ("La brecha al primero se redujo esta vez.", "al primero"),
        ("Le sacó tiempo al tercero en la última vuelta.", "al tercero"),
        ("Estuvo lejos del primero en el sector técnico.", "del primero"),
        # "el primero en cruzar la meta" / primer clasificado
        ("Fue el primero en cruzar la meta.", "primero en cruzar"),
        ("Se acercó al primer clasificado en el último tramo.", "primer clasificado"),
        # top 3 / los tres primeros
        ("Quedó fuera del top 3 por poco margen.", "top 3"),
        ("Rodó cerca de los tres primeros durante la subida.", "tres primeros"),
    ],
)
def test_detecta_mencion(text: str, needle: str) -> None:
    result = find_family_gap_mentions([text])
    assert len(result) == 1, f"esperaba 1 snippet para {text!r}, obtuve {result!r}"
    assert needle.lower() in result[0].lower()


def test_snippet_mantiene_el_texto_original_con_tildes_y_mayusculas() -> None:
    (snippet,) = find_family_gap_mentions(["Quedó a 9.4% del Líder de la carrera."])
    assert "Líder" in snippet  # el snippet sale del texto original, no del plegado


# ---------------------------------------------------------------------------
# Insensibilidad a mayúsculas y tildes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    ["líder", "LÍDER", "lider", "Líder", "LIDER"],
)
def test_lider_ignora_tildes_y_mayusculas(variant: str) -> None:
    assert find_family_gap_mentions([f"Gap de 9% al {variant} del grupo."])


@pytest.mark.parametrize(
    "variant",
    ["primer lugar", "PRIMER LUGAR", "Primer Lugar", "primér lugár"],
)
def test_primer_lugar_ignora_tildes_y_mayusculas(variant: str) -> None:
    assert find_family_gap_mentions([f"Sueña con el {variant} de la copa."])


def test_forma_nfd_descompuesta_tambien_detecta() -> None:
    decomposed = unicodedata.normalize("NFD", "Brecha de 9% al líder de la carrera.")
    assert decomposed != unicodedata.normalize("NFC", decomposed)  # sí viene en NFD
    (snippet,) = find_family_gap_mentions([decomposed])
    assert "lider" in unicodedata.normalize("NFD", snippet).lower().replace("́", "")


# ---------------------------------------------------------------------------
# Negativos — palabras temporales/ordinales o de otro significado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Arrancó fuerte en la primera vuelta y bajó el ritmo después.",
        "Es su primer intento con la nueva relación de cambios.",
        "Mantuvo el ritmo durante los primeros 5 minutos.",
        "Primero calentó y luego hizo la serie completa.",
        "Sale bien a la primera en las curvas cerradas.",
        "En la tercera válida de la temporada mejoró el descenso.",
        "Repetirá la tercera parte del circuito con calma.",
        "Muestra liderazgo dentro del grupo de entrenamiento.",
        "Lidera las bromas del grupo en los viajes.",
        "Ganó 3 posiciones en el último kilómetro.",
        "Mejoró 3 posiciones frente a la válida anterior.",
        "Rodó 3 vueltas seguidas sin bajar la cadencia.",
        "Su percentil 62 indica una carrera sólida en el pelotón.",
        "La posición 12 de la parrilla exigió salir con calma.",
        "Terminó en P13 de su categoría.",
        "Completó 30 minutos de intervalos en la semana.",
        "El tercero de los bloques fue el más exigente.",
    ],
)
def test_no_hay_falso_positivo(text: str) -> None:
    assert find_family_gap_mentions([text]) == []


@pytest.mark.parametrize(
    "text",
    [
        "En primer lugar, conviene practicar las curvas cerradas.",
        "En tercer lugar: dormir bien antes de la carrera.",
        "Primero la técnica; en tercer lugar; la nutrición.",
    ],
)
def test_conector_en_primer_lugar_no_es_una_mencion(text: str) -> None:
    assert find_family_gap_mentions([text]) == []


def test_terminar_en_primer_lugar_si_es_una_mencion() -> None:
    assert find_family_gap_mentions(["Terminó en primer lugar de su tanda."])


def test_del_primero_al_segundo_no_es_una_mencion() -> None:
    assert find_family_gap_mentions(["Mejoró del primero al segundo intento."]) == []


def test_texto_limpio_devuelve_lista_vacia() -> None:
    assert find_family_gap_mentions(["Progreso sostenido con buena técnica."]) == []


# ---------------------------------------------------------------------------
# Entradas degeneradas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("empty", [[], [""], [None], [None, "", "   "], None, ""])
def test_entradas_vacias(empty: object) -> None:
    assert find_family_gap_mentions(empty) == []  # type: ignore[arg-type]


def test_un_string_suelto_es_un_campo_no_una_secuencia_de_caracteres() -> None:
    assert len(find_family_gap_mentions("Brecha al líder de 9%.")) == 1


# ---------------------------------------------------------------------------
# Límites: ≤3 snippets, ≤80 caracteres
# ---------------------------------------------------------------------------


def test_constantes_del_contrato() -> None:
    assert MAX_SNIPPETS == 3
    assert MAX_SNIPPET_CHARS == 80


def test_maximo_tres_snippets() -> None:
    fields = [
        "Brecha al líder de 9%.",
        "Distancia al podio de 3 minutos.",
        "Quedó lejos del P3.",
        "Se comparó con la ganadora.",
        "Miró el primer lugar de reojo.",
    ]
    result = find_family_gap_mentions(fields)
    assert len(result) == MAX_SNIPPETS
    # Respeta el orden de los campos.
    assert "líder" in result[0]
    assert "podio" in result[1]
    assert "P3" in result[2]


def test_snippet_no_supera_80_caracteres_y_conserva_la_coincidencia() -> None:
    relleno = "texto sin relevancia para el análisis " * 12
    text = f"{relleno}la brecha al líder fue de 9% {relleno}"
    (snippet,) = find_family_gap_mentions([text])
    assert len(snippet) <= MAX_SNIPPET_CHARS
    assert "líder" in snippet


def test_snippet_al_inicio_y_al_final_del_texto_no_supera_el_limite() -> None:
    relleno = "x " * 100
    inicio = find_family_gap_mentions([f"líder {relleno}"])
    final = find_family_gap_mentions([f"{relleno} podio"])
    for snippet in (*inicio, *final):
        assert len(snippet) <= MAX_SNIPPET_CHARS
    assert "líder" in inicio[0]
    assert "podio" in final[0]


def test_snippet_colapsa_saltos_de_linea() -> None:
    (snippet,) = find_family_gap_mentions(["Brecha\n\nal   líder\tde 9%."])
    assert "\n" not in snippet and "\t" not in snippet and "  " not in snippet


def test_menciones_cercanas_en_un_campo_se_agrupan_en_un_snippet() -> None:
    (snippet,) = find_family_gap_mentions(["Lejos del líder y del P3 en el sector."])
    assert "líder" in snippet and "P3" in snippet


def test_misma_mencion_repetida_no_duplica_snippets() -> None:
    fields = ["Brecha al líder de 9%.", "Brecha al líder de 9%."]
    assert len(find_family_gap_mentions(fields)) == 1


# ---------------------------------------------------------------------------
# Campos visibles para la familia del payload HITL
# ---------------------------------------------------------------------------


def _structured(**overrides: object) -> dict:
    base: dict = {
        "schema_version": "v3",
        "headline": "Avance sostenido en el descenso técnico.",
        "field_reading": {
            "percentile": 62.0,
            "expected_position": 5,
            "actual_position": 4,
            "delta_vs_expected": 1,
            "gap_to_p3_hhmmss": "0:01:12",
            "series_label": "Copa regional",
            "summary": "Mantuvo un ritmo estable dentro del pelotón.",
        },
        "trend": "improving",
        "observations": [
            {
                "claim": "Sostuvo la cadencia en la subida.",
                "evidence": ["percentil 62"],
                "domain": "race",
                "confidence": "medium",
            },
            {
                "claim": "Acumuló buena carga esta semana.",
                "evidence": ["4 sesiones"],
                "domain": "training",
                "confidence": "medium",
            },
        ],
        "actions": [
            {"text": "Practicar curvas cerradas dos veces por semana.", "category": "technique"},
            {"text": "Dormir bien antes de la próxima carrera.", "category": "recovery"},
        ],
        "watch_signals": ["Fatiga acumulada al final de la semana."],
        "coach_question": "¿Cómo se sintió en la última subida?",
        "data_gaps": ["Falta el peso de la bicicleta."],
        "principles_cited": ["3. Progresión técnica en MTB/XCO"],
    }
    base.update(overrides)
    return base


def test_family_visible_texts_incluye_los_campos_que_ve_la_familia() -> None:
    texts = family_visible_texts({"structured_draft": _structured()})
    joined = "\n".join(texts)
    for expected in (
        "Avance sostenido",  # headline
        "Mantuvo un ritmo estable",  # field_reading.summary
        "Copa regional",  # field_reading.series_label
        "Sostuvo la cadencia",  # observations[].claim
        "percentil 62",  # observations[].evidence (dominio no training)
        "Practicar curvas cerradas",  # actions[].text
        "Fatiga acumulada",  # watch_signals
        "Falta el peso",  # data_gaps
        "Progresión técnica",  # principles_cited
    ):
        assert expected in joined, expected


def test_family_visible_texts_excluye_lo_que_la_familia_no_ve() -> None:
    texts = family_visible_texts({"structured_draft": _structured()})
    joined = "\n".join(texts)
    assert "última subida" not in joined  # coach_question
    assert "0:01:12" not in joined  # gap_to_p3_hhmmss
    assert "4 sesiones" not in joined  # evidence de una observación training


def test_family_visible_texts_no_usa_el_markdown_si_hay_draft_estructurado() -> None:
    # El markdown v3 es una proyección de la vista del coach ("gap a P3",
    # "Pregunta para el coach"): escanearlo avisaría en cada análisis.
    payload = {
        "structured_draft": _structured(),
        "draft_markdown": "## Lectura del pelotón\ngap a P3 0:01:12\n## Pregunta para el coach",
    }
    assert find_family_gap_mentions(family_visible_texts(payload)) == []


def test_family_visible_texts_cae_al_markdown_sin_draft_estructurado() -> None:
    payload = {"structured_draft": None, "structured_drafts": {}, "draft_markdown": "Brecha al líder."}
    assert family_visible_texts(payload) == ["Brecha al líder."]


def test_family_visible_texts_recorre_todos_los_drafts_multi_valida() -> None:
    limpio = _structured()
    sucio = _structured(headline="Terminó a 3 minutos del líder.")
    payload = {
        "structured_draft": limpio,
        "structured_drafts": {"1": limpio, "2": sucio},
    }
    result = find_family_gap_mentions(family_visible_texts(payload))
    assert len(result) == 1 and "líder" in result[0]


def test_family_visible_texts_tolera_payload_basura() -> None:
    assert family_visible_texts({}) == []
    assert family_visible_texts({"structured_draft": "no-es-dict"}) == []
    assert family_visible_texts({"structured_drafts": {"1": None, "2": 7}}) == []
    malformed = _structured(observations="no-es-lista", actions=[None, 5], watch_signals=None)
    assert isinstance(family_visible_texts({"structured_draft": malformed}), list)


def test_with_family_gap_mentions_agrega_la_clave_sin_mutar_el_original() -> None:
    original = {
        "step": "review",
        "structured_draft": _structured(headline="Brecha de 9.4% al líder."),
        "critic": {"approved": True},
    }
    snapshot = repr(original)
    enriched = with_family_gap_mentions(original)
    assert repr(original) == snapshot  # el original queda intacto
    assert "family_gap_mentions" not in original
    assert enriched["family_gap_mentions"] and "líder" in enriched["family_gap_mentions"][0]
    assert enriched["step"] == "review" and enriched["critic"] == {"approved": True}


def test_with_family_gap_mentions_texto_limpio_da_lista_vacia_no_ausente() -> None:
    enriched = with_family_gap_mentions({"structured_draft": _structured()})
    assert enriched["family_gap_mentions"] == []
