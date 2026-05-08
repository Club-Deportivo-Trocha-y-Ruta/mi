"""Tests exhaustivos de validación Pydantic — AttendanceUpdate.

Cubre la lógica del model_validator _validate_consistency:
- Rúbrica solo si presente/tarde
- excuse_reason requerida si ausente/justificado/lesionado
- Combinaciones válidas e inválidas de todos los campos
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.training_session import AttendanceStatus
from app.schemas.training_session import AttendanceUpdate


# ---------------------------------------------------------------------------
# Casos VÁLIDOS
# ---------------------------------------------------------------------------


class TestAttendanceUpdateValid:
    def test_presente_sin_nada_valido(self):
        a = AttendanceUpdate(status=AttendanceStatus.PRESENTE)
        assert a.status == AttendanceStatus.PRESENTE
        assert a.rpe_omni is None

    def test_presente_con_todos_los_rubros(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            rpe_omni=7,
            rubric_effort=4,
            rubric_attitude=5,
            rubric_technique=3,
            individual_feedback="Muy buena sesión",
        )
        assert a.rpe_omni == 7
        assert a.rubric_effort == 4
        assert a.rubric_attitude == 5
        assert a.rubric_technique == 3
        assert a.individual_feedback == "Muy buena sesión"

    def test_tarde_con_rubrica_valido(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.TARDE,
            rpe_omni=5,
            rubric_effort=3,
            rubric_attitude=4,
            rubric_technique=2,
        )
        assert a.status == AttendanceStatus.TARDE
        assert a.rubric_effort == 3

    def test_tarde_sin_rubrica_valido(self):
        a = AttendanceUpdate(status=AttendanceStatus.TARDE)
        assert a.rpe_omni is None

    def test_ausente_con_excuse_reason_valido(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.AUSENTE,
            excuse_reason="Enfermedad",
        )
        assert a.excuse_reason == "Enfermedad"

    def test_justificado_con_excuse_reason_valido(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.JUSTIFICADO,
            excuse_reason="Competencia departamental",
        )
        assert a.excuse_reason == "Competencia departamental"

    def test_lesionado_con_excuse_reason_valido(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.LESIONADO,
            excuse_reason="Lesión tobillo derecho",
        )
        assert a.excuse_reason == "Lesión tobillo derecho"

    def test_presente_con_excuse_reason_permitido(self):
        # excuse_reason es opcional si está presente
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            excuse_reason="Llegó con retraso pero participó",
        )
        assert a.excuse_reason == "Llegó con retraso pero participó"

    def test_rpe_omni_cero_valido(self):
        a = AttendanceUpdate(status=AttendanceStatus.PRESENTE, rpe_omni=0)
        assert a.rpe_omni == 0

    def test_rpe_omni_diez_valido(self):
        a = AttendanceUpdate(status=AttendanceStatus.PRESENTE, rpe_omni=10)
        assert a.rpe_omni == 10

    def test_rubric_uno_valido(self):
        a = AttendanceUpdate(status=AttendanceStatus.PRESENTE, rubric_effort=1)
        assert a.rubric_effort == 1

    def test_rubric_cinco_valido(self):
        a = AttendanceUpdate(status=AttendanceStatus.PRESENTE, rubric_technique=5)
        assert a.rubric_technique == 5

    def test_feedback_vacio_presente_valido(self):
        a = AttendanceUpdate(status=AttendanceStatus.PRESENTE, individual_feedback="")
        assert a.individual_feedback == ""

    def test_feedback_500_chars_valido(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            individual_feedback="A" * 500,
        )
        assert len(a.individual_feedback) == 500


# ---------------------------------------------------------------------------
# Casos INVÁLIDOS — razón requerida cuando no asiste
# ---------------------------------------------------------------------------


class TestAttendanceUpdateRequiresExcuseReason:
    def test_ausente_sin_excuse_reason_falla(self):
        with pytest.raises(ValidationError) as exc_info:
            AttendanceUpdate(status=AttendanceStatus.AUSENTE)
        errors = exc_info.value.errors()
        assert any(
            "razón" in str(e.get("msg", "")) or "excuse_reason" in str(e.get("loc", ""))
            for e in errors
        )

    def test_justificado_sin_excuse_reason_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.JUSTIFICADO)

    def test_lesionado_sin_excuse_reason_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.LESIONADO)

    def test_ausente_excuse_reason_vacio_falla(self):
        # string vacío también debería ser considerado ausente de razón
        # (el validator chequea falsy)
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="",
            )


# ---------------------------------------------------------------------------
# Casos INVÁLIDOS — rúbrica solo si presente/tarde
# ---------------------------------------------------------------------------


class TestAttendanceUpdateRubricaEnAusentes:
    def test_ausente_con_rpe_falla(self):
        with pytest.raises(ValidationError) as exc_info:
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="Gripa",
                rpe_omni=5,
            )
        errors = exc_info.value.errors()
        assert any(
            "rúbrica" in str(e.get("msg", "")).lower()
            or "rubric" in str(e.get("msg", "")).lower()
            or "presente" in str(e.get("msg", "")).lower()
            for e in errors
        )

    def test_ausente_con_rubric_effort_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="Lesión",
                rubric_effort=3,
            )

    def test_ausente_con_rubric_attitude_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="Lesión",
                rubric_attitude=4,
            )

    def test_ausente_con_rubric_technique_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="Examen",
                rubric_technique=2,
            )

    def test_ausente_con_individual_feedback_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="Gripa",
                individual_feedback="Buen esfuerzo virtual",
            )

    def test_justificado_con_rpe_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.JUSTIFICADO,
                excuse_reason="Evento escolar",
                rpe_omni=6,
            )

    def test_lesionado_con_rubric_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.LESIONADO,
                excuse_reason="Esguince",
                rubric_effort=2,
            )


# ---------------------------------------------------------------------------
# Casos de borde — valores límite de rúbrica
# ---------------------------------------------------------------------------


class TestAttendanceUpdateBoundaryValues:
    def test_rpe_por_debajo_de_cero_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.PRESENTE, rpe_omni=-1)

    def test_rpe_por_encima_de_diez_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.PRESENTE, rpe_omni=11)

    def test_rubric_cero_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.PRESENTE, rubric_effort=0)

    def test_rubric_seis_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.PRESENTE, rubric_attitude=6)

    def test_rubric_negativo_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.PRESENTE, rubric_technique=-1)

    def test_feedback_501_chars_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.PRESENTE,
                individual_feedback="A" * 501,
            )

    def test_excuse_reason_max_length_300(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.AUSENTE,
            excuse_reason="R" * 300,
        )
        assert len(a.excuse_reason) == 300

    def test_excuse_reason_301_falla(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="R" * 301,
            )
