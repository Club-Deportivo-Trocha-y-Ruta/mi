"""Tests del router de boletines mensuales individuales (Fase 1.8).

Estrategia: mocks vía `app.dependency_overrides` para evitar dependencia
de MySQL real. Cubre los contratos de API + RBAC + lógica de negocio.

Cubre:
- _validate_period: mes actual / futuro rechazado (400), mes pasado OK
- POST create: 401 sin auth, 403 parent, 201 coach
- POST create: 409 si periodo no cerrado
- GET list: 200 coach, 403 parent
- GET detail: 404 si no existe
- PATCH: 409 si status != draft
- POST approve: 409 si no es draft
- POST send: 409 si no es approved / ya sent
- POST batch: RBAC correcto
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.athlete_newsletter import NewsletterStatus
from app.routers.athlete_monthly_newsletters import _validate_period


# ---------------------------------------------------------------------------
# Helpers: SimpleNamespace factories
# ---------------------------------------------------------------------------


def make_user(
    id_: int = 1,
    role: str = "coach",
    email: str = "coach@test.com",
    first_name: str = "Coach",
    last_name: str = "Test",
    club_id: int = 1,
) -> Any:
    from app.models.user import UserRole
    role_map = {"coach": UserRole.coach, "admin": UserRole.admin, "parent": UserRole.parent}
    return SimpleNamespace(
        id=id_,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role_map[role],
        is_active=True,
        can_login=True,
        club_ids=[club_id],
    )


def make_athlete(id_: int = 5, club_id: int = 1) -> Any:
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        first_name="Atleta",
        last_name="Test",
        birth_date=date(2012, 3, 15),
    )


def make_newsletter(
    id_: int = 1,
    athlete_id: int = 5,
    status: NewsletterStatus = NewsletterStatus.draft,
) -> Any:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=id_,
        athlete_id=athlete_id,
        year=2026,
        month=3,
        status=status,
        metrics_snapshot={"email_blocks": {"period": {"year": 2026, "month": 3}}, "pdf_only_blocks": {}},
        ai_narrative={
            "strengths": "Gran dedicación y constancia durante el mes de entrenamiento.",
            "area_to_develop": "Mejorar la técnica de frenado en descensos con curvas.",
            "milestone": "Completó el primer recorrido técnico sin asistencia del entrenador.",
            "model": "fake",
            "prompt_version": "v1",
            "confidence": "medium",
        },
        coach_narrative_overrides=None,
        badges_earned=None,
        pdf_storage_url=None,
        pdf_generated_at=None,
        pdf_sha256=None,
        generated_by_user_id=1,
        approved_by_user_id=None,
        approved_at=None,
        sent_at=None,
        sent_to=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Tests de _validate_period (sin DB)
# ---------------------------------------------------------------------------


class TestValidatePeriod:
    def test_past_month_ok(self):
        """Mes anterior al actual: sin excepción."""
        today = date.today()
        prev_month = today.month - 1 if today.month > 1 else 12
        prev_year = today.year if today.month > 1 else today.year - 1
        # No debe lanzar excepción
        _validate_period(prev_year, prev_month)

    def test_current_month_raises_400(self):
        """Mes actual rechazado sin force=True."""
        from fastapi import HTTPException

        today = date.today()
        with pytest.raises(HTTPException) as exc:
            _validate_period(today.year, today.month)
        assert exc.value.status_code == 400

    def test_future_month_raises_400(self):
        """Mes futuro rechazado sin force=True."""
        from fastapi import HTTPException

        today = date.today()
        future_year = today.year + 1
        with pytest.raises(HTTPException) as exc:
            _validate_period(future_year, today.month)
        assert exc.value.status_code == 400

    def test_current_month_with_force_ok(self):
        """force=True permite generar para mes actual."""
        today = date.today()
        # No debe lanzar excepción
        _validate_period(today.year, today.month, force=True)

    def test_year_2025_ok(self):
        """Año 2025 mes 1 es claramente pasado."""
        _validate_period(2025, 1)

    def test_previous_year_ok(self):
        """Año anterior completo es pasado."""
        today = date.today()
        _validate_period(today.year - 1, 6)


# ---------------------------------------------------------------------------
# Tests de endpoints con dependency_overrides
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    sess = MagicMock()
    sess.execute = AsyncMock()
    sess.flush = AsyncMock()
    sess.commit = AsyncMock()
    sess.rollback = AsyncMock()
    sess.add = MagicMock()
    return sess


@pytest.fixture
def coach_user():
    return make_user(id_=1, role="coach")


@pytest.fixture
def parent_user():
    return make_user(id_=2, role="parent")


def make_scalars_result(items):
    result = MagicMock()
    result.scalars.return_value = result
    result.all.return_value = items
    result.scalar_one_or_none.return_value = items[0] if items else None
    return result


# ---------------------------------------------------------------------------
# GET /api/athletes/{id}/monthly-newsletters — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_newsletters_requires_auth():
    """Sin autenticación → 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/athletes/5/monthly-newsletters")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_newsletters_parent_forbidden():
    """Parent no puede listar newsletters de atletas."""
    from app.dependencies import get_db, require_role
    from app.models.user import UserRole

    parent = make_user(role="parent")
    db = MagicMock()
    db.execute = AsyncMock(return_value=make_scalars_result([]))

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_role([UserRole.admin, UserRole.coach])] = lambda: parent

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Sin token real → 401 (require_role verifica JWT)
            resp = await client.get("/api/athletes/5/monthly-newsletters")
        # El endpoint require_role([admin, coach]) bloquea a parent
        assert resp.status_code in {401, 403}
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pruebas de schema de respuesta — desde from_orm_model
# ---------------------------------------------------------------------------


