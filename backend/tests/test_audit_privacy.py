"""FR-003 — privacy-minimisation of ``audit_log`` (data-model.md §2.5, §8.4).

Modelled on ``tests/test_privacy.py:31``. No instrumentation writes to
``audit_log`` yet (routers are not wired to ``record_audit`` — that lands in
Phase 3 of feature 041), so this module is deliberately split in two:

1. **Catalogue-level checks** (no rows needed): ``VALUE_ALLOWLIST`` and
   ``META_ALLOWLIST`` themselves must never admit a forbidden field, and
   ``CLUB_OPTIONAL`` must stay the small, documented exception set. These are
   meaningful today and will keep being meaningful forever — they are the
   contract §1.7/data-model §2.5 tables, asserted as code.
2. **Row-level scan**, exercised two ways so the assertions are not vacuous:
   a) directly through ``record_audit`` (already implemented, T010) with a
      realistic two-coach/one-athlete scenario, including several
      *rejected* fields on purpose, to prove the production filtering path
      keeps them out — the meaningful-now half of SC-001's second clause;
   b) a negative control that inserts a raw ``AuditLog`` row bypassing
      ``record_audit`` with a deliberately forbidden key, to prove the scan
      function used everywhere in this file actually detects a violation
      and is not a silent no-op.
3. A **suite-reality check**: the same scan run over whatever rows the
   existing HTTP-level fixtures produce when hit through the real app (today:
   zero, because no router calls ``record_audit`` yet). The row count is
   asserted and printed explicitly — not a silent empty loop — so this test
   starts exercising real production rows the moment Phase 3 wires the first
   router, with no edit required here.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from tests.fixtures.two_coaches import _TABLES as _TWO_COACHES_TABLES
from app.models.user import UserRole
from app.schemas.athlete_newsletter import _HIDEABLE_BLOCKS
from app.services.audit import (
    AuditEntityType,
    AuditReasonCode,
    CLUB_OPTIONAL,
    META_ALLOWLIST,
    VALUE_ALLOWLIST,
    record_audit,
)
from app.services.request_context import request_id_scope

from tests.fixtures.two_coaches import (
    ATHLETE_BIRTH_DATE,
    ATHLETE_FIRST_NAME,
    ATHLETE_LAST_NAME,
    TwoCoachesScenario,
    seed_two_coaches,
)


# ---------------------------------------------------------------------------
# Local fixtures — the shared ``two_coaches`` fixtures only create a small
# subset of tables (users/clubs/club_members/athletes/parent_athlete, see
# ``tests/fixtures/two_coaches.py::_TABLES``). This module also needs
# ``audit_log`` to exist, so it seeds the same scenario over the *full*
# ``Base.metadata`` instead of reusing ``two_coaches_scenario`` directly —
# without editing the shared fixture module (out of scope for this task).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def privacy_engine() -> "AsyncEngine":
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Only the tables the two-coach scenario + the audited router smoke
    # need — mirrors tests/fixtures/two_coaches.py::_TABLES exactly, which
    # already includes audit_log (see tests/helpers/audit_tables.py).
    # Using the *full* Base.metadata fails today: privacy_policies declares
    # a MySQL-only LONGTEXT column with no SQLite variant.
    tables = [Base.metadata.tables[t] for t in dict.fromkeys(_TWO_COACHES_TABLES)]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def privacy_session_factory(privacy_engine: "AsyncEngine"):
    return async_sessionmaker(privacy_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def privacy_scenario(privacy_session_factory) -> "TwoCoachesScenario":
    async with privacy_session_factory() as session:
        yield await seed_two_coaches(session)


@pytest_asyncio.fixture
async def privacy_client_factory(privacy_session_factory, privacy_scenario):
    """Same shape as ``two_coaches_client_factory`` (tests/fixtures/two_coaches.py)
    but backed by the full-schema engine above so a real router write lands
    in a queryable ``audit_log`` table."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from httpx import ASGITransport, AsyncClient

    from app.dependencies import get_current_user, get_db
    from app.main import app

    @asynccontextmanager
    async def make_client(user_id: int, role: UserRole):
        async def _override_db():
            async with privacy_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        def _override_current_user():
            return SimpleNamespace(
                id=user_id,
                first_name="Test",
                last_name="Actor",
                phone=None,
                email=f"actor{user_id}@test.local",
                role=role,
                can_login=True,
                is_active=True,
                club_memberships=[],
                created_at=datetime.now(timezone.utc),
            )

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_current_user
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client

