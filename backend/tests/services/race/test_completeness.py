"""Tests de ``app.services.race.completeness`` (feature 044, T013).

Cubre ``check_completeness`` (función pura sobre una secuencia de
ordinales), el catálogo cerrado ``AcknowledgeReasonCode`` (R-05 — vive en
este módulo según ``tasks.md`` T017, no en ``schemas/race_imports.py`` como
``RevisionReasonCode``) y ``apply_corrections`` (add/edit/remove sobre un
``ParsedResults`` + re-verificación).

Contrato exacto (``contracts/reading-integrity.md``):
    ``status == "inconsistent"`` **iff** el multiset de ordinales de una
    categoría ≠ ``{1…N}``, donde N es la cantidad de filas de la categoría.

Regla derivada, no textual pero necesaria para una categoría vacía: con
``N=0``, ``{1..0}`` es el conjunto vacío, que coincide con el multiset
vacío de ``ordinals=[]`` — por lo tanto una categoría sin filas es "ok" por
definición (no hay nada incompleto en un conjunto vacío). Se prueba
explícitamente porque es la clase de borde más fácil de implementar mal
(ej. reventar con ``max()`` de una lista vacía).

Supuesto no confirmado en el contrato: ``missing``/``duplicated`` se
devuelven ordenados ascendentemente (comportamiento razonable para una UI,
pero no está escrito en ``reading-integrity.md``/R-05 — señalado a
``engineering-lead`` junto con el resto de ambigüedades).
"""
from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.services.race.completeness import (
    AcknowledgeReasonCode,
    apply_corrections,
    check_completeness,
)
from app.services.race.pdf_parser import ParsedCategory, ParsedResults, ResultsRow

try:
    from app.services.race.completeness import ACKNOWLEDGE_REASON_LABELS
except ImportError:  # pragma: no cover - documentado en el reporte a engineering-lead
    ACKNOWLEDGE_REASON_LABELS = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(position: int, *, bib: str | None = None, time_raw: str = "0:10:00", points: int = 10) -> ResultsRow:
    return ResultsRow(
        position=position,
        bib=bib if bib is not None else str(position),
        name="Nombre Ficticio",
        city="Ciudad Ficticia",
        club="Club Ficticio",
        time_raw=time_raw,
        points=points,
    )


def _parsed(rows: list[ResultsRow], *, header: str = "INFANTIL A", code: str | None = "INF_A") -> ParsedResults:
    return ParsedResults(
        categories=[ParsedCategory(header_raw=header, code=code, rows=rows)],
        unreadable_rows=[],
    )


# ===========================================================================
# check_completeness — gap, duplicado, ambos, vacío, fila única
# ===========================================================================


class TestCheckCompletenessGapAndDuplicate:
    def test_gap_is_reported_as_missing(self):
        report = check_completeness([1, 2, 3, 5, 6])

        assert report.status == "inconsistent"
        assert report.missing == [4]
        assert report.duplicated == []

    def test_duplicate_is_reported_as_duplicated(self):
        report = check_completeness([1, 2, 2, 3, 4])

        assert report.status == "inconsistent"
        assert report.missing == []
        assert report.duplicated == [2]

    def test_gap_and_duplicate_together(self):
        """Defecto real observado en ambos PDFs de 2025 (research.md R-05):
        un ordinal duplicado Y uno faltante en la misma categoría."""
        report = check_completeness([1, 2, 2, 4, 6])  # N=5 -> esperado {1..5}

        assert report.status == "inconsistent"
        assert report.missing == [3, 5]
        assert report.duplicated == [2]

    def test_empty_category_is_ok(self):
        """{1..0} == conjunto vacío == multiset vacío -> consistente."""
        report = check_completeness([])

        assert report.status == "ok"
        assert report.missing == []
        assert report.duplicated == []

    def test_single_row_correct_ordinal_is_ok(self):
        report = check_completeness([1])

        assert report.status == "ok"
        assert report.missing == []
        assert report.duplicated == []

    def test_single_row_wrong_ordinal_is_inconsistent(self):
        """Una sola fila pero con ordinal 5 (N=1, esperado {1}) -> falta el
        1; el 5 en sí no aparece como "duplicado" (no lo es) ni tiene un
        campo propio en el contrato — solo se refleja vía `missing`."""
        report = check_completeness([5])

        assert report.status == "inconsistent"
        assert report.missing == [1]
        assert report.duplicated == []


class TestCheckCompletenessProperty:
    """Hypothesis: cualquier secuencia 1..N sin huecos ni duplicados da
    status ok, sin importar el orden en que llegan los ordinales (multiset,
    no lista posicional)."""

    @given(n=st.integers(min_value=1, max_value=200))
    def test_sequential_1_to_n_is_always_ok(self, n: int):
        report = check_completeness(list(range(1, n + 1)))

        assert report.status == "ok"
        assert report.missing == []
        assert report.duplicated == []

    @given(n=st.integers(min_value=1, max_value=60), data=st.data())
    def test_any_order_of_1_to_n_is_ok(self, n: int, data: st.DataObject):
        shuffled = data.draw(st.permutations(list(range(1, n + 1))))

        report = check_completeness(list(shuffled))

        assert report.status == "ok"
        assert report.missing == []
        assert report.duplicated == []


# ===========================================================================
# AcknowledgeReasonCode — catálogo cerrado (R-05)
# ===========================================================================