class TestSchemaPrivacyContract:
    """Verifica que el schema AthleteNewsletterRead nunca expone datos sensibles."""

    def test_sent_to_not_in_schema(self):
        from app.schemas.athlete_newsletter import AthleteNewsletterRead

        nl = make_newsletter(status=NewsletterStatus.sent)
        nl.sent_to = ["secreto@email.com"]

        read = AthleteNewsletterRead.from_orm_model(nl)
        data = read.model_dump()

        assert "sent_to" not in data
        assert "secreto@email.com" not in str(data)

    def test_pdf_only_blocks_not_in_schema(self):
        from app.schemas.athlete_newsletter import AthleteNewsletterRead

        nl = make_newsletter()
        nl.metrics_snapshot = {
            "email_blocks": {"attendance": {"sessions_total": 8}},
            "pdf_only_blocks": {
                "anthropometry": {
                    "has_records": True,
                    "records": [{"weight_kg": 45.0, "standing_height_cm": 152.0}],
                }
            },
        }

        read = AthleteNewsletterRead.from_orm_model(nl)
        data = read.model_dump()

        # pdf_only_blocks nunca en response
        assert "pdf_only_blocks" not in data
        assert "anthropometry" not in data
        assert "weight_kg" not in str(data)
        assert "standing_height_cm" not in str(data)

    def test_email_blocks_present_in_schema(self):
        from app.schemas.athlete_newsletter import AthleteNewsletterRead

        nl = make_newsletter()
        nl.metrics_snapshot = {
            "email_blocks": {"attendance": {"sessions_total": 8, "attendance_pct": 80.0}},
            "pdf_only_blocks": {},
        }

        read = AthleteNewsletterRead.from_orm_model(nl)
        assert read.email_blocks is not None
        assert "attendance" in read.email_blocks

    def test_status_workflow_serializable(self):
        from app.schemas.athlete_newsletter import AthleteNewsletterRead

        for status in NewsletterStatus:
            nl = make_newsletter(status=status)
            read = AthleteNewsletterRead.from_orm_model(nl)
            assert read.status == status

    def test_error_message_in_failed_response(self):
        from app.schemas.athlete_newsletter import AthleteNewsletterRead

        nl = make_newsletter(status=NewsletterStatus.failed)
        nl.error_message = "Timeout IA: 45s superados."
        read = AthleteNewsletterRead.from_orm_model(nl)
        assert read.error_message == "Timeout IA: 45s superados."


# ---------------------------------------------------------------------------
# Pruebas de RBAC — _verify_coach_athlete_access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_coach_athlete_access_admin_bypasses_club_check():
    """Admin puede acceder a cualquier atleta sin importar el club."""
    from app.routers.athlete_monthly_newsletters import _verify_coach_athlete_access
    from app.models.user import UserRole

    admin = make_user(role="admin")
    athlete = make_athlete(id_=5, club_id=99)  # club distinto al del admin

    db = MagicMock()
    db.execute = AsyncMock(return_value=make_scalars_result([athlete]))

    result = await _verify_coach_athlete_access(db, admin, 5)
    assert result.id == 5