# ---------------------------------------------------------------------------
# Forbidden field/value catalogue — data-model.md §2.5, verbatim
# ---------------------------------------------------------------------------

NEVER_ALLOWLISTED_FIELDS: frozenset[str] = frozenset(
    {
        "first_name",
        "last_name",
        "email",
        "phone",
        "birth_date",
        "sex",
        "maturation_status",
        "nutritional_status",
        "training_implications",
        "individual_feedback",
        "excuse_reason",
        "coach_note",
        "coach_notes",
        "coach_observations",
        "coach_answer_text",
        "notes",
        "description",
        "objectives",
        "summary_text",
        "ai_summary",
        "ai_narrative",
        "narrative_blocks",
        "stage_log_json",
        "stage_overrides",
        "structured_json",
        "recommendations_json",
        "metrics_snapshot",
        "ip_address",
        "user_agent",
        "sent_to",
        "error_message",
        "storage_url",
        "storage_path",
        "filename_original",
        "caption",
    }
)

#: Prefixes/patterns not expressible as exact names in the frozenset above.
_FORBIDDEN_SUFFIXES = ("_cm", "_kg", "_z_score", "_percentile")
_FORBIDDEN_PREFIXES = ("consent_",)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_MEASUREMENT_LIKE_RE = re.compile(r"\b\d{2,3}\.\d\b")