class TestAcknowledgeReasonCatalogue:
    def test_catalogue_has_exactly_the_four_documented_codes(self):
        codes = {c.value for c in AcknowledgeReasonCode}

        assert codes == {
            "source_duplicate_ordinal",
            "source_missing_ordinal",
            "source_disqualification_gap",
            "verified_against_source",
        }

    def test_every_code_has_a_non_empty_spanish_label(self):
        if ACKNOWLEDGE_REASON_LABELS is None:
            pytest.fail(
                "No se encontró ACKNOWLEDGE_REASON_LABELS en "
                "app.services.race.completeness — ver ambigüedad reportada "
                "a engineering-lead (paralelo a REVISION_REASON_LABELS)."
            )
        for code in AcknowledgeReasonCode:
            label = ACKNOWLEDGE_REASON_LABELS[code]
            assert isinstance(label, str) and label.strip()

    def test_an_unknown_reason_is_not_a_member(self):
        with pytest.raises(ValueError):
            AcknowledgeReasonCode("motivo_inventado")


# ===========================================================================
# apply_corrections — add / edit / remove + re-verificación
# ===========================================================================


class TestApplyCorrectionsAdd:
    def test_add_fixes_a_gap(self):
        parsed = _parsed([_row(1), _row(2), _row(4)])  # falta 3
        corrections = [
            {
                "op": "add",
                "category_header": "INFANTIL A",
                "ordinal": 3,
                "row": {
                    "position": 3, "bib": "803", "name": "Nombre Ficticio",
                    "city": "Ciudad Ficticia", "club": "Club Ficticio",
                    "time_raw": "0:12:00", "points": 8,
                },
            }
        ]

        result = apply_corrections(parsed, corrections)

        ordinals = sorted(r.position for r in result.categories[0].rows)
        assert ordinals == [1, 2, 3, 4]
        assert check_completeness(ordinals).status == "ok"


class TestApplyCorrectionsEdit:
    def test_edit_fixes_a_misread_ordinal(self):
        """Una fila fue leída con ordinal 6 pero en realidad era la 4
        (ej. dígito mal reconocido) — se identifica por su ordinal actual
        (6) y se corrige a su valor real."""
        parsed = _parsed([_row(1), _row(2), _row(3), _row(6, bib="806")])
        corrections = [
            {
                "op": "edit",
                "category_header": "INFANTIL A",
                "ordinal": 6,
                "row": {
                    "position": 4, "bib": "806", "name": "Nombre Ficticio",
                    "city": "Ciudad Ficticia", "club": "Club Ficticio",
                    "time_raw": "0:15:00", "points": 5,
                },
            }
        ]

        result = apply_corrections(parsed, corrections)

        ordinals = sorted(r.position for r in result.categories[0].rows)
        assert ordinals == [1, 2, 3, 4]
        assert check_completeness(ordinals).status == "ok"


class TestApplyCorrectionsRemove:
    def test_remove_fixes_an_extra_row(self):
        """N=6 filas pero una posición 7 espuria (fuera de {1..6}) — se
        retira y las 5 restantes quedan consistentes."""
        parsed = _parsed(
            [_row(1), _row(2), _row(3), _row(4), _row(5), _row(7, bib="807")]
        )
        corrections = [
            {"op": "remove", "category_header": "INFANTIL A", "ordinal": 7}
        ]

        result = apply_corrections(parsed, corrections)

        ordinals = sorted(r.position for r in result.categories[0].rows)
        assert ordinals == [1, 2, 3, 4, 5]
        assert check_completeness(ordinals).status == "ok"


class TestApplyCorrectionsSequential:
    def test_multiple_corrections_apply_in_order(self):
        """add + remove combinados sobre la misma categoría: falta el 3,
        sobra un 8 espurio."""
        parsed = _parsed(
            [_row(1), _row(2), _row(4), _row(5), _row(8, bib="808")]
        )
        corrections = [
            {
                "op": "add",
                "category_header": "INFANTIL A",
                "ordinal": 3,
                "row": {
                    "position": 3, "bib": "803", "name": "Nombre Ficticio",
                    "city": "Ciudad Ficticia", "club": "Club Ficticio",
                    "time_raw": "0:12:00", "points": 8,
                },
            },
            {"op": "remove", "category_header": "INFANTIL A", "ordinal": 8},
        ]

        result = apply_corrections(parsed, corrections)

        ordinals = sorted(r.position for r in result.categories[0].rows)
        assert ordinals == [1, 2, 3, 4, 5]
        assert check_completeness(ordinals).status == "ok"

    def test_apply_corrections_does_not_mutate_the_input(self):
        """``apply_corrections`` debe devolver un ``ParsedResults`` nuevo
        (o al menos no dejar el original con las filas ya corregidas) —
        importante porque el router re-aplica correcciones almacenadas
        sobre un parseo fresco en cada dry-run/commit (R-05:
        ``_reload_parsed_from_storage``), nunca debe acumular estado."""
        original = _parsed([_row(1), _row(2), _row(4)])
        original_ordinals_before = sorted(r.position for r in original.categories[0].rows)

        apply_corrections(
            original,
            [
                {
                    "op": "add",
                    "category_header": "INFANTIL A",
                    "ordinal": 3,
                    "row": {
                        "position": 3, "bib": "803", "name": "Nombre Ficticio",
                        "city": "Ciudad Ficticia", "club": "Club Ficticio",
                        "time_raw": "0:12:00", "points": 8,
                    },
                }
            ],
        )

        original_ordinals_after = sorted(r.position for r in original.categories[0].rows)
        assert original_ordinals_after == original_ordinals_before