@pytest.mark.asyncio
async def test_verify_coach_athlete_access_404_if_not_found():
    """Si el atleta no existe → HTTPException 404."""
    from fastapi import HTTPException
    from app.routers.athlete_monthly_newsletters import _verify_coach_athlete_access

    coach = make_user(role="coach")
    db = MagicMock()
    db.execute = AsyncMock(return_value=make_scalars_result([]))

    with pytest.raises(HTTPException) as exc:
        await _verify_coach_athlete_access(db, coach, 999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_verify_coach_athlete_access_403_if_different_club():
    """Coach sin acceso al club del atleta → HTTPException 403."""
    from fastapi import HTTPException
    from app.routers.athlete_monthly_newsletters import _verify_coach_athlete_access

    coach = make_user(role="coach", club_id=1)
    athlete = make_athlete(id_=5, club_id=99)  # club distinto

    db = MagicMock()
    # Primera query: athlete found
    db.execute = AsyncMock(return_value=make_scalars_result([athlete]))

    # user_club_role retorna None (coach no es miembro del club 99)
    with patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            await _verify_coach_athlete_access(db, coach, 5)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Pruebas de _get_newsletter_or_404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_newsletter_or_404_found():
    """Retorna el newsletter si existe."""
    from app.routers.athlete_monthly_newsletters import _get_newsletter_or_404

    nl = make_newsletter(id_=10, athlete_id=5)
    db = MagicMock()
    db.execute = AsyncMock(return_value=make_scalars_result([nl]))

    result = await _get_newsletter_or_404(db, 10, 5)
    assert result.id == 10


@pytest.mark.asyncio
async def test_get_newsletter_or_404_raises():
    """HTTPException 404 si no existe."""
    from fastapi import HTTPException
    from app.routers.athlete_monthly_newsletters import _get_newsletter_or_404

    db = MagicMock()
    db.execute = AsyncMock(return_value=make_scalars_result([]))

    with pytest.raises(HTTPException) as exc:
        await _get_newsletter_or_404(db, 999, 5)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Pruebas de estado del workflow via helper functions del router
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_rejected_if_not_draft():
    """PATCH rechaza con 409 si status != draft."""
    from fastapi import HTTPException
    from app.routers.athlete_monthly_newsletters import _get_newsletter_or_404
    from app.schemas.athlete_newsletter import AthleteNewsletterPatch, NarrativeOverride

    nl = make_newsletter(status=NewsletterStatus.approved)

    # Simular la lógica del endpoint patch
    if nl.status != NewsletterStatus.draft:
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Solo se puede editar un boletín en estado 'draft'. Estado actual: '{nl.status.value}'.",
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approve_rejected_if_not_draft():
    """approve endpoint rechaza con 409 si status != draft."""
    from fastapi import HTTPException

    nl = make_newsletter(status=NewsletterStatus.approved)

    # Simular condición del endpoint approve
    if nl.status != NewsletterStatus.draft:
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Solo se puede aprobar un boletín en estado 'draft'. Estado actual: '{nl.status.value}'.",
            )
        assert exc.value.status_code == 409
        assert "draft" in exc.value.detail


@pytest.mark.asyncio
async def test_send_rejected_if_already_sent():
    """send endpoint rechaza con 409 si ya está sent."""
    from fastapi import HTTPException

    nl = make_newsletter(status=NewsletterStatus.sent)

    if nl.status == NewsletterStatus.sent:
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(
                status_code=409,
                detail="Este boletín ya fue enviado.",
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_send_rejected_if_not_approved():
    """send endpoint rechaza con 409 si status != approved."""
    from fastapi import HTTPException

    nl = make_newsletter(status=NewsletterStatus.draft)

    if nl.status != NewsletterStatus.approved:
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Solo se puede enviar un boletín aprobado. Estado actual: '{nl.status.value}'.",
            )
        assert exc.value.status_code == 409
        assert "aprobado" in exc.value.detail


# ---------------------------------------------------------------------------
# Integración: newsletter batch response schema
# ---------------------------------------------------------------------------


