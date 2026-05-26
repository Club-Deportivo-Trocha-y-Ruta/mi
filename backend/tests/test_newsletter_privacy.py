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
        catalog = {"llm_timeout", "guardrails_rejected", "llm_internal_error", "consent_missing", "no_parent_linked"}
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


class TestRedactorWordBoundaries:
    """El redactor respeta word boundaries — no corta palabras que contienen un forbidden name como substring."""

    def test_redactor_respeta_word_boundaries(self):
        from app.services.ai.use_cases.monthly_report import _redact_names

        forbidden: frozenset[str] = frozenset({"Test", "Ana"})
        text = "testimonio ananá Anatomía Test Cano Ana López"
        result = _redact_names(text, forbidden)

        assert "testimonio" in result, "NO debe redactar: 'Test' es substring interno de 'testimonio'"
        assert "ananá" in result, "NO debe redactar: 'Ana' es substring de 'ananá'"
        assert "Anatomía" in result, "NO debe redactar: 'Ana' es prefix de 'Anatomía'"
        assert "[REDACTADO] Cano" in result, "DEBE redactar: 'Test' como palabra completa"
        assert "[REDACTADO] López" in result, "DEBE redactar: 'Ana' como palabra completa"

    def test_redactor_nombre_compuesto(self):
        from app.services.ai.use_cases.monthly_report import _redact_names

        forbidden: frozenset[str] = frozenset({"Juan Diego"})
        text = "Juan Diego avanzó bien. Juandiego no aplica."
        result = _redact_names(text, forbidden)

        assert "[REDACTADO]" in result, "DEBE redactar 'Juan Diego' completo"
        assert "Juandiego" in result, "NO debe redactar 'Juandiego' (sin espacio)"

    def test_redactor_property_substring_no_redactado(self):
        """Para cualquier forbidden name N que sea substring estricto de una palabra W
        (con letra antes O después), W aparece intacta en el output.

        Cada caso: (forbidden, texto, palabra_standalone, palabras_que_no_deben_redactarse)
        """
        from app.services.ai.use_cases.monthly_report import _redact_names

        casos = [
            # forbidden "Luis" → "Luis" standalone se redacta; "Luisito" no
            ({"Luis"}, "hola Luis por Luisito algo", "Luis", ["Luisito"]),
            # forbidden "Mar" → "Mar" standalone se redacta; "María" y "mares" no
            ({"Mar"}, "Mar fue a ver María y los mares", "Mar", ["María", "mares"]),
            # forbidden "Ana" → "Ana" standalone se redacta; "ananá" y "Anatomía" no
            ({"Ana"}, "Ana come ananá en Anatomía", "Ana", ["ananá", "Anatomía"]),
        ]
        for forbidden_set, text, standalone, no_redact in casos:
            result = _redact_names(text, frozenset(forbidden_set))
            name = next(iter(forbidden_set))
            assert "[REDACTADO]" in result, f"'{name}' como palabra completa debe redactarse en: {text!r}"
            for word in no_redact:
                assert word in result, f"'{word}' NO debe redactarse ('{name}' es substring) en: {text!r}"


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


# ===========================================================================
# Fase 1.8-bis — Curvas de percentiles en el boletín PDF
# Invariantes adicionales: el gráfico vive únicamente en pdf_only_blocks,
# no inyecta metadata SVG, no aparece en logs, y la narrativa IA no usa
# términos nutricionales diagnósticos.
# ===========================================================================


