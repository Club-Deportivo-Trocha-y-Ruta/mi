"""T203 — Tests para el email de la bitácora de etapa (feature 038) y el
despacho en ``newsletter_dispatcher.py``.

Cubre (spec: specs/038-newsletter-bitacora-redesign/tasks.md T203):
  - Tamaño del email ≤ 100 KB y ausencia de strings de antropometría, sobre
    las tres fixtures (mes completo, mes sin carrera, mes de cero
    asistencia) — ``stage_log`` ya en forma de ``to_parent_dto()``.
  - CTA "Ver la bitácora completa" (cuenta activa) vs "Activa tu cuenta"
    (invitación pendiente — ``hashed_password`` aún no definido).
  - Se escribe un evento ``sent`` en ``newsletter_delivery_events`` por
    destinatario, con ``provider_message_id`` solo cuando el proveedor es
    Resend (``None`` en SMTP — SMTP no da un id real del proveedor).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.newsletter_delivery_event import DeliveryEventType, NewsletterDeliveryEvent
from app.services.notification.email_client import ResendEmailClient
from app.services.notification.newsletter_dispatcher import (
    DispatchResult,
    _render_email_template,
    _send_for_parent,
)
from app.services.notification.template_registry import TemplateRegistry

# ---------------------------------------------------------------------------
# Fixtures de stage_log — ya en forma de to_parent_dto() (allow-list plana).
# ---------------------------------------------------------------------------


def _full_month_dto() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "stage_number": 6,
        "period_label": "Junio 2026",
        "is_current_month": False,
        "athlete_first_name": "Atleta",
        "athlete_reference": "su hijo",
        "stage_title": "Una etapa sólida con la mejor carrera de la temporada",
        "trail": [
            {"kind": "first_session", "date": "2026-06-02", "label": "Primera sesión de la temporada", "sublabel": None, "icon": "flag", "is_future": False},
            {"kind": "race", "date": "2026-06-15", "label": "Válida 3 · P2", "sublabel": "+4,1 % al P1", "icon": "map-pin", "is_future": False},
            {"kind": "next_race", "date": "2026-07-10", "label": "Próxima: Válida 4", "sublabel": "Ginebra", "icon": "compass", "is_future": True},
        ],
        "summit": {"kind": "race", "title": "P2 en la Válida 3", "detail": "Prejuvenil A Femenino · +4,1 % al P1", "caption": "Subió dos puestos.", "date": "2026-06-15"},
        "observations": [
            {"claim": "Asistió a 14 de 14 sesiones planificadas este mes.", "evidence": "14/14 sesiones (100 %).", "block_ref": "attendance"},
            {"claim": "Mejoró la frenada en curva cerrada.", "evidence": "Rúbrica técnica de 3,2 a 4,1.", "block_ref": "technical"},
            {"claim": "Logró su mejor resultado de la temporada.", "evidence": "P2, a 4,1 % del primer lugar.", "block_ref": "race"},
        ],
        "analyst_reading": {"headline_family": "Mantuvo el ritmo del grupo de punta.", "action_family": "Practicar la salida en pendiente.", "valida_label": "Válida 3 · Copa Valle"},
        "effort_profile": [{"week_label": "1–7 jun", "sessions_planned": 3, "sessions_attended": 3, "mean_rpe": 4.5}],
        "next_segment": {"focus_groups": ["Frenada"], "next_race": {"label": "Válida 4", "date": "2026-07-10", "venue": "Ginebra", "priority_label": "Prioridad A"}, "text": "Seguimos trabajando frenada."},
        "family_compass": {"conversation_question": "¿Qué fue lo que más disfrutó?", "monthly_challenge": "Practicar el calentamiento.", "what_to_watch": "Su confianza en curvas."},
        "badges": [{"code": "attendance_100", "label": "Asistencia 100 %", "icon": "award", "earned_at": "2026-06-20"}],
        "photos": [{"thumbnail_url": "https://cdn.example.com/photos/thumb1.jpg", "caption": "Entrenamiento"}],
        "coach_note": "Vamos muy bien este mes.",
    }


def _no_race_month_dto() -> dict[str, Any]:
    dto = _full_month_dto()
    dto.update(
        {
            "stage_title": "Un mes de trabajo de base sin carrera",
            "summit": {"kind": "training", "title": "Mejor sesión de entrenamiento del mes", "detail": None, "caption": "La mejor sesión técnica del mes.", "date": "2026-05-12"},
            "trail": [
                {"kind": "best_session", "date": "2026-05-12", "label": "Mejor sesión · técnica 4,5/5", "sublabel": None, "icon": "star", "is_future": False},
            ],
            "analyst_reading": None,
            "badges": [],
            "photos": [],
            "coach_note": None,
        }
    )
    return dto


def _zero_attendance_month_dto() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "stage_number": 2,
        "period_label": "Abril 2026",
        "is_current_month": False,
        "athlete_first_name": "Atleta",
        "athlete_reference": "su hijo/a",
        "stage_title": "Etapa de pausa",
        "trail": [
            {"kind": "next_race", "date": "2026-05-20", "label": "Próxima: Válida 2", "sublabel": "Palmira", "icon": "compass", "is_future": True},
        ],
        "summit": None,
        "observations": [],
        "analyst_reading": None,
        "effort_profile": [],
        "next_segment": {"focus_groups": [], "next_race": {"label": "Válida 2", "date": "2026-05-20", "venue": "Palmira", "priority_label": None}, "text": None},
        "family_compass": None,
        "badges": [],
        "photos": [],
        "coach_note": None,
    }


_FIXTURES = {
    "full_month": _full_month_dto,
    "no_race_month": _no_race_month_dto,
    "zero_attendance_month": _zero_attendance_month_dto,
}


def _to_coach_json(dto: dict[str, Any], *, source_insight_id: int = 99) -> dict[str, Any]:
    """``to_parent_dto()`` ya quita ``analyst_reading.source_insight_id`` (uso
    exclusivo del coach). ``AthleteMonthlyNewsletter.stage_log_json`` persiste
    la forma COMPLETA (vista coach) — este helper reconstruye esa forma a
    partir del dto de un fixture, para simular lo que ``build_stage_log()``
    realmente guarda en la columna (``_send_v2_email`` valida contra el
    ``StageLog`` completo antes de volver a proyectar con ``to_parent_dto``)."""
    coach = dict(dto)
    if coach.get("analyst_reading") is not None:
        coach["analyst_reading"] = {
            **coach["analyst_reading"],
            "source_insight_id": source_insight_id,
        }
    return coach

_ANTHROPOMETRY_STRINGS = ("antropometr", "z-score", "percentil", "phv", "maduración")


def _render(stage_log: dict[str, Any], *, cta_label: str = "Ver la bitácora completa") -> str:
    registry = TemplateRegistry()
    context = {
        "parent_name": "Familia Pérez",
        "club_name": "Trocha y Ruta",
        "month_label": stage_log.get("period_label") or "Junio 2026",
        "season_year": "2026",
        "children": [
            {
                "athlete_id": 1,
                "athlete_first_name": stage_log["athlete_first_name"],
                "stage_log": stage_log,
                "cta_url": "https://app.example.com/my-athletes/1/bitacora/10",
                "cta_label": cta_label,
            }
        ],
    }
    return _render_email_template(
        registry, context, body_path="email/athlete_stage_log.html"
    )


# ---------------------------------------------------------------------------
# Tamaño ≤ 100 KB y ausencia de antropometría, sobre las tres fixtures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name", list(_FIXTURES))
def test_email_size_within_budget(fixture_name):
    html = _render(_FIXTURES[fixture_name]())
    size_bytes = len(html.encode("utf-8"))
    assert size_bytes <= 100 * 1024, f"{fixture_name}: {size_bytes} bytes > 100 KB"


@pytest.mark.parametrize("fixture_name", list(_FIXTURES))
def test_email_never_mentions_anthropometry(fixture_name):
    import re

    html = _render(_FIXTURES[fixture_name]())
    # Los comentarios HTML del propio template explican (en prosa, para
    # desarrolladores) por qué NO hay antropometría — eso menciona la
    # palabra a propósito. Se descartan antes de revisar el contenido
    # visible, que es lo que Ley 1581 protege (nunca llega a la familia).
    visible_html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html_lower = visible_html.lower()
    for needle in _ANTHROPOMETRY_STRINGS:
        assert needle not in html_lower, f"{fixture_name}: found forbidden term '{needle}'"


def test_email_renders_trail_and_cta():
    html = _render(_full_month_dto())
    assert "Ruta del mes" in html
    assert "Válida 3 · P2" in html
    assert "Ver la bitácora completa" in html


def test_email_cta_activate_account_label_renders():
    html = _render(_zero_attendance_month_dto(), cta_label="Activa tu cuenta")
    assert "Activa tu cuenta" in html


def test_email_header_does_not_duplicate_year():
    """``month_label`` ya trae el año (p.ej. ``_month_label()`` produce
    "Junio 2026") — el encabezado no debe volver a concatenar
    ``season_year`` o el padre ve "Junio 2026 2026" (bug real hallado en QA
    manual del feature 038, 2026-09-03)."""
    html = _render(_full_month_dto())
    assert "Junio 2026 2026" not in html
    assert "Bitácora de etapa — Junio 2026" in html


# ---------------------------------------------------------------------------
# Despacho — _send_for_parent
# ---------------------------------------------------------------------------


def _make_v2_newsletter(
    id_: int,
    athlete_id: int,
    stage_log_json: dict[str, Any],
    year: int = 2026,
    month: int = 6,
) -> Any:
    return SimpleNamespace(
        id=id_,
        athlete_id=athlete_id,
        year=year,
        month=month,
        stage_log_json=stage_log_json,
        hidden_blocks=None,
        status="approved",
        sent_at=None,
        sent_to=None,
    )


def _make_parent(has_account: bool) -> Any:
    return SimpleNamespace(
        id=20,
        email="padre@test.com",
        first_name="Padre",
        hashed_password="hash" if has_account else None,
    )


def _make_athlete(id_: int, first_name: str = "Atleta") -> Any:
    return SimpleNamespace(id=id_, first_name=first_name, last_name="Test", club_id=1, sex="M")


def _make_db_for_send(parent: Any, athlete_by_id: dict[int, Any]) -> Any:
    """DB stub: primero resuelve el padre, luego un Athlete por cada nl."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    calls: list[Any] = []

    async def execute(stmt):
        # Primera llamada de _send_for_parent: select(User) (padre).
        if not calls:
            calls.append("parent")
            result = MagicMock()
            result.scalar_one_or_none.return_value = parent
            return result
        # Llamadas siguientes: select(Athlete) — una por newsletter, en el
        # orden en que aparecen en la lista `newsletters`.
        idx = len(calls) - 1
        athlete = list(athlete_by_id.values())[idx]
        calls.append(f"athlete-{athlete.id}")
        result = MagicMock()
        result.scalar_one_or_none.return_value = athlete
        return result

    db.execute = execute
    return db


