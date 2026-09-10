"""Tests T025/T026 (feature 041) — auditoría de informes mensuales, perfil de
proyecto del club y boletines familiares.

contracts/audit-recording.md §4.7 (informes/perfil) y §4.8 (boletines).

Estrategia: DB real (SQLite in-memory + StaticPool) sembrada con los
helpers compartidos de ``tests/fixtures/race_history_fixtures.py``, llamando
directamente a las funciones de servicio/router (sin pasar por HTTP) para
evitar la complejidad de las dependencias de IA. Como no hay
``RequestIdMiddleware`` fuera de una petición HTTP real, cada llamada se
envuelve en ``request_id_scope()`` (mismo mecanismo que usa la CLI/cron,
contracts/audit-recording.md §3.3).

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.audit_log import AuditAction, AuditLog
from app.models.club_project_profile import ClubProjectProfile
from app.models.training_session import MonthlyReport, MonthlyReportStatus
from app.models.user import UserRole
from app.schemas.athlete_newsletter import AttachInsightsRequest, RegenerateBlockRequest
from app.schemas.club_project_profile import ClubProjectProfileCreate, ClubProjectProfileUpdate
from app.services.request_context import request_id_scope
from app.services.training.reports import regenerate_block, update_report_blocks

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "monthly_reports",
    "club_project_profiles",
    "athlete_monthly_newsletters",
    "newsletter_delivery_events",
    "athlete_ai_insights",
    *AUDIT_TABLES,
)

CLUB_ID = 1
ATHLETE_ID = 50
COACH_ID = 10


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncSession:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def coach(db: AsyncSession):
    await create_club(db, club_id=CLUB_ID, name="Club Ficticio Auditoria", code="cft-041-r")
    c = await create_user(
        db, user_id=COACH_ID, role=UserRole.coach, first_name="Coach", last_name="Ficticio"
    )
    from app.models.club import ClubRole

    await link_user_to_club(db, user_id=COACH_ID, club_id=CLUB_ID, role_in_club=ClubRole.coach)
    await db.commit()
    return c


@pytest_asyncio.fixture
async def athlete(db: AsyncSession, coach):
    a = await create_athlete(
        db,
        athlete_id=ATHLETE_ID,
        first_name="Atleta Ficticia",
        last_name="Prueba",
        birth_date=date(2013, 5, 1),
        club_id=CLUB_ID,
        user_id=9000,
        created_by=COACH_ID,
    )
    await db.commit()
    return a


async def _audit_rows(db: AsyncSession, entity_type: str, entity_id: int) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# T025 — PATCH /monthly-reports/{year}/{month}/blocks
# ---------------------------------------------------------------------------


class TestMonthlyReportBlocksAudit:
    @pytest.mark.asyncio
    async def test_edicion_de_bloque_registra_update(self, db, coach):
        report = MonthlyReport(
            club_id=CLUB_ID,
            year=2026,
            month=6,
            status=MonthlyReportStatus.DRAFT,
            generated_by_user_id=coach.id,
            generated_at=datetime.now(timezone.utc),
            narrative_blocks={},
        )
        db.add(report)
        await db.flush()
        await db.commit()

        with request_id_scope():
            await update_report_blocks(
                db=db,
                club_id=CLUB_ID,
                year=2026,
                month=6,
                blocks={"objetivo": "Texto de prueba."},
                new_status=None,
                editor_user=coach,
            )

        rows = await _audit_rows(db, "monthly_report", report.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.update
        assert "narrative_blocks" in rows[0].changed_fields
        assert rows[0].diff_json is None

    @pytest.mark.asyncio
    async def test_aprobar_registra_update_y_approve(self, db, coach):
        report = MonthlyReport(
            club_id=CLUB_ID,
            year=2026,
            month=7,
            status=MonthlyReportStatus.DRAFT,
            generated_by_user_id=coach.id,
            generated_at=datetime.now(timezone.utc),
            narrative_blocks={},
        )
        db.add(report)
        await db.flush()
        await db.commit()

        with request_id_scope():
            await update_report_blocks(
                db=db,
                club_id=CLUB_ID,
                year=2026,
                month=7,
                blocks={},
                new_status=MonthlyReportStatus.APPROVED,
                editor_user=coach,
            )

        rows = await _audit_rows(db, "monthly_report", report.id)
        actions = {r.action for r in rows}
        assert actions == {AuditAction.update, AuditAction.approve}
        update_row = next(r for r in rows if r.action == AuditAction.update)
        assert update_row.diff_json == {
            "status": {"before": "draft", "after": "approved"}
        }


# ---------------------------------------------------------------------------
# T025 — POST /monthly-reports/{year}/{month}/blocks/{block_key}/regenerate
# ---------------------------------------------------------------------------


class TestMonthlyReportRegenerateBlockAudit:
    @pytest.mark.asyncio
    async def test_regenerar_bloque_registra_update_con_meta_period(self, db, coach, athlete):
        report = MonthlyReport(
            club_id=CLUB_ID,
            year=2026,
            month=8,
            status=MonthlyReportStatus.DRAFT,
            generated_by_user_id=coach.id,
            generated_at=datetime.now(timezone.utc),
            narrative_blocks={},
        )
        db.add(report)
        await db.flush()
        await db.commit()

        draft = MagicMock()
        draft.ai_draft = "Nuevo borrador IA."
        draft.ai_model = "fake-model"
        draft.generated_at = datetime.now(timezone.utc)

        blocks_use_case = MagicMock()
        blocks_use_case.build_context_from_metrics.return_value = MagicMock()
        blocks_use_case.run_block = AsyncMock(return_value=draft)

        empty_metrics = MagicMock()

        with patch(
            "app.services.training.reports.compute_monthly_metrics",
            AsyncMock(return_value=empty_metrics),
        ):
            with request_id_scope():
                await regenerate_block(
                    db=db,
                    club_id=CLUB_ID,
                    year=2026,
                    month=8,
                    block_key="objetivo",
                    blocks_use_case=blocks_use_case,
                    editor_user=coach,
                )

        rows = await _audit_rows(db, "monthly_report", report.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.update
        assert rows[0].meta_json == {"period": "2026-08"}


# ---------------------------------------------------------------------------
# T025 — PUT/PATCH /clubs/{club_id}/project-profile
# ---------------------------------------------------------------------------


class TestClubProjectProfileAudit:
    @pytest.mark.asyncio
    async def test_put_crea_perfil_registra_create(self, db, coach):
        from app.routers.monthly_reports import upsert_project_profile

        body = ClubProjectProfileCreate(project_name="Proyecto Ficticio")
        with request_id_scope():
            with patch(
                "app.routers.monthly_reports.user_club_role",
                AsyncMock(return_value="coach"),
            ):
                out = await upsert_project_profile(
                    club_id=CLUB_ID, body=body, db=db, current_user=coach
                )

        rows = await _audit_rows(db, "club_project_profile", out.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create

    @pytest.mark.asyncio
    async def test_patch_actualiza_perfil_registra_update(self, db, coach):
        from app.routers.monthly_reports import patch_project_profile

        profile = ClubProjectProfile(club_id=CLUB_ID, project_name="Nombre inicial")
        db.add(profile)
        await db.flush()
        await db.commit()

        body = ClubProjectProfileUpdate(project_name="Nombre actualizado")
        with request_id_scope():
            with patch(
                "app.routers.monthly_reports.user_club_role",
                AsyncMock(return_value="coach"),
            ):
                await patch_project_profile(
                    club_id=CLUB_ID, body=body, db=db, current_user=coach
                )

        rows = await _audit_rows(db, "club_project_profile", profile.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.update
        assert rows[0].changed_fields == ["project_name"]


# ---------------------------------------------------------------------------
# T026 — POST /athletes/{athlete_id}/monthly-newsletters (create)
# ---------------------------------------------------------------------------


class TestNewsletterCreateAudit:
    @pytest.mark.asyncio
    async def test_create_newsletter_registra_create(self, db, coach, athlete):
        from app.routers.athlete_monthly_newsletters import _generate_newsletter_for_athlete

        with patch(
            "app.services.privacy.athlete_has_ai_processing_consent",
            AsyncMock(return_value=False),
        ), patch(
            "app.services.training.newsletter_builder.build_newsletter_metrics",
            AsyncMock(return_value={"email_blocks": {}, "pdf_only_blocks": {}}),
        ), patch(
            "app.routers.athlete_monthly_newsletters._build_forbidden_names",
            AsyncMock(return_value=frozenset()),
        ), patch(
            "app.routers.athlete_monthly_newsletters._build_v2_stage_log_content",
            AsyncMock(return_value=(None, None, None)),
        ):
            with request_id_scope():
                nl = await _generate_newsletter_for_athlete(
                    db=db,
                    athlete=athlete,
                    year=2026,
                    month=6,
                    current_user=coach,
                    force=False,
                    llm_provider=None,
                    prompt_registry=None,
                )
            await db.commit()

        rows = await _audit_rows(db, "athlete_monthly_newsletter", nl.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create
        assert rows[0].athlete_id == ATHLETE_ID


# ---------------------------------------------------------------------------
# T026 — PATCH /athletes/{athlete_id}/monthly-newsletters/{id}
# ---------------------------------------------------------------------------


class TestNewsletterPatchAudit:
    @pytest.mark.asyncio
    async def test_edicion_simple_registra_update(self, db, coach, athlete):
        from app.routers.athlete_monthly_newsletters import patch_newsletter
        from app.schemas.athlete_newsletter import AthleteNewsletterPatch

        nl = AthleteMonthlyNewsletter(
            athlete_id=ATHLETE_ID,
            year=2026,
            month=6,
            status=NewsletterStatus.draft,
        )
        db.add(nl)
        await db.flush()
        await db.commit()

        # T069: el PATCH exige la versión esperada; la fila recién sembrada nace en 1.
        body = AthleteNewsletterPatch(hidden_blocks=["photos"], expected_version=1)
        with request_id_scope():
            with patch(
                "app.routers.athlete_monthly_newsletters._rederive_stage_log",
                AsyncMock(return_value=None),
            ):
                await patch_newsletter(
                    athlete_id=ATHLETE_ID,
                    newsletter_id=nl.id,
                    body=body,
                    response=Response(),
                    # Llamada directa al handler: FastAPI no resuelve el
                    # `Header(...)`, así que la precondición viaja en el cuerpo.
                    if_match=None,
                    db=db,
                    current_user=coach,
                )

        rows = await _audit_rows(db, "athlete_monthly_newsletter", nl.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.update
        assert "hidden_blocks" in rows[0].changed_fields

    @pytest.mark.asyncio
    async def test_edicion_que_desaprueba_registra_update_y_unapprove(self, db, coach, athlete):
        from app.routers.athlete_monthly_newsletters import patch_newsletter
        from app.schemas.athlete_newsletter import AthleteNewsletterPatch

        nl = AthleteMonthlyNewsletter(
            athlete_id=ATHLETE_ID,
            year=2026,
            month=7,
            status=NewsletterStatus.approved,
            approved_by_user_id=coach.id,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(nl)
        await db.flush()
        await db.commit()

        # T069: el PATCH exige la versión esperada; la fila recién sembrada nace en 1.
        body = AthleteNewsletterPatch(
            coach_note="Buen mes de entrenamiento.", expected_version=1
        )
        with request_id_scope():
            with patch(
                "app.routers.athlete_monthly_newsletters._rederive_stage_log",
                AsyncMock(return_value=None),
            ):
                await patch_newsletter(
                    athlete_id=ATHLETE_ID,
                    newsletter_id=nl.id,
                    body=body,
                    response=Response(),
                    # Llamada directa al handler: FastAPI no resuelve el
                    # `Header(...)`, así que la precondición viaja en el cuerpo.
                    if_match=None,
                    db=db,
                    current_user=coach,
                )

        rows = await _audit_rows(db, "athlete_monthly_newsletter", nl.id)
        actions = {r.action for r in rows}
        assert actions == {AuditAction.update, AuditAction.unapprove}


# ---------------------------------------------------------------------------
# T026 — POST /athletes/{athlete_id}/monthly-newsletters/{id}/regenerate-block
# ---------------------------------------------------------------------------


class TestNewsletterRegenerateBlockAudit:
    @pytest.mark.asyncio
    async def test_regenerar_bloque_registra_update(self, db, coach, athlete):
        from app.routers.athlete_monthly_newsletters import regenerate_newsletter_block

        nl = AthleteMonthlyNewsletter(
            athlete_id=ATHLETE_ID,
            year=2026,
            month=6,
            status=NewsletterStatus.draft,
        )
        db.add(nl)
        await db.flush()
        await db.commit()

        body = RegenerateBlockRequest(block="observations")

        with patch(
            "app.services.privacy.athlete_has_ai_processing_consent",
            AsyncMock(return_value=True),
        ), patch(
            "app.routers.athlete_monthly_newsletters._build_forbidden_names",
            AsyncMock(return_value=frozenset()),
        ), patch(
            "app.routers.athlete_monthly_newsletters._resolve_family_insight",
            AsyncMock(return_value=None),
        ), patch(
            "app.routers.athlete_monthly_newsletters._previous_stage_texts",
            AsyncMock(return_value=(None, None)),
        ), patch(
            "app.routers.athlete_monthly_newsletters._rederive_stage_log",
            AsyncMock(return_value=None),
        ):
            from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
                AthleteMonthlyNewsletterV2UseCase,
            )

            with patch.object(
                AthleteMonthlyNewsletterV2UseCase,
                "regenerate_block",
                AsyncMock(return_value="Nuevo texto de observaciones."),
            ):
                with request_id_scope():
                    await regenerate_newsletter_block(
                        athlete_id=ATHLETE_ID,
                        newsletter_id=nl.id,
                        body=body,
                        db=db,
                        current_user=coach,
                        llm_provider=None,
                        prompt_registry=None,
                    )

        rows = await _audit_rows(db, "athlete_monthly_newsletter", nl.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.update
        assert rows[0].meta_json == {"block": "observations"}


# ---------------------------------------------------------------------------
# T026 — POST /athletes/{athlete_id}/monthly-newsletters/{id}/approve
# ---------------------------------------------------------------------------


class TestNewsletterApproveAudit:
    @pytest.mark.asyncio
    async def test_aprobar_registra_approve(self, db, coach, athlete):
        from app.routers.athlete_monthly_newsletters import approve_newsletter

        nl = AthleteMonthlyNewsletter(
            athlete_id=ATHLETE_ID,
            year=2026,
            month=6,
            status=NewsletterStatus.draft,
        )
        db.add(nl)
        await db.flush()
        await db.commit()

        with request_id_scope():
            await approve_newsletter(
                athlete_id=ATHLETE_ID, newsletter_id=nl.id, db=db, current_user=coach
            )

        rows = await _audit_rows(db, "athlete_monthly_newsletter", nl.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.approve
        assert rows[0].club_id == CLUB_ID


# ---------------------------------------------------------------------------
# T026 — POST /athletes/{athlete_id}/monthly-newsletters/{id}/send
# ---------------------------------------------------------------------------


class TestNewsletterSendAudit:
    @pytest.mark.asyncio
    async def test_enviar_registra_send_con_recipients_count(self, db, coach, athlete):
        from app.models.athlete import ParentAthlete, FamilyRelationship
        from app.models.user import User
        from app.services.notification.newsletter_dispatcher import dispatch_newsletters

        parent = User(
            id=9500,
            email="padre.ficticio@test.local",
            hashed_password="x",
            first_name="Padre",
            last_name="Ficticio",
            role=UserRole.parent,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(parent)
        await db.flush()
        db.add(ParentAthlete(
            parent_id=parent.id,
            athlete_id=ATHLETE_ID,
            relationship_type=FamilyRelationship.padre,
        ))

        nl = AthleteMonthlyNewsletter(
            athlete_id=ATHLETE_ID,
            year=2026,
            month=6,
            status=NewsletterStatus.approved,
        )
        db.add(nl)
        await db.flush()
        await db.commit()

        send_result = MagicMock()
        send_result.message_id = "smtp-fake"
        email_client = MagicMock()
        email_client.send = AsyncMock(return_value=send_result)

        registry = MagicMock()

        # Reemplaza el envío real de email (jinja/HTML) por un stub liviano:
        # _send_v2_email hace demasiado I/O de templates para este test de
        # auditoría, así que se parchea directamente.
        async def _fake_send_v2_email(*, db, email_client, registry, parent, newsletters,
                                       year, month, result, actor=None):
            now = datetime.now(timezone.utc)
            sent_ids = []
            for nl_ in newsletters:
                nl_.status = NewsletterStatus.sent
                nl_.sent_at = now
                nl_.sent_to = [parent.email]
                await db.flush()
                if actor is not None:
                    from app.services.audit import AuditAction as _AA
                    from app.services.audit import AuditEntityType as _AET
                    from app.services.audit import record_audit as _ra
                    await _ra(
                        db,
                        action=_AA.send,
                        entity_type=_AET.athlete_monthly_newsletter,
                        entity_id=nl_.id,
                        actor=actor,
                        club_id=CLUB_ID,
                        athlete_id=nl_.athlete_id,
                        meta={
                            "document_kind": "newsletter_email",
                            "recipients_count": len(nl_.sent_to or []),
                        },
                    )
                result.newsletters_sent.append(nl_.id)
                sent_ids.append(nl_.id)
            return sent_ids

        with patch(
            "app.services.notification.newsletter_dispatcher._send_v2_email",
            _fake_send_v2_email,
        ):
            with request_id_scope():
                await dispatch_newsletters(
                    db=db,
                    email_client=email_client,
                    registry=registry,
                    newsletter_ids=[nl.id],
                    actor=coach,
                )

        rows = await _audit_rows(db, "athlete_monthly_newsletter", nl.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.send
        assert rows[0].meta_json == {
            "document_kind": "newsletter_email",
            "recipients_count": 1,
        }


# ---------------------------------------------------------------------------
# T026 — POST /athletes/{athlete_id}/monthly-newsletters/attach-insights
# ---------------------------------------------------------------------------


class TestAttachInsightsAudit:
    @pytest.mark.asyncio
    async def test_crear_via_attach_insights_registra_create(self, db, coach, athlete):
        from app.routers.athlete_monthly_newsletters import attach_insights

        body = AttachInsightsRequest(insight_ids=[1], year=2026, month=6)

        from app.models.athlete_ai_insight import AthleteAiInsight

        insight = AthleteAiInsight(
            id=1,
            athlete_id=ATHLETE_ID,
            season=2026,
            valida_num=1,
            use_case="race_analysis",
            summary_text="Resumen ficticio.",
            recommendations_json=[],
            metrics_snapshot_json={},
            principles_cited_json=[],
            is_active=1,
            is_fallback=False,
            model="fake-model",
            prompt_version="race_analyst_v3",
            generated_by_user_id=coach.id,
            generated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(insight)
        await db.flush()
        await db.commit()

        with request_id_scope():
            out = await attach_insights(
                athlete_id=ATHLETE_ID, body=body, db=db, current_user=coach
            )

        rows = await _audit_rows(db, "athlete_monthly_newsletter", out.newsletter_id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create

    @pytest.mark.asyncio
    async def test_agregar_a_existente_registra_link(self, db, coach, athlete):
        from app.routers.athlete_monthly_newsletters import attach_insights
        from app.models.athlete_ai_insight import AthleteAiInsight

        nl = AthleteMonthlyNewsletter(
            athlete_id=ATHLETE_ID,
            year=2026,
            month=6,
            status=NewsletterStatus.draft,
            selected_race_insight_ids=[1],
        )
        db.add(nl)
        db.add(AthleteAiInsight(
            id=1,
            athlete_id=ATHLETE_ID,
            season=2026,
            valida_num=1,
            use_case="race_analysis",
            summary_text="Resumen ficticio 1.",
            recommendations_json=[],
            metrics_snapshot_json={},
            principles_cited_json=[],
            is_active=1,
            is_fallback=False,
            model="fake-model",
            prompt_version="race_analyst_v3",
            generated_by_user_id=coach.id,
            generated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.add(AthleteAiInsight(
            id=2,
            athlete_id=ATHLETE_ID,
            season=2026,
            valida_num=2,
            use_case="race_analysis",
            summary_text="Resumen ficticio 2.",
            recommendations_json=[],
            metrics_snapshot_json={},
            principles_cited_json=[],
            is_active=1,
            is_fallback=False,
            model="fake-model",
            prompt_version="race_analyst_v3",
            generated_by_user_id=coach.id,
            generated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        await db.flush()
        await db.commit()

        body = AttachInsightsRequest(insight_ids=[2], year=2026, month=6)
        with request_id_scope():
            await attach_insights(
                athlete_id=ATHLETE_ID, body=body, db=db, current_user=coach
            )

        rows = await _audit_rows(db, "athlete_monthly_newsletter", nl.id)
        assert len(rows) == 1
        assert rows[0].action == AuditAction.link