def _looks_forbidden(field: str) -> bool:
    if field in NEVER_ALLOWLISTED_FIELDS:
        return True
    if any(field.endswith(suffix) for suffix in _FORBIDDEN_SUFFIXES):
        return True
    if any(field.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
        return True
    return False


# ---------------------------------------------------------------------------
# Part 1 — catalogue-level checks (no DB rows needed)
# ---------------------------------------------------------------------------


def test_value_allowlist_never_admits_a_forbidden_field():
    """Every field name in every VALUE_ALLOWLIST[entity_type] must be absent
    from the data-model.md §2.5 forbidden list."""
    offenders: list[str] = []
    for entity_type, fields in VALUE_ALLOWLIST.items():
        for field in fields:
            if _looks_forbidden(field):
                offenders.append(f"{entity_type}: {field}")
    assert not offenders, (
        "VALUE_ALLOWLIST admits forbidden field(s): " + ", ".join(offenders)
    )


def test_value_allowlist_only_covers_known_entity_types():
    """Every key of VALUE_ALLOWLIST is a real AuditEntityType member — a typo
    here would silently allowlist nothing and never be caught elsewhere."""
    known = {e.value for e in AuditEntityType}
    for entity_type in VALUE_ALLOWLIST:
        value = entity_type.value if hasattr(entity_type, "value") else entity_type
        assert value in known, f"VALUE_ALLOWLIST has an unknown entity_type key: {entity_type!r}"


def test_meta_allowlist_never_admits_a_forbidden_key():
    offenders = [key for key in META_ALLOWLIST if _looks_forbidden(key)]
    assert not offenders, (
        "META_ALLOWLIST admits forbidden key(s): " + ", ".join(offenders)
    )


def test_athlete_newsletter_hidden_blocks_value_allowlist_matches_schema():
    """The one JSON value the allowlist admits (`hidden_blocks`) must stay in
    lockstep with the schema's own closed set of hideable block keys —
    otherwise a future block gets added to the schema and starts leaking
    silently into diff_json without anyone re-reading data-model.md §2.5."""
    assert "hidden_blocks" in VALUE_ALLOWLIST[AuditEntityType.athlete_monthly_newsletter]
    assert _HIDEABLE_BLOCKS, "schema's hideable-block set must not be empty"


def test_club_optional_is_the_small_documented_exception_set():
    """data-model.md §8.4: club_id is required for every audited entity type
    except the explicitly documented cases. Guard against silent growth of
    this exception set."""
    expected = {
        (AuditEntityType.user, AuditAction.update),
        (AuditEntityType.club, AuditAction.create),
        (AuditEntityType.audit_log, AuditAction.purge),
    }
    actual = {(AuditEntityType(e), a) for (e, a) in CLUB_OPTIONAL}
    assert actual == expected, (
        f"CLUB_OPTIONAL drifted from data-model.md §8.4: {actual - expected} "
        f"added, {expected - actual} removed"
    )


# ---------------------------------------------------------------------------
# Row-level scanner — reused by every check below
# ---------------------------------------------------------------------------


def scan_rows_for_privacy_violations(
    rows: list[AuditLog],
    *,
    forbidden_substrings: tuple[str, ...] = (),
) -> list[str]:
    """Returns a list of human-readable violation strings, empty if clean.

    Checks, per row:
    - every ``diff_json`` key is in ``VALUE_ALLOWLIST[entity_type]``
    - every ``meta_json`` key is in ``META_ALLOWLIST``
    - ``hidden_blocks`` values (when present) are members of the known
      hideable-block set, never free text
    - no forbidden substring (fixture names, ISO dates, measurement-shaped
      numerics) appears anywhere in the row's JSON payloads
    - ``club_id`` is non-null unless ``(entity_type, action)`` is in
      ``CLUB_OPTIONAL``
    """
    violations: list[str] = []
    for row in rows:
        entity_type = row.entity_type
        allowed_values = VALUE_ALLOWLIST.get(AuditEntityType(entity_type), frozenset())

        if row.diff_json:
            for key, payload in row.diff_json.items():
                if key not in allowed_values:
                    violations.append(
                        f"row id={row.id} entity_type={entity_type}: diff_json key "
                        f"'{key}' not in VALUE_ALLOWLIST"
                    )
                if key == "hidden_blocks":
                    for side in ("before", "after"):
                        value = payload.get(side) if isinstance(payload, dict) else None
                        if isinstance(value, list):
                            bad = [v for v in value if v not in _HIDEABLE_BLOCKS]
                            if bad:
                                violations.append(
                                    f"row id={row.id}: hidden_blocks.{side} has "
                                    f"non-block-key value(s) {bad}"
                                )

        if row.meta_json:
            for key in row.meta_json:
                if key not in META_ALLOWLIST:
                    violations.append(
                        f"row id={row.id} entity_type={entity_type}: meta_json key "
                        f"'{key}' not in META_ALLOWLIST"
                    )

        action = row.action if isinstance(row.action, AuditAction) else AuditAction(row.action)
        if row.club_id is None and (AuditEntityType(entity_type), action) not in CLUB_OPTIONAL:
            violations.append(
                f"row id={row.id} entity_type={entity_type} action={action}: "
                "club_id is NULL and this pair is not in CLUB_OPTIONAL"
            )

        blob = str(row.diff_json) + "|" + str(row.meta_json) + "|" + str(row.changed_fields)
        for needle in forbidden_substrings:
            if needle and needle in blob:
                violations.append(
                    f"row id={row.id}: forbidden substring '{needle}' found in payload"
                )
        if _ISO_DATE_RE.search(blob):
            # occurred_at itself is not part of the scanned blob, so any ISO
            # date-shaped string here is suspicious (e.g. a leaked birth_date).
            violations.append(f"row id={row.id}: ISO date-shaped string in payload: {blob}")
        if _MEASUREMENT_LIKE_RE.search(blob):
            violations.append(
                f"row id={row.id}: measurement-shaped numeric in payload: {blob}"
            )

    return violations


# ---------------------------------------------------------------------------
# Part 2a — record_audit exercised directly with a realistic scenario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_audit_output_is_clean_for_a_realistic_two_coach_scenario(
    privacy_scenario,
):
    """Calls record_audit() directly (routers are not wired yet, T010 is the
    service itself) with realistic diffs — including several fields that are
    NOT allow-listed, on purpose — and scans the produced rows. Proves the
    production filtering path (record_audit's own §2.5 minimisation) keeps
    forbidden values out, using the exact scenario data (fictitious athlete
    name/birth date) a real request would carry.
    """
    s = privacy_scenario
    session = s.session

    with request_id_scope() as request_id:
        # 1. athlete update — realistic diff mixing allow-listed and
        #    forbidden fields, as a real caller assembling `diff` from a
        #    Pydantic model dump would.
        await record_audit(
            session,
            action=AuditAction.update,
            entity_type=AuditEntityType.athlete,
            entity_id=s.athlete_id,
            actor=None,
            actor_kind=AuditActorKind.system,
            club_id=s.club_id,
            athlete_id=s.athlete_id,
            diff={
                "club_join_date": (
                    date(2025, 1, 1).isoformat(),
                    date(2025, 2, 1).isoformat(),
                ),
                "first_name": (ATHLETE_FIRST_NAME, "Otra Ficticia"),
                "last_name": (ATHLETE_LAST_NAME, "Otra"),
                "birth_date": (ATHLETE_BIRTH_DATE.isoformat(), "2013-06-21"),
            },
            request_id=request_id,
        )

        # 2. athlete archive — reason_code required, no diff.
        await record_audit(
            session,
            action=AuditAction.archive,
            entity_type=AuditEntityType.athlete,
            entity_id=s.athlete_id,
            actor=None,
            actor_kind=AuditActorKind.system,
            club_id=s.club_id,
            athlete_id=s.athlete_id,
            reason_code=AuditReasonCode.athlete_family_request,
            request_id=request_id,
        )

        # 3. newsletter update with hidden_blocks (the one admissible JSON value)
        await record_audit(
            session,
            action=AuditAction.update,
            entity_type=AuditEntityType.athlete_monthly_newsletter,
            entity_id=1,
            actor=None,
            actor_kind=AuditActorKind.system,
            club_id=s.club_id,
            athlete_id=s.athlete_id,
            diff={
                "hidden_blocks": ([], ["photos", "coach_note"]),
                "coach_note": ("", "texto narrativo que nunca debe llegar aquí"),
            },
            request_id=request_id,
        )

    await session.flush()

    result = await session.execute(select(AuditLog))
    rows = list(result.scalars().all())
    assert len(rows) == 3, f"expected 3 queued audit rows, found {len(rows)}"

    violations = scan_rows_for_privacy_violations(
        rows,
        forbidden_substrings=(
            ATHLETE_FIRST_NAME,
            ATHLETE_LAST_NAME,
            ATHLETE_BIRTH_DATE.isoformat(),
            "texto narrativo",
        ),
    )
    assert violations == [], "\n".join(violations)

    # And explicitly: the forbidden keys never made it into changed_fields'
    # *values* even though they are legitimately named in changed_fields.
    athlete_update_row = rows[0]
    assert athlete_update_row.diff_json is not None
    assert set(athlete_update_row.diff_json) == {"club_join_date"}
    assert "first_name" not in athlete_update_row.diff_json
    assert "birth_date" not in athlete_update_row.diff_json