def make_registry() -> Any:
    registry = MagicMock()
    spec = MagicMock()
    spec.subject_template = "Bitácora {{ month_label }} — {{ club_name }}"
    registry.get_email_spec.return_value = spec
    return registry


def make_email_client(success: bool = True, message_id: str | None = "smtp-x") -> Any:
    client = MagicMock()
    result = MagicMock()
    result.success = success
    result.error = None if success else "SMTP error"
    result.message_id = message_id
    client.send = AsyncMock(return_value=result)
    return client


async def test_v2_only_send_uses_stage_log_template_and_writes_sent_event():
    nl = _make_v2_newsletter(id_=1, athlete_id=5, stage_log_json=_to_coach_json(_full_month_dto()))
    athlete = _make_athlete(5)
    parent = _make_parent(has_account=True)
    db = _make_db_for_send(parent, {5: athlete})
    email_client = make_email_client()
    result = DispatchResult()

    sent_ids = await _send_for_parent(
        db=db,
        email_client=email_client,
        registry=make_registry(),
        parent_id=20,
        newsletters=[nl],
        force_individual=True,
        result=result,
    )

    assert sent_ids == [1]
    assert nl.status == "sent"

    sent_msg = email_client.send.call_args.args[0]
    assert sent_msg.template_ref == "athlete_stage_log"
    assert "Ver la bitácora completa" in sent_msg.html_body

    # Un NewsletterDeliveryEvent(sent) por destinatario, con
    # provider_message_id=None (SMTP no da un id real del proveedor).
    added = [c.args[0] for c in db.add.call_args_list if c.args]
    delivery_events = [a for a in added if isinstance(a, NewsletterDeliveryEvent)]
    assert len(delivery_events) == 1
    assert delivery_events[0].newsletter_id == 1
    assert delivery_events[0].event_type == DeliveryEventType.sent
    assert delivery_events[0].provider_message_id is None


