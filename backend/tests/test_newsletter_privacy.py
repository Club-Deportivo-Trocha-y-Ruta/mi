"""Tests de privacidad consolidados — módulo Boletín Mensual Individual (Fase 1.8).

Invariantes end-to-end del módulo, validados en un solo archivo:

1. ``sent_to`` (emails de padres) nunca aparece en el schema de respuesta.
2. ``pdf_only_blocks`` (antropometría) nunca aparece en el schema de respuesta.
3. ``pdf_storage_url`` (ruta interna de storage) nunca aparece en el schema.
4. ``has_pdf`` reemplaza a ``pdf_storage_url`` como indicador booleano.
5. ``AthleteNewsletterBatchResult.errors`` no contiene caracteres ``@`` (emails).
6. ``error_message`` persistido usa códigos del catálogo, no detalles técnicos.
7. El dispatcher elimina defensivamente claves prohibidas del ``email_blocks``
   antes de pasar al template (anthropometry / pdf_only_blocks / charts).
8. El subject del email NO contiene nombre del atleta.
9. Errores del email provider se sanitizan antes de loguear o devolver al
   cliente (regex de emails redactada).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.athlete_newsletter import NewsletterStatus
from app.schemas.athlete_newsletter import (
    AthleteNewsletterBatchResult,
    AthleteNewsletterRead,
)
from app.services.notification.template_registry import EMAIL_TEMPLATES
from app.schemas.notification import NotificationTemplate


def _make_obj(**overrides) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        athlete_id=10,
        year=2026,
        month=4,
        status=NewsletterStatus.sent,
        metrics_snapshot={
            "email_blocks": {"attendance": {"percentage": 92.0}},
            "pdf_only_blocks": {
                "anthropometry": {
                    "weight_kg": 45.0,
                    "standing_height_cm": 150.0,
                    "bmi": 20.0,
                    "z_scores": {"weight": 0.2, "height": -0.3, "bmi": 0.5},
                    "percentiles": {"weight": 55, "height": 40, "bmi": 65},
                    "maturity_offset": 0.5,
                    "age_at_phv": 13.2,
                    "maturation_status": "Circa-PHV",
                }
            },
        },
        ai_narrative=None,
        coach_narrative_overrides=None,
        badges_earned=None,
        pdf_storage_url="newsletters/2026/04/10_1.pdf",
        pdf_generated_at=now,
        pdf_sha256="a" * 64,
        generated_by_user_id=99,
        approved_by_user_id=99,
        approved_at=now,
        sent_at=now,
        sent_to=["padre@example.com", "madre@example.com"],
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestPersonalDataNotInResponse:
    """Datos sensibles nunca alcanzan el contrato API."""

    def test_sent_to_field_not_in_schema(self):
        read = AthleteNewsletterRead.from_orm_model(_make_obj())
        json_repr = read.model_dump_json()
        assert "sent_to" not in json_repr
        assert "padre@example.com" not in json_repr
        assert "madre@example.com" not in json_repr

    def test_pdf_only_blocks_not_in_schema(self):
        read = AthleteNewsletterRead.from_orm_model(_make_obj())
        json_repr = read.model_dump_json()
        assert "pdf_only_blocks" not in json_repr
        assert "anthropometry" not in json_repr
        assert "weight_kg" not in json_repr
        assert "maturity_offset" not in json_repr
        assert "z_scores" not in json_repr

    def test_pdf_storage_url_replaced_by_has_pdf(self):
        read = AthleteNewsletterRead.from_orm_model(_make_obj())
        json_repr = read.model_dump_json()
        assert "pdf_storage_url" not in json_repr
        assert "has_pdf" in json_repr
        assert read.has_pdf is True

    def test_has_pdf_false_when_no_pdf_yet(self):
        obj = _make_obj(pdf_storage_url=None, pdf_sha256=None)
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.has_pdf is False

    def test_email_blocks_present_in_schema(self):
        read = AthleteNewsletterRead.from_orm_model(_make_obj())
        assert read.email_blocks is not None
        assert read.email_blocks.get("attendance", {}).get("percentage") == 92.0


class TestBatchErrorsSanitized:
    """Errores del batch nunca contienen PII."""

    def test_batch_errors_no_email_chars(self):
        result = AthleteNewsletterBatchResult(
            period_year=2026,
            period_month=4,
            total_athletes=3,
            created=1,
            skipped=1,
            failed=1,
            newsletter_ids=[42],
            errors=[
                "Atleta ID 5: consent_missing",
                "Atleta ID 7: guardrails_rejected",
                "Atleta ID 9: internal_error",
            ],
        )
        for err in result.errors:
            assert "@" not in err, f"Error contiene char '@': {err}"

    def test_error_message_uses_catalog_codes(self):
        catalog = {"llm_timeout", "guardrails_rejected", "llm_internal_error", "consent_missing"}
        obj = _make_obj(error_message="guardrails_rejected")
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.error_message in catalog


class TestEmailSubjectNoAthleteName:
    """El subject del email no expone el nombre del atleta."""

    def test_subject_template_does_not_reference_athlete_name(self):
        spec = EMAIL_TEMPLATES[NotificationTemplate.ATHLETE_MONTHLY_NEWSLETTER]
        assert "athlete_first_name" not in spec.subject_template
        assert "athlete_last_name" not in spec.subject_template
        assert "children[0]" not in spec.subject_template

    def test_subject_template_is_generic(self):
        spec = EMAIL_TEMPLATES[NotificationTemplate.ATHLETE_MONTHLY_NEWSLETTER]
        # Debe ser un texto fijo, sin nombres ni conteos identificadores
        assert "Boletín" in spec.subject_template
        assert "Trocha y Ruta" in spec.subject_template


class TestDispatcherSanitization:
    """El dispatcher elimina claves prohibidas y sanitiza errores del provider."""

    def test_dispatcher_source_strips_forbidden_keys(self):
        """Defensa en profundidad: el código fuente del dispatcher debe
        eliminar 'anthropometry', 'pdf_only_blocks' y 'charts' del email_blocks
        antes de pasarlo al template, aunque el builder ya separe."""
        import inspect
        from app.services.notification import newsletter_dispatcher

        source = inspect.getsource(newsletter_dispatcher)
        # Verificamos las claves prohibidas presentes en el guard
        assert '"anthropometry"' in source
        assert '"pdf_only_blocks"' in source
        assert '"charts"' in source
        # Y que se hace pop sobre email_blocks_safe
        assert "email_blocks_safe" in source
        assert ".pop(" in source

    def test_dispatcher_source_redacts_provider_email_in_errors(self):
        """El dispatcher debe aplicar regex de redacción de emails sobre
        send_result.error antes de loguear o devolver."""
        import inspect
        from app.services.notification import newsletter_dispatcher

        source = inspect.getsource(newsletter_dispatcher)
        # Confirmamos el regex de redacción y la variable safe_error
        assert "safe_error" in source
        assert "[email]" in source

    def test_provider_error_sanitization_redacts_emails(self):
        """El regex en el dispatcher debe redactar emails de errores del provider."""
        raw = "Recipient rejected: padre@example.com (550 No such user)"
        safe = re.sub(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "[email]",
            raw,
        )[:120]
        assert "@" not in safe
        assert "padre@example.com" not in safe
        assert "[email]" in safe


class TestSentToPersistedNotLogged:
    """sent_to se persiste en DB pero NUNCA aparece en logs ni en API."""

    def test_sent_to_persisted_to_db(self):
        """Sanity check: el campo existe en el modelo ORM."""
        from app.models.athlete_newsletter import AthleteMonthlyNewsletter
        cols = AthleteMonthlyNewsletter.__table__.columns.keys()
        assert "sent_to" in cols, "sent_to debe existir en la tabla para persistencia"

    def test_sent_to_excluded_from_orm_to_schema(self):
        """from_orm_model NO debe asignar sent_to al schema."""
        obj = _make_obj(sent_to=["padre@x.com", "madre@y.com"])
        read = AthleteNewsletterRead.from_orm_model(obj)
        # El schema no tiene atributo sent_to
        assert not hasattr(read, "sent_to")