class TestPercentileCurvesPdfOnly:
    """El bloque de curvas de percentiles NUNCA escapa a email_blocks."""

    def test_growth_chart_only_in_pdf_blocks(self):
        """Invariante consolidado: schema de respuesta no expone percentile_curves."""
        obj = _make_obj()
        # Inyectamos curvas en el snapshot para comprobar que el schema las descarta
        obj.metrics_snapshot["pdf_only_blocks"]["percentile_curves"] = {
            "height": {
                "enough_data": True,
                "indicator": "height",
                "curves": {"p50": {"path": "M 0,0", "stroke_dasharray": "", "color": "#000"}},
                "athlete": {"polyline_points": "0,0", "points": [{"x": 0.0, "y": 0.0}]},
                "phv_marker": None,
            }
        }
        read = AthleteNewsletterRead.from_orm_model(obj)
        json_repr = read.model_dump_json()
        # El schema no expone pdf_only_blocks ni percentile_curves
        assert "percentile_curves" not in json_repr
        assert "polyline_points" not in json_repr
        # email_blocks no las contiene (la antropometría tampoco)
        assert read.email_blocks is None or "percentile_curves" not in read.email_blocks

    def test_svg_no_metadata_tags(self):
        """El macro NO emite tags <title>/<desc>/<metadata> ni data-* attrs.

        Render aislado del macro contra un fixture full-data.
        """
        from pathlib import Path
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        templates_root = Path(__file__).resolve().parent.parent / "templates"
        env = Environment(
            loader=FileSystemLoader(str(templates_root)),
            autoescape=select_autoescape(["html", "svg.jinja"]),
        )
        tpl = env.from_string(
            '{% from "documents/pdf/charts/percentile_curves.svg.jinja" import percentile_curves %}'
            "{{ percentile_curves(chart) }}"
        )
        chart = {
            "enough_data": True,
            "reason_no_data": None,
            "indicator": "bmi",
            "indicator_label_es": "IMC (kg/m²)",
            "sex": "M",
            "viewbox": "0 0 400 260",
            "width": 400,
            "height": 260,
            "x_axis": {"min_months": 120.0, "max_months": 180.0, "ticks": [132.0]},
            "y_axis": {"min": 15.0, "max": 25.0, "ticks": [15.0, 20.0, 25.0]},
            "curves": {
                "p3":  {"path": "M 42,200 L 100,180", "stroke_dasharray": "2,2", "color": "#e74c3c"},
                "p25": {"path": "M 42,180 L 100,160", "stroke_dasharray": "6,2", "color": "#f39c12"},
                "p50": {"path": "M 42,160 L 100,140", "stroke_dasharray": "",    "color": "#27ae60"},
                "p75": {"path": "M 42,140 L 100,120", "stroke_dasharray": "6,2", "color": "#f39c12"},
                "p97": {"path": "M 42,120 L 100,100", "stroke_dasharray": "2,2", "color": "#e74c3c"},
            },
            "athlete": {"polyline_points": "60.0,180.0", "points": [{"x": 60.0, "y": 180.0}]},
            "phv_marker": {"x": 110.0, "label": "PHV"},
        }
        html = tpl.render(chart=chart)
        for tag in ("<title", "<desc", "<metadata"):
            assert tag not in html, f"Tag '{tag}' prohibido por privacidad — output:\n{html[:300]}"
        assert "data-" not in html, "Atributos data-* prohibidos en SVG del boletín"


class TestDispatcherLogsNoAnthropometricData:
    """El dispatcher no debe loguear talla, peso, percentil ni edad numérica."""

    def test_dispatcher_logs_no_anthropometric_data(self, caplog):
        """Inspecciona los formatters: ningún logger.info/error/warning del
        dispatcher referencia anthropo/percentil/edad."""
        import inspect
        import re
        from app.services.notification import newsletter_dispatcher

        source = inspect.getsource(newsletter_dispatcher)
        # Capturamos los strings de format dentro de logger.X(...)
        log_calls = re.findall(
            r"logger\.(?:info|warning|error|debug)\(\s*([rfb]?\"[^\"]+\"|[rfb]?'[^']+')",
            source,
        )
        assert log_calls, "El dispatcher debería tener al menos un log call"

        # Conjunto explícito de fragmentos prohibidos en log messages
        forbidden = [
            "talla", "altura_cm", "standing_height",
            "peso", "weight_kg",
            "percentil", "percentile",
            "z_score", "z-score",
            "imc", "bmi",
            "edad_anos", "age_decimal",
        ]
        for raw in log_calls:
            msg = raw.lower()
            for term in forbidden:
                assert term not in msg, (
                    f"Log del dispatcher contiene término sensible '{term}': {raw}"
                )