async def test_v2_send_via_resend_persists_provider_message_id():
    nl = _make_v2_newsletter(id_=1, athlete_id=5, stage_log_json=_to_coach_json(_full_month_dto()))
    athlete = _make_athlete(5)
    parent = _make_parent(has_account=True)
    db = _make_db_for_send(parent, {5: athlete})

    resend_client = MagicMock(spec=ResendEmailClient)
    send_result = MagicMock()
    send_result.success = True
    send_result.message_id = "re_abc123"
    resend_client.send = AsyncMock(return_value=send_result)

    result = DispatchResult()
    await _send_for_parent(
        db=db,
        email_client=resend_client,
        registry=make_registry(),
        parent_id=20,
        newsletters=[nl],
        force_individual=True,
        result=result,
    )

    added = [c.args[0] for c in db.add.call_args_list if c.args]
    delivery_events = [a for a in added if isinstance(a, NewsletterDeliveryEvent)]
    assert delivery_events[0].provider_message_id == "re_abc123"


async def test_v2_cta_is_activate_account_without_hashed_password():
    nl = _make_v2_newsletter(id_=1, athlete_id=5, stage_log_json=_zero_attendance_month_dto())
    athlete = _make_athlete(5)
    parent = _make_parent(has_account=False)
    db = _make_db_for_send(parent, {5: athlete})
    email_client = make_email_client()
    result = DispatchResult()

    await _send_for_parent(
        db=db,
        email_client=email_client,
        registry=make_registry(),
        parent_id=20,
        newsletters=[nl],
        force_individual=True,
        result=result,
    )

    sent_msg = email_client.send.call_args.args[0]
    assert "Activa tu cuenta" in sent_msg.html_body
    assert "/onboarding" in sent_msg.html_body


