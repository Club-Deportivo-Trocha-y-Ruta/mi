"""Pruebas de `render_sentence` y sus bloques de construcción (T032).

Cubre `contracts/audit-log-api.md` §7: el catálogo completo de plantillas
(§7.5), el algoritmo de resolución con degradación al genérico (§7.4), el
límite de 140 caracteres (§7.4) y `format_count_es` (§7.3). No requiere base
de datos: `render_sentence` es puro sobre cualquier objeto con los atributos
de `AuditLog`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.models.audit_log import AuditAction
from app.services.audit import (
    AUDIT_ACTION_VERBS,
    AUDIT_DOCUMENT_LABELS,
    AUDIT_ENTITY_LABELS,
    AuditDocumentKind,
    AuditEntityType,
    AuditReasonCode,
    SENTENCE_TEMPLATES,
    format_count_es,
    render_sentence,
)


@dataclass
class FakeAuditEntry:
    """Doble de prueba con los mismos atributos que `AuditLog` usa
    `render_sentence` (evita levantar la base de datos)."""

    entity_type: str
    action: AuditAction
    reason_code: str | None = None
    meta_json: dict[str, Any] | None = None
    diff_json: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# format_count_es (§7.3)
# ---------------------------------------------------------------------------


def test_format_count_es_singular() -> None:
    assert format_count_es(1) == "1 registro"


@pytest.mark.parametrize("n", [0, 2, 143])
def test_format_count_es_plural(n: int) -> None:
    assert format_count_es(n) == f"{n} registros"


# ---------------------------------------------------------------------------
# Cobertura íntegra del catálogo §7.5 — cada plantilla debe renderizar con
# datos representativos y respetar el límite de 140 caracteres.
# ---------------------------------------------------------------------------

_REPRESENTATIVE_META: dict[str, Any] = {
    "period": "2026-03",
    "document_kind": AuditDocumentKind.growth_pdf.value,
    "event_date": "2026-03-15",
    "role": "coach",
    "removed_count": 143,
}

_REPRESENTATIVE_DIFF: dict[str, Any] = {
    "scheduled_date": {"before": None, "after": "2026-03-15"},
    "start_at": {"before": None, "after": "2026-03-22T08:00:00"},
    "role": {"before": "parent", "after": "coach"},
    "role_in_club": {"before": "parent", "after": "coach"},
}


@pytest.mark.parametrize(("entity_type", "action"), list(SENTENCE_TEMPLATES.keys()))
def test_every_template_renders_with_representative_data(
    entity_type: AuditEntityType, action: AuditAction
) -> None:
    reason_code = None
    if "{motivo}" in SENTENCE_TEMPLATES[(entity_type, action)]:
        reason_code = AuditReasonCode.athlete_left_club.value
        if action == AuditAction.purge:
            reason_code = AuditReasonCode.retention_24m.value

    entry = FakeAuditEntry(
        entity_type=entity_type.value,
        action=action,
        reason_code=reason_code,
        meta_json=dict(_REPRESENTATIVE_META),
        diff_json=dict(_REPRESENTATIVE_DIFF),
    )

    sentence = render_sentence(entry, "Ana Coach")

    assert sentence.startswith("Ana Coach") or "Ana Coach" in sentence
    assert sentence.endswith(".")
    assert "{" not in sentence and "}" not in sentence
    assert "None" not in sentence
    assert len(sentence) <= 140


def test_template_catalogue_covers_documented_pairs() -> None:
    """§7.5 — pares clave del catálogo, verificados explícitamente."""
    assert (AuditEntityType.athlete, AuditAction.archive) in SENTENCE_TEMPLATES
    assert (AuditEntityType.audit_log, AuditAction.purge) in SENTENCE_TEMPLATES
    assert (AuditEntityType.user, AuditAction.role_change) in SENTENCE_TEMPLATES
    assert (AuditEntityType.club_member, AuditAction.delete) in SENTENCE_TEMPLATES


# ---------------------------------------------------------------------------
# Ejemplos puntuales del contrato (§7.5, columna "Rendered example")
# ---------------------------------------------------------------------------


def test_athlete_archive_with_reason() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.athlete.value,
        action=AuditAction.archive,
        reason_code=AuditReasonCode.athlete_left_club.value,
    )
    assert (
        render_sentence(entry, "Ana Coach")
        == "Ana Coach archivó la ficha de un deportista (Se retiró del club)."
    )


def test_anthropometric_record_create_with_event_date() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.anthropometric_record.value,
        action=AuditAction.create,
        meta_json={"event_date": "2026-03-14"},
    )
    assert (
        render_sentence(entry, "Ana Coach")
        == "Ana Coach registró una medición antropométrica del 14 de marzo de 2026."
    )


def test_training_session_cancel_with_scheduled_date_from_diff() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.training_session.value,
        action=AuditAction.cancel,
        reason_code=AuditReasonCode.cancel_weather.value,
        diff_json={"scheduled_date": {"before": None, "after": "2026-03-15"}},
    )
    assert (
        render_sentence(entry, "Beto Coach")
        == "Beto Coach canceló la sesión de entrenamiento del 15 de marzo de 2026 (Clima adverso)."
    )


def test_monthly_report_export_with_document_and_period() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.monthly_report.value,
        action=AuditAction.export,
        meta_json={
            "period": "2026-03",
            "document_kind": AuditDocumentKind.monthly_report_docx.value,
        },
    )
    assert (
        render_sentence(entry, "Ana Coach")
        == "Ana Coach descargó el informe mensual en DOCX de marzo de 2026."
    )


def test_user_create_with_role() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.user.value,
        action=AuditAction.create,
        meta_json={"role": "coach"},
    )
    assert render_sentence(entry, "Admin Club") == "Admin Club creó una cuenta de entrenador."


def test_club_member_role_change_uses_role_in_club_from_diff() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.club_member.value,
        action=AuditAction.role_change,
        diff_json={"role_in_club": {"before": "parent", "after": "coach"}},
    )
    assert (
        render_sentence(entry, "Admin Club")
        == "Admin Club cambió el rol en el club de una cuenta a entrenador."
    )


def test_audit_log_purge_singular_and_plural() -> None:
    plural = FakeAuditEntry(
        entity_type=AuditEntityType.audit_log.value,
        action=AuditAction.purge,
        reason_code=AuditReasonCode.retention_24m.value,
        meta_json={"removed_count": 143},
    )
    assert (
        render_sentence(plural, "Tarea programada")
        == "Tarea programada purgó 143 registros del historial (Retención: 24 meses cumplidos)."
    )

    singular = FakeAuditEntry(
        entity_type=AuditEntityType.audit_log.value,
        action=AuditAction.purge,
        reason_code=AuditReasonCode.retention_24m.value,
        meta_json={"removed_count": 1},
    )
    assert (
        render_sentence(singular, "Tarea programada")
        == "Tarea programada purgó 1 registro del historial (Retención: 24 meses cumplidos)."
    )


# ---------------------------------------------------------------------------
# Degradación al genérico (§7.4)
# ---------------------------------------------------------------------------


def test_unknown_pair_falls_back_to_generic() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.race_series.value,
        action=AuditAction.delete,  # sin plantilla dedicada
    )
    assert (
        render_sentence(entry, "Ana Coach")
        == "Ana Coach eliminó la serie de válidas."
    )


def test_missing_required_placeholder_falls_back_to_generic() -> None:
    """`(monthly_report, approve)` sin `meta_json.period` degrada al
    genérico en lugar de romper (§7.4, caso explícito del contrato)."""
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.monthly_report.value,
        action=AuditAction.approve,
        meta_json={},
    )
    assert (
        render_sentence(entry, "Ana Coach")
        == "Ana Coach aprobó el informe mensual del club."
    )


def test_missing_reason_code_falls_back_to_generic_sentence() -> None:
    entry = FakeAuditEntry(
        entity_type=AuditEntityType.athlete.value,
        action=AuditAction.archive,
        reason_code=None,
    )
    sentence = render_sentence(entry, "Ana Coach")
    assert sentence == "Ana Coach archivó la ficha del deportista."


def test_unknown_entity_type_falls_back_to_generic_without_crash() -> None:
    entry = FakeAuditEntry(entity_type="unknown_future_entity", action=AuditAction.create)
    sentence = render_sentence(entry, "Ana Coach")
    assert sentence.startswith("Ana Coach creó")
    assert sentence.endswith(".")


# ---------------------------------------------------------------------------
# Catálogos auxiliares — sanidad
# ---------------------------------------------------------------------------


def test_every_audit_action_has_a_verb() -> None:
    for action in AuditAction:
        assert action in AUDIT_ACTION_VERBS


def test_every_audit_entity_type_has_a_label() -> None:
    for entity_type in AuditEntityType:
        assert entity_type in AUDIT_ENTITY_LABELS


def test_every_document_kind_has_a_label() -> None:
    for kind in AuditDocumentKind:
        assert kind in AUDIT_DOCUMENT_LABELS