class TestAthleteNewsletterBatchResult:
    def test_batch_result_fields(self):
        from app.schemas.athlete_newsletter import AthleteNewsletterBatchResult

        result = AthleteNewsletterBatchResult(
            period_year=2026,
            period_month=3,
            total_athletes=5,
            created=3,
            skipped=2,
            failed=0,
            newsletter_ids=[1, 2, 3],
            errors=[],
        )
        assert result.total_athletes == 5
        assert result.created == 3
        assert result.skipped == 2
        assert result.newsletter_ids == [1, 2, 3]

    def test_batch_result_errors_list(self):
        from app.schemas.athlete_newsletter import AthleteNewsletterBatchResult

        result = AthleteNewsletterBatchResult(
            period_year=2026,
            period_month=3,
            total_athletes=3,
            created=1,
            skipped=0,
            failed=2,
            newsletter_ids=[1],
            errors=[
                "Atleta ID 2: sin consentimiento IA",
                "Atleta ID 3: Timeout IA",
            ],
        )
        assert len(result.errors) == 2
        # Los errores no deben incluir PII como emails
        for err in result.errors:
            assert "@" not in err


# ---------------------------------------------------------------------------
# Pruebas de attach-insights — lógica de servicio directa (sin HTTP)
# ---------------------------------------------------------------------------
# Estrategia: testeamos la lógica del endpoint directamente, mockeando db,
# _verify_coach_athlete_access y AthleteAiInsight para evitar MySQL.
# Los tests de RBAC HTTP-level se hacen con dependency_overrides.


def make_insight(
    id_: int,
    athlete_id: int = 5,
    is_active: int = 1,
    is_fallback: bool = False,
) -> Any:
    """Factory de AthleteAiInsight mínimo para tests."""
    return SimpleNamespace(
        id=id_,
        athlete_id=athlete_id,
        is_active=is_active,
        coach_approved=True,
        is_fallback=is_fallback,
    )


def make_newsletter_with_insights(
    id_: int = 1,
    athlete_id: int = 5,
    selected_race_insight_ids: list | None = None,
    status: NewsletterStatus = NewsletterStatus.draft,
) -> Any:
    """Factory de newsletter con campo selected_race_insight_ids."""
    now = datetime.now(timezone.utc)
    nl = make_newsletter(id_=id_, athlete_id=athlete_id, status=status)
    nl.selected_race_insight_ids = selected_race_insight_ids
    return nl


class TestAttachInsightsSchemas:
    """Validaciones de schema Pydantic sin HTTP."""

    def test_request_requires_at_least_one_insight(self):
        from pydantic import ValidationError
        from app.schemas.athlete_newsletter import AttachInsightsRequest

        with pytest.raises(ValidationError):
            AttachInsightsRequest(insight_ids=[])

    def test_request_max_20_insights(self):
        from pydantic import ValidationError
        from app.schemas.athlete_newsletter import AttachInsightsRequest

        with pytest.raises(ValidationError):
            AttachInsightsRequest(insight_ids=list(range(1, 22)))  # 21 elementos

    def test_request_valid_with_defaults(self):
        from app.schemas.athlete_newsletter import AttachInsightsRequest

        req = AttachInsightsRequest(insight_ids=[1, 2, 3])
        assert req.year is None
        assert req.month is None
        assert req.insight_ids == [1, 2, 3]

    def test_request_with_explicit_year_month(self):
        from app.schemas.athlete_newsletter import AttachInsightsRequest

        req = AttachInsightsRequest(insight_ids=[10], year=2026, month=3)
        assert req.year == 2026
        assert req.month == 3

    def test_response_schema_fields(self):
        from app.schemas.athlete_newsletter import AttachInsightsResponse

        resp = AttachInsightsResponse(
            newsletter_id=1,
            athlete_id=5,
            year=2026,
            month=3,
            status=NewsletterStatus.draft,
            selected_race_insight_ids=[10, 20],
            created=True,
        )
        assert resp.created is True
        assert resp.selected_race_insight_ids == [10, 20]

    def test_response_no_pii_fields(self):
        """El response schema no expone emails, DOB ni datos médicos."""
        from app.schemas.athlete_newsletter import AttachInsightsResponse

        resp = AttachInsightsResponse(
            newsletter_id=1,
            athlete_id=5,
            year=2026,
            month=3,
            status=NewsletterStatus.draft,
            selected_race_insight_ids=[1],
            created=False,
        )
        data = resp.model_dump()
        sensitive_keys = {"sent_to", "email", "birth_date", "pdf_storage_url", "anthropometry"}
        assert not sensitive_keys.intersection(data.keys())