async def test_two_children_same_parent_send_two_separate_emails():
    """Un padre con boletines de dos hijos del mismo periodo recibe dos
    correos — uno por atleta."""
    nl_1 = _make_v2_newsletter(id_=1, athlete_id=5, stage_log_json=_to_coach_json(_full_month_dto()))
    nl_2 = _make_v2_newsletter(id_=2, athlete_id=6, stage_log_json=_to_coach_json(_no_race_month_dto()))
    athlete_1 = _make_athlete(5, first_name="Hijo1")
    athlete_2 = _make_athlete(6, first_name="Hijo2")
    parent = _make_parent(has_account=True)
    db = _make_db_for_send(parent, {5: athlete_1, 6: athlete_2})
    email_client = make_email_client()
    result = DispatchResult()

    sent_ids = await _send_for_parent(
        db=db,
        email_client=email_client,
        registry=make_registry(),
        parent_id=20,
        newsletters=[nl_1, nl_2],
        force_individual=True,
        result=result,
    )

    assert sorted(sent_ids) == [1, 2]
    assert email_client.send.call_count == 1
    sent_msg = email_client.send.call_args.args[0]
    assert sent_msg.template_ref == "athlete_stage_log"

    added = [c.args[0] for c in db.add.call_args_list if c.args]
    delivery_events = [a for a in added if isinstance(a, NewsletterDeliveryEvent)]
    assert {e.newsletter_id for e in delivery_events} == {1, 2}