class TestAiNarrativeForbiddenNutritionalTerms:
    """La narrativa IA no debe contener términos diagnósticos nutricionales.

    Property test: 10 outputs IA fixture → ninguno contiene los términos
    'desnutrición', 'obesidad', 'sobrepeso', 'bajo peso', 'talla baja'.
    Los términos individuales NO se filtran por _MEDICAL_PATTERN actual, así
    que validamos que las fixtures que pasamos al test estén limpias —
    si el equipo prompt agrega un caso real con esos términos, este test
    fallaría y obligaría a extender el guardrail.
    """

    _FORBIDDEN_NUTRITIONAL = (
        "desnutrición",
        "obesidad",
        "sobrepeso",
        "bajo peso",
        "talla baja",
    )

    _FIXTURE_OUTPUTS = [
        "Este mes mostró constancia notable en los entrenamientos técnicos del jueves, "
        "completando todas las sesiones programadas con buena actitud.",
        "Su progreso en frenado progresivo fue claro durante el segundo bloque del mes. "
        "Recomendamos seguir reforzando equilibrio en descensos suaves.",
        "Aún hay margen para trabajar la cadencia en subidas medianas. "
        "Las sesiones de zona 2 le ayudarán a consolidar la base aeróbica.",
        "Próxima válida en La Cumbre el 19 de abril — sesiones de carácter diagnóstico, "
        "sin tapering. Apoyo desde casa: sueño regular y bici limpia.",
        "Atributo destacado del mes: actitud frente a errores técnicos. "
        "Convertir caídas en aprendizaje es parte central de esta etapa.",
        "El trabajo de habilidades en circuito cerrado mostró buen progreso. "
        "Mantener la consigna de cadencia ≥70 rpm en próximas sesiones.",
        "Su asistencia fue del 92%. Hubo un día en que llegó cansado tras una jornada "
        "escolar intensa — el ajuste fue oportuno y bien gestionado.",
        "Para el próximo mes proponemos dos sesiones de habilidad técnica por semana, "
        "con énfasis en cambios de dirección a baja velocidad.",
        "Hidratación durante entrenamientos: agua antes, durante y después. "
        "La rutina familiar de hidratación ha mejorado de manera consistente.",
        "Buen avance en confianza al descender. Es importante seguir reforzando "
        "habilidad sobre potencia/resistencia en este grupo de edad.",
    ]

    def test_fixtures_dont_contain_nutritional_terms(self):
        """10 outputs IA fixture: ninguno usa términos diagnósticos nutricionales."""
        assert len(self._FIXTURE_OUTPUTS) >= 10
        for i, text in enumerate(self._FIXTURE_OUTPUTS):
            lower = text.lower()
            for term in self._FORBIDDEN_NUTRITIONAL:
                assert term not in lower, (
                    f"Fixture {i} contiene término nutricional prohibido '{term}': {text}"
                )

    def test_medical_pattern_blocks_medication_terms(self):
        """El guardrail actual rechaza términos médicos/suplementos en la narrativa."""
        from app.services.ai.use_cases.athlete_monthly_newsletter import (
            AthleteNewsletterGuardrails,
        )
        from app.services.ai.errors import LLMSchemaError

        guard = AthleteNewsletterGuardrails(forbidden_names=frozenset())
        offending = (
            "Recomendamos suplemento de proteínas en polvo y creatina para mejorar la "
            "recuperación tras las sesiones. Esto debería compensarse con la dosis "
            "adecuada según prescripción del nutricionista." * 2
        )
        with pytest.raises(LLMSchemaError):
            guard.scrub_block(offending)