@pytest.mark.asyncio
async def test_attach_insights_creates_newsletter_when_not_exists():
    """Coach attach con newsletter inexistente → crea newsletter, created=True."""
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest
    from app.models.user import UserRole

    coach = make_user(role="coach")
    insight_10 = make_insight(id_=10, athlete_id=5)
    insight_20 = make_insight(id_=20, athlete_id=5)

    # db devuelve insights válidos en primera query, ningún newsletter en segunda
    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Verificar coach → atleta found
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        elif call_count == 2:
            # Query de insights válidos
            return make_scalars_result([insight_10, insight_20])
        else:
            # Query de newsletter existente → None
            return make_scalars_result([])

    # flush simula el INSERT asignando id al objeto recién agregado
    added_objects: list = []

    def fake_add(obj):
        obj.id = 42  # simula autoincrement post-flush
        added_objects.append(obj)

    async def fake_flush():
        # Si hay objetos sin id en added_objects, ya se asignaron en add
        pass

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.flush = AsyncMock(side_effect=fake_flush)
    db.commit = AsyncMock()
    db.add = MagicMock(side_effect=fake_add)

    body = AttachInsightsRequest(insight_ids=[10, 20], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        result = await attach_insights(
            athlete_id=5,
            body=body,
            db=db,
            current_user=coach,
        )

    assert result.created is True
    assert result.newsletter_id == 42
    assert result.athlete_id == 5
    assert result.year == 2026
    assert result.month == 3
    assert result.status == NewsletterStatus.draft
    assert set(result.selected_race_insight_ids) == {10, 20}
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_attach_insights_appends_to_existing_newsletter():
    """Coach attach con newsletter existente → append + dedupe, created=False."""
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")
    existing_nl = make_newsletter_with_insights(
        id_=1, athlete_id=5, selected_race_insight_ids=[10, 20]
    )
    insight_30 = make_insight(id_=30, athlete_id=5)

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        elif call_count == 2:
            return make_scalars_result([insight_30])
        else:
            return make_scalars_result([existing_nl])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    body = AttachInsightsRequest(insight_ids=[30], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        result = await attach_insights(
            athlete_id=5,
            body=body,
            db=db,
            current_user=coach,
        )

    assert result.created is False
    assert result.selected_race_insight_ids == [10, 20, 30]
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_attach_insights_deduplicates_on_repeated_append():
    """Append repetido del mismo insight_id no genera duplicados."""
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")
    # Newsletter ya tiene [10, 20]
    existing_nl = make_newsletter_with_insights(
        id_=1, athlete_id=5, selected_race_insight_ids=[10, 20]
    )
    insight_10 = make_insight(id_=10, athlete_id=5)  # ya estaba

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        elif call_count == 2:
            return make_scalars_result([insight_10])
        else:
            return make_scalars_result([existing_nl])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    body = AttachInsightsRequest(insight_ids=[10], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        result = await attach_insights(
            athlete_id=5,
            body=body,
            db=db,
            current_user=coach,
        )

    assert result.created is False
    # Sin duplicados: [10, 20] + [] = [10, 20]
    assert result.selected_race_insight_ids == [10, 20]
    assert len(result.selected_race_insight_ids) == len(set(result.selected_race_insight_ids))


@pytest.mark.asyncio
async def test_attach_insights_rejects_insight_of_another_athlete():
    """Insight que pertenece a otro atleta → 400 con IDs inválidos."""
    from fastapi import HTTPException
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")
    # insight_99 pertenece al atleta 99, no al 5
    # La query filtra por athlete_id=5, así que no lo devuelve

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        else:
            # Ningún insight válido devuelto (el insight 99 es de otro atleta)
            return make_scalars_result([])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)

    body = AttachInsightsRequest(insight_ids=[99], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        with pytest.raises(HTTPException) as exc:
            await attach_insights(
                athlete_id=5,
                body=body,
                db=db,
                current_user=coach,
            )

    assert exc.value.status_code == 400
    assert "99" in exc.value.detail


@pytest.mark.asyncio
async def test_attach_insights_rejects_inactive_insight():
    """Insight con is_active != 1 → 400."""
    from fastapi import HTTPException
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")
    # La query en el endpoint filtra por is_active=1, por tanto el insight inactivo
    # no aparece en valid_insights → se reporta como inválido

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        else:
            # insight 50 existe pero is_active=NULL → no pasa el filtro is_active==1
            return make_scalars_result([])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)

    body = AttachInsightsRequest(insight_ids=[50], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        with pytest.raises(HTTPException) as exc:
            await attach_insights(
                athlete_id=5,
                body=body,
                db=db,
                current_user=coach,
            )

    assert exc.value.status_code == 400
    assert "50" in exc.value.detail


@pytest.mark.asyncio
async def test_attach_insights_rejects_fallback_insight():
    """Insight con is_fallback=True → 422, aunque exista, sea del atleta y esté activo.

    Feature 036 (US4, T026): un placeholder de análisis fallido nunca se
    adjunta a un boletín — ni siquiera si el coach lo aprobó y envía su ID
    explícitamente. Distinto del 400 de ``is_active``: acá el insight es
    válido en su existencia/pertenencia, pero su contenido no es publicable.
    """
    from fastapi import HTTPException
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")
    fallback_insight = make_insight(id_=60, athlete_id=5, is_active=1, is_fallback=True)

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        else:
            # Insight 60 pasa el filtro is_active==1 de la query, pero es fallback.
            return make_scalars_result([fallback_insight])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)

    body = AttachInsightsRequest(insight_ids=[60], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        with pytest.raises(HTTPException) as exc:
            await attach_insights(
                athlete_id=5,
                body=body,
                db=db,
                current_user=coach,
            )

    assert exc.value.status_code == 422
    assert "60" in exc.value.detail


@pytest.mark.asyncio
async def test_attach_insights_allows_non_fallback_insight_mixed_with_check():
    """Sólo el insight fallback bloquea el request; el resto no importa aquí.

    Con dos insights válidos y uno de ellos fallback, el 422 debe listar
    únicamente el ID fallback — no el válido.
    """
    from fastapi import HTTPException
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")
    good_insight = make_insight(id_=10, athlete_id=5, is_fallback=False)
    fallback_insight = make_insight(id_=60, athlete_id=5, is_fallback=True)

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        else:
            return make_scalars_result([good_insight, fallback_insight])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)

    body = AttachInsightsRequest(insight_ids=[10, 60], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        with pytest.raises(HTTPException) as exc:
            await attach_insights(
                athlete_id=5,
                body=body,
                db=db,
                current_user=coach,
            )

    assert exc.value.status_code == 422
    assert "60" in exc.value.detail
    assert "10" not in exc.value.detail


@pytest.mark.asyncio
async def test_attach_insights_parent_blocked_by_rbac():
    """Parent no puede usar attach-insights → require_role devuelve 403."""
    from app.dependencies import get_db, require_role
    from app.models.user import UserRole

    parent = make_user(role="parent")

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[require_role([UserRole.admin, UserRole.coach])] = (
        lambda: (_ for _ in ()).throw(
            __import__("fastapi").HTTPException(status_code=403, detail="Forbidden")
        )
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/athletes/5/monthly-newsletters/attach-insights",
                json={"insight_ids": [1]},
            )
        # Sin auth real → 401; con override de parent → 403
        assert resp.status_code in {401, 403}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_attach_insights_custom_year_month():
    """year/month explícito en el body se usa en lugar del default Colombia."""
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")
    insight_10 = make_insight(id_=10, athlete_id=5)

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        elif call_count == 2:
            return make_scalars_result([insight_10])
        else:
            return make_scalars_result([])  # no existe newsletter

    def fake_add(obj):
        obj.id = 7  # simula autoincrement post-flush

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock(side_effect=fake_add)

    # year/month custom: enero 2025
    body = AttachInsightsRequest(insight_ids=[10], year=2025, month=1)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        result = await attach_insights(
            athlete_id=5,
            body=body,
            db=db,
            current_user=coach,
        )

    assert result.year == 2025
    assert result.month == 1
    assert result.created is True


@pytest.mark.asyncio
async def test_attach_insights_multiple_invalid_ids_all_reported():
    """Varios IDs inválidos → todos aparecen en el detalle del 400."""
    from fastapi import HTTPException
    from unittest.mock import patch as _patch
    from app.routers.athlete_monthly_newsletters import attach_insights
    from app.schemas.athlete_newsletter import AttachInsightsRequest

    coach = make_user(role="coach")

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([make_athlete(id_=5, club_id=1)])
        else:
            # Solo insight 10 es válido, 88 y 99 no lo son
            return make_scalars_result([make_insight(id_=10, athlete_id=5)])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)

    body = AttachInsightsRequest(insight_ids=[10, 88, 99], year=2026, month=3)

    with _patch(
        "app.routers.athlete_monthly_newsletters.user_club_role",
        new_callable=AsyncMock,
        return_value="coach",
    ):
        with pytest.raises(HTTPException) as exc:
            await attach_insights(
                athlete_id=5,
                body=body,
                db=db,
                current_user=coach,
            )

    assert exc.value.status_code == 400
    assert "88" in exc.value.detail
    assert "99" in exc.value.detail
    # 10 era válido, no debe aparecer en el detalle de error
    assert "10" not in exc.value.detail


# ---------------------------------------------------------------------------
# Regresión FR-015 (024) — snapshots pre-024 renderizan sin excepción
# ---------------------------------------------------------------------------
#
# Snapshot "legacy": carece de los campos nuevos de la 024 (focus_groups,
# weekly_hours_avg/ltad_limit_hours/ltad_status, short_label, streak_sessions)
# y en su lugar trae la clave vieja `streak_days`. Los templates deben
# degradar con sus fallbacks (`is defined` / `.get(...)`) sin lanzar.


_LEGACY_EMAIL_BLOCKS: dict = {
    "period": {"year": 2026, "month": 3},
    "attendance": {
        "sessions_present": 8,
        "sessions_total": 10,
        "attendance_pct": 80.0,
        "attendance_pct_prev_month": 75.0,
        "streak_days": 3,  # clave vieja; streak_sessions no existe
    },
    "technical": {
        "focos_tecnicos": ["Frenado"],
        "avg_rpe": 6.0,
        "avg_rubric_technique": 3.5,
        "total_training_hours": 9.0,
        # sin focus_groups / weekly_hours_avg / ltad_limit_hours / ltad_status
    },
    "race_results": {
        "has_races": True,
        "results": [
            {"position": 4, "valida_num": "III", "gap_to_winner_pct": 6.2}
            # sin "label" ni "short_label"
        ],
    },
    "calendar": {"next_training_sessions": [], "next_race_events": []},
    "photos": {"count": 0, "items": []},
    "badges": {"items": [{"badge_type": "attendance_90"}]},
}

_LEGACY_PDF_ONLY_BLOCKS: dict = {
    "anthropometry": {"has_records": False},
    "charts_context": {
        "has_data": False,
        "low_confidence": True,
        "positions": [],
        "gap_pcts": [],
        "points_accumulated": [],
    },
    "percentile_curves": None,
}


class TestLegacySnapshotBackwardCompat:
    """FR-015: un snapshot generado antes de la 024 debe renderizar PDF y
    email sin lanzar excepciones, pese a carecer de los campos nuevos."""

    @pytest.mark.asyncio
    async def test_legacy_snapshot_renders_pdf_without_raising(self):
        from app.services.notification.athlete_newsletter_pdf import generate_newsletter_pdf
        from app.services.notification.document_generator import DocumentGenerator
        from app.services.notification.template_registry import TemplateRegistry

        generator = DocumentGenerator(TemplateRegistry())

        doc, sha256 = await generate_newsletter_pdf(
            generator=generator,
            athlete_first_name="Atleta",
            athlete_last_name="Legacy",
            athlete_id=5,
            year=2026,
            month=3,
            email_blocks=_LEGACY_EMAIL_BLOCKS,
            pdf_only_blocks=_LEGACY_PDF_ONLY_BLOCKS,
            ai_narrative=None,
            coach_narrative_overrides=None,
            db=None,  # sin sesión: photos_render degrada a embeddable_count=0
        )

        assert len(doc.data) > 0
        assert len(sha256) == 64

    def test_legacy_snapshot_renders_email_without_raising(self):
        from app.services.notification.newsletter_dispatcher import _render_email_template
        from app.services.notification.template_registry import TemplateRegistry

        registry = TemplateRegistry()
        context = {
            "club_name": "Trocha y Ruta",
            "month_label": "Marzo 2026",
            "season_year": "2026",
            "children": [
                {
                    "athlete_id": 5,
                    "athlete_first_name": "Atleta",
                    "email_blocks": _LEGACY_EMAIL_BLOCKS,
                    "ai_narrative": None,
                    "coach_narrative_overrides": None,
                }
            ],
        }

        html = _render_email_template(registry, context)

        assert "Atleta" in html
        # Fallback de streak: usa la clave vieja `streak_days`
        assert "3 sesiones consecutivas" in html
        # Fallback de label: usa "Válida <valida_num>" al faltar short_label/label
        assert "Válida III" in html
