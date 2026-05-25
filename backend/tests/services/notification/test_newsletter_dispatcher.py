"""Tests para newsletter_dispatcher.py.

Cubre:
- Agrupa newsletters por padre correctamente (multi-hijo)
- Idempotencia: newsletters ya sent se omiten (newsletters_skipped)
- Bloqueo si hermano en draft del mismo periodo (newsletters_blocked)
- force_individual=True omite la verificación de hermanos
- force_resend=True reenvía aunque ya esté sent
- Sin padres vinculados → newsletter omitido
- Lista vacía → DispatchResult vacío
- Newsletter no aprobado (draft) → blocked por estado
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.athlete_newsletter import NewsletterStatus
from app.services.notification.newsletter_dispatcher import (
    DispatchResult,
    dispatch_newsletters,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db() -> Any:
    sess = MagicMock()
    sess.execute = AsyncMock()
    sess.flush = AsyncMock()
    sess.commit = AsyncMock()
    sess.add = MagicMock()
    return sess


def make_scalars_result(items: list) -> Any:
    result = MagicMock()
    result.scalars.return_value = result
    result.all.return_value = items
    result.scalar_one_or_none.return_value = items[0] if items else None
    return result


def make_newsletter(
    id_: int,
    athlete_id: int,
    year: int = 2026,
    month: int = 3,
    status: NewsletterStatus = NewsletterStatus.approved,
    metrics_snapshot: dict | None = None,
    ai_narrative: dict | None = None,
) -> Any:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=id_,
        athlete_id=athlete_id,
        year=year,
        month=month,
        status=status,
        metrics_snapshot=metrics_snapshot or {"email_blocks": {}, "pdf_only_blocks": {}},
        ai_narrative=ai_narrative,
        coach_narrative_overrides=None,
        badges_earned=None,
        pdf_storage_url=None,
        pdf_sha256=None,
        sent_at=None,
        sent_to=None,
        created_at=now,
        updated_at=now,
        error_message=None,
    )


def make_parent_athlete(parent_id: int, athlete_id: int) -> Any:
    return SimpleNamespace(parent_id=parent_id, athlete_id=athlete_id)


def make_user(id_: int, email: str = "padre@test.com", first_name: str = "Padre") -> Any:
    return SimpleNamespace(id=id_, email=email, first_name=first_name)


def make_athlete(id_: int, first_name: str = "Atleta") -> Any:
    return SimpleNamespace(id=id_, first_name=first_name, last_name="Test", club_id=1)


def make_email_client(success: bool = True) -> Any:
    client = MagicMock()
    result = MagicMock()
    result.success = success
    result.error = None if success else "SMTP error"
    client.send = AsyncMock(return_value=result)
    return client


def make_registry() -> Any:
    registry = MagicMock()
    spec = MagicMock()
    spec.subject_template = "Boletín {{ month_label }} — {{ club_name }}"
    registry.get_email_spec.return_value = spec
    return registry


# ---------------------------------------------------------------------------
# Test: lista vacía de IDs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_newsletter_ids_returns_empty_result():
    db = make_db()
    email_client = make_email_client()
    registry = make_registry()

    result = await dispatch_newsletters(
        db=db,
        email_client=email_client,
        registry=registry,
        newsletter_ids=[],
    )

    assert isinstance(result, DispatchResult)
    assert result.newsletters_sent == []
    assert result.emails_sent == 0
    # No hubo consultas a DB
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Test: newsletter ya sent → omitido (idempotencia)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_sent_skipped_by_default():
    db = make_db()
    nl = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.sent)

    db.execute = AsyncMock(return_value=make_scalars_result([nl]))

    result = await dispatch_newsletters(
        db=db,
        email_client=make_email_client(),
        registry=make_registry(),
        newsletter_ids=[1],
    )

    assert 1 in result.newsletters_skipped
    assert result.emails_sent == 0


@pytest.mark.asyncio
async def test_force_resend_overrides_skip():
    """force_resend=True reenvía newsletters ya sent."""
    db = make_db()
    nl = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.sent)
    parent_athlete = make_parent_athlete(parent_id=20, athlete_id=5)
    parent = make_user(id_=20)
    athlete = make_athlete(id_=5)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Select newsletters
            return make_scalars_result([nl])
        elif call_count == 2:
            # ParentAthlete (group_by_parent)
            return make_scalars_result([parent_athlete])
        elif call_count == 3:
            # _check_sibling_newsletters: select(ParentAthlete.athlete_id)
            # athlete 5 es el único y está siendo enviado → other_athlete_ids vacío
            # → sin segunda query, retorna [] inmediatamente
            return make_scalars_result([5])
        elif call_count == 4:
            # User (parent) — sibling newsletter query omitida
            return make_scalars_result([parent])
        elif call_count == 5:
            # Athlete data
            return make_scalars_result([athlete])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    with patch(
        "app.services.notification.newsletter_dispatcher._render_email_template",
        return_value="<html>email</html>",
    ), patch(
        "app.services.notification.newsletter_dispatcher._render_subject",
        return_value="Boletín Marzo 2026",
    ):
        result = await dispatch_newsletters(
            db=db,
            email_client=make_email_client(success=True),
            registry=make_registry(),
            newsletter_ids=[1],
            force_resend=True,
        )

    # El newsletter ya sent debe ser procesado (no omitido)
    assert 1 not in result.newsletters_skipped


# ---------------------------------------------------------------------------
# Test: newsletter en draft → blocked por estado (no aprobado)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_newsletter_blocked_by_status():
    db = make_db()
    nl = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.draft)

    db.execute = AsyncMock(return_value=make_scalars_result([nl]))

    result = await dispatch_newsletters(
        db=db,
        email_client=make_email_client(),
        registry=make_registry(),
        newsletter_ids=[1],
    )

    assert 1 in result.newsletters_blocked
    assert result.emails_sent == 0


# ---------------------------------------------------------------------------
# Test: agrupación multi-hijo por padre
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_groups_multiple_children_for_same_parent():
    """Dos atletas del mismo padre se agrupan en un solo email."""
    db = make_db()
    nl1 = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.approved)
    nl2 = make_newsletter(id_=2, athlete_id=6, status=NewsletterStatus.approved)

    parent_athletes = [
        make_parent_athlete(parent_id=20, athlete_id=5),
        make_parent_athlete(parent_id=20, athlete_id=6),
    ]
    parent = make_user(id_=20)
    athlete1 = make_athlete(id_=5, first_name="Ana")
    athlete2 = make_athlete(id_=6, first_name="Carlos")

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([nl1, nl2])
        elif call_count == 2:
            # ParentAthlete group_by_parent
            return make_scalars_result(parent_athletes)
        elif call_count == 3:
            # sibling check: select(ParentAthlete.athlete_id) para parent 20
            # Ambos atletas (5 y 6) están siendo enviados → other_athlete_ids vacío
            # → _check_sibling_newsletters retorna [] sin segunda query
            # → siguiente call es User
            return make_scalars_result([5, 6])
        elif call_count == 4:
            # User (parent) — la query de sibling newsletters se omite
            # porque other_athlete_ids está vacío
            return make_scalars_result([parent])
        elif call_count == 5:
            # Athlete data nl1
            return make_scalars_result([athlete1])
        elif call_count == 6:
            # Athlete data nl2
            return make_scalars_result([athlete2])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    with patch(
        "app.services.notification.newsletter_dispatcher._render_email_template",
        return_value="<html>email</html>",
    ), patch(
        "app.services.notification.newsletter_dispatcher._render_subject",
        return_value="Boletín Marzo 2026",
    ):
        result = await dispatch_newsletters(
            db=db,
            email_client=make_email_client(success=True),
            registry=make_registry(),
            newsletter_ids=[1, 2],
        )

    # Debe haber enviado 1 email con 2 hijos
    assert result.emails_sent == 1
    assert 1 in result.newsletters_sent
    assert 2 in result.newsletters_sent


# ---------------------------------------------------------------------------
# Test: bloqueo si hermano en draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_if_sibling_in_draft():
    """Si el padre tiene otro atleta con newsletter en draft, se bloquea."""
    db = make_db()
    nl_approved = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.approved)
    nl_draft_sibling = make_newsletter(id_=99, athlete_id=6, status=NewsletterStatus.draft)

    parent_athlete = make_parent_athlete(parent_id=20, athlete_id=5)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Select newsletters to dispatch
            return make_scalars_result([nl_approved])
        elif call_count == 2:
            # ParentAthlete group_by_parent
            return make_scalars_result([parent_athlete])
        elif call_count == 3:
            # sibling check: athlete_ids del padre 20
            return make_scalars_result([5, 6])
        elif call_count == 4:
            # sibling newsletters en draft → hay uno!
            return make_scalars_result([nl_draft_sibling])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    result = await dispatch_newsletters(
        db=db,
        email_client=make_email_client(),
        registry=make_registry(),
        newsletter_ids=[1],
        force_individual=False,
    )

    assert 1 in result.newsletters_blocked
    assert result.emails_sent == 0
    assert result.newsletters_sent == []


@pytest.mark.asyncio
async def test_force_individual_bypasses_sibling_check():
    """force_individual=True omite la verificación de hermanos."""
    db = make_db()
    nl_approved = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.approved)

    parent_athlete = make_parent_athlete(parent_id=20, athlete_id=5)
    parent = make_user(id_=20)
    athlete = make_athlete(id_=5)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Select newsletters to dispatch
            return make_scalars_result([nl_approved])
        elif call_count == 2:
            # ParentAthlete group_by_parent
            return make_scalars_result([parent_athlete])
        # Con force_individual=True, _check_sibling_newsletters NO se llama
        # → siguiente call es directamente User
        elif call_count == 3:
            # User (parent)
            return make_scalars_result([parent])
        elif call_count == 4:
            # Athlete data
            return make_scalars_result([athlete])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    with patch(
        "app.services.notification.newsletter_dispatcher._render_email_template",
        return_value="<html>email</html>",
    ), patch(
        "app.services.notification.newsletter_dispatcher._render_subject",
        return_value="Boletín Marzo 2026",
    ):
        result = await dispatch_newsletters(
            db=db,
            email_client=make_email_client(success=True),
            registry=make_registry(),
            newsletter_ids=[1],
            force_individual=True,
        )

    # Con force_individual=True debe enviarse sin importar hermanos
    assert result.newsletters_blocked == []
    assert 1 in result.newsletters_sent
    assert result.emails_sent == 1


# ---------------------------------------------------------------------------
# Test: atleta sin padres vinculados
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_athlete_without_parents_newsletter_omitted():
    """Si el atleta no tiene padres vinculados, el newsletter se omite."""
    db = make_db()
    nl = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.approved)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([nl])
        elif call_count == 2:
            # ParentAthlete → vacío (sin padres)
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    result = await dispatch_newsletters(
        db=db,
        email_client=make_email_client(),
        registry=make_registry(),
        newsletter_ids=[1],
    )

    assert result.emails_sent == 0
    assert result.newsletters_sent == []


# ---------------------------------------------------------------------------
# Test: error de email client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_send_failure_recorded_in_errors():
    """Si el email client falla, el error se registra sin crashear."""
    db = make_db()
    nl = make_newsletter(id_=1, athlete_id=5, status=NewsletterStatus.approved)

    parent_athlete = make_parent_athlete(parent_id=20, athlete_id=5)
    parent = make_user(id_=20)
    athlete = make_athlete(id_=5)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([nl])
        elif call_count == 2:
            # ParentAthlete group_by_parent
            return make_scalars_result([parent_athlete])
        elif call_count == 3:
            # sibling check: select(ParentAthlete.athlete_id) para parent 20
            # Solo tiene atleta 5 que está siendo enviado → other_athlete_ids vacío
            # → _check_sibling_newsletters retorna [] sin segunda query
            return make_scalars_result([5])
        elif call_count == 4:
            # User (parent) — sibling newsletter query omitida
            return make_scalars_result([parent])
        elif call_count == 5:
            # Athlete data
            return make_scalars_result([athlete])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    with patch(
        "app.services.notification.newsletter_dispatcher._render_email_template",
        return_value="<html>email</html>",
    ), patch(
        "app.services.notification.newsletter_dispatcher._render_subject",
        return_value="Boletín Marzo 2026",
    ):
        result = await dispatch_newsletters(
            db=db,
            email_client=make_email_client(success=False),
            registry=make_registry(),
            newsletter_ids=[1],
        )

    assert result.emails_sent == 0
    assert len(result.errors) > 0
    assert result.newsletters_sent == []