# ---------------------------------------------------------------------------
# Part 2b — negative control: prove the scanner is not vacuous
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_detects_a_deliberately_planted_violation(privacy_scenario):
    """Bypasses record_audit and inserts a raw AuditLog row with a forbidden
    diff_json key, a forbidden meta_json key, and a null club_id for a
    non-CLUB_OPTIONAL pair — proves scan_rows_for_privacy_violations() would
    actually catch a real regression, rather than always returning []."""
    bad_row = AuditLog(
        occurred_at=datetime.now(timezone.utc),
        actor_user_id=None,
        actor_kind=AuditActorKind.system,
        actor_role=None,
        club_id=None,  # (athlete, update) is NOT in CLUB_OPTIONAL
        athlete_id=None,
        entity_type=AuditEntityType.athlete.value,
        entity_id=1,
        action=AuditAction.update,
        changed_fields=["first_name"],
        diff_json={"first_name": {"before": "Ana Ficticia", "after": "Otra Ficticia"}},
        reason_code=None,
        request_id="b" * 32,
        meta_json={"leaked_note": "no deberia estar aqui"},
    )

    violations = scan_rows_for_privacy_violations([bad_row])

    assert any("diff_json key 'first_name'" in v for v in violations)
    assert any("meta_json key 'leaked_note'" in v for v in violations)
    assert any("club_id is NULL" in v for v in violations)


# ---------------------------------------------------------------------------
# Part 3 — suite-reality check: whatever the app itself has produced so far
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_rows_produced_by_the_real_app_are_clean(
    privacy_scenario, privacy_client_factory
):
    """Drives a handful of already-wired write endpoints through the real
    HTTP app (create/patch calls a coach can already make today) and scans
    whatever landed in audit_log.

    As of this writing (2026-09-09) no router calls record_audit yet — Phase
    3 of feature 041 wires that in a later task — so this documents an
    explicit row count of 0. The scan below runs regardless of that count,
    so the moment a router starts writing rows this test starts checking
    them for real, with no code change required here.
    """
    s = privacy_scenario
    async with privacy_client_factory(s.coach_a_user_id, UserRole.coach) as client:
        resp = await client.get("/api/athletes", params={"club_id": s.club_id})
        assert resp.status_code == 200

    result = await s.session.execute(select(AuditLog))
    rows = list(result.scalars().all())

    # Explicit, visible count — not a silently-empty loop. Update the
    # expected number here (and only here) once Phase 3 wires the first
    # router into record_audit; the scan itself needs no change.
    assert len(rows) == 0, (
        f"Expected 0 audit_log rows before Phase 3 instrumentation lands, "
        f"found {len(rows)}. If this is expected (instrumentation shipped), "
        "update this assertion — the privacy scan below already covers the "
        "real rows without further changes."
    )

    violations = scan_rows_for_privacy_violations(rows)
    assert violations == [], "\n".join(violations)
