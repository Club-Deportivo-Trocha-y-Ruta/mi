"""Closed catalogues for the club-wide audit trail (feature 041).

This module holds only the **Python-only** closed catalogues referenced by
``data-model.md`` §2 and ``contracts/audit-recording.md`` §1.7/§3.1:

- ``AuditEntityType`` — one member per auditable table (§2.3).
- ``AuditReasonCode`` — the full closed reason-code catalogue (§2.4) plus its
  five request-level sub-enums (``contracts/audit-recording.md`` §3.1),
  ``AuditReasonGroup`` and ``AUDIT_REASON_GROUPS``.
- ``AUDIT_REASON_LABELS`` — the español-neutro label per reason code. The
  backend never persists the label, same discipline as
  ``REVISION_REASON_LABELS`` (``app/schemas/race_imports.py``).
- ``AuditDocumentKind`` — the closed set of ``meta_json.document_kind``
  values for ``export``/``send`` rows (§2.3).
- ``VALUE_ALLOWLIST`` — the only fields whose *values* may reach
  ``diff_json``, keyed by ``entity_type`` (§2.5).
- ``CLUB_OPTIONAL`` and ``META_ALLOWLIST`` — the write-side contract of
  ``record_audit`` (``contracts/audit-recording.md`` §1.7).
- ``AUDITED_ROUTES`` and ``MUTATING_GETS`` — the route-registry coverage
  catalogue (``contracts/audit-recording.md`` §4/§7), plus the
  ``AUDIT_STRICT`` test-lane flush detector (§7, `plan.md` Complexity
  Tracking) that fails a test when an auditable table is mutated in a flush
  whose unit of work queued no matching ``AuditLog`` row.

``record_audit`` itself — the single write entry point — is implemented on
top of this module. Nothing here writes to the database outside of it.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.user import User, UserRole
from app.services.utils.dates_es import format_date_es


# ---------------------------------------------------------------------------
# AuditEntityType — one member per auditable table (data-model.md §2.3)
# ---------------------------------------------------------------------------


class AuditEntityType(StrEnum):
    """Polymorphic discriminator for ``audit_log.entity_type``.

    Closed catalogue validated on write and by the coverage test (FR-009).
    Document exports/sends (FR-005) do NOT get their own entity type — they
    are recorded against the record the document is generated from, with
    ``meta_json.document_kind`` naming the document (see
    ``AuditDocumentKind`` below).
    """

    user = "user"
    club = "club"
    club_member = "club_member"
    athlete = "athlete"
    parent_athlete = "parent_athlete"
    parent_invite = "parent_invite"
    parental_consent = "parental_consent"
    anthropometric_record = "anthropometric_record"
    training_session = "training_session"
    training_session_coach = "training_session_coach"
    session_attendance = "session_attendance"
    session_media = "session_media"
    calendar_event = "calendar_event"
    event_attendance = "event_attendance"
    monthly_report = "monthly_report"
    club_project_profile = "club_project_profile"
    athlete_monthly_newsletter = "athlete_monthly_newsletter"
    athlete_ai_insight = "athlete_ai_insight"
    agent_run = "agent_run"
    race_import = "race_import"
    race_series = "race_series"
    race_event = "race_event"
    race_event_roster = "race_event_roster"
    race_result = "race_result"
    race_competitor = "race_competitor"
    interval_structure = "interval_structure"
    interval_template = "interval_template"
    strava_connection = "strava_connection"
    strava_activity = "strava_activity"
    athlete_ai_explanation = "athlete_ai_explanation"
    audit_log = "audit_log"


# ---------------------------------------------------------------------------
# AuditDocumentKind — meta_json.document_kind for export/send rows (§2.3)
# ---------------------------------------------------------------------------


class AuditDocumentKind(StrEnum):
    growth_pdf = "growth_pdf"
    clearance_docx = "clearance_docx"
    monthly_report_pdf = "monthly_report_pdf"
    monthly_report_docx = "monthly_report_docx"
    newsletter_pdf = "newsletter_pdf"
    newsletter_email = "newsletter_email"
    race_analysis_pdf = "race_analysis_pdf"
    session_instructivo_pdf = "session_instructivo_pdf"


# ---------------------------------------------------------------------------
# AuditReasonCode — closed catalogue (data-model.md §2.4) + Spanish labels
# ---------------------------------------------------------------------------


class AuditReasonCode(StrEnum):
    """Persisted as its string value in ``audit_log.reason_code`` and, where
    the domain keeps its own column, in ``athletes.deleted_reason_code`` /
    ``calendar_events.cancellation_reason_code``. Free text is never
    accepted anywhere — this is the whole point of the catalogue (FR-003).
    """

    # Athlete archive (FR-015)
    athlete_left_club = "athlete_left_club"
    athlete_transferred = "athlete_transferred"
    athlete_season_inactive = "athlete_season_inactive"
    athlete_family_request = "athlete_family_request"
    athlete_duplicate_record = "athlete_duplicate_record"
    athlete_data_correction = "athlete_data_correction"

    # Athlete restore
    restore_mistaken_archive = "restore_mistaken_archive"
    restore_returned_to_club = "restore_returned_to_club"

    # Event / session cancellation (FR-017)
    cancel_weather = "cancel_weather"
    cancel_venue_unavailable = "cancel_venue_unavailable"
    cancel_insufficient_athletes = "cancel_insufficient_athletes"
    cancel_coach_unavailable = "cancel_coach_unavailable"
    cancel_rescheduled = "cancel_rescheduled"
    cancel_organizer_cancelled = "cancel_organizer_cancelled"

    # Account state (FR-020)
    account_staff_rotation = "account_staff_rotation"
    account_end_of_engagement = "account_end_of_engagement"
    account_security = "account_security"
    account_reactivation = "account_reactivation"

    # Parent account removal (FR-018)
    parent_family_request = "parent_family_request"
    parent_duplicate_account = "parent_duplicate_account"

    # Retention (FR-030) — no sub-enum, no group key; never offered in a
    # picker, written only by the purge CLI (contracts/retention-purge.md).
    retention_24m = "retention_24m"


#: Etiquetas legibles (es-CO) para la UI. El backend solo persiste el code.
AUDIT_REASON_LABELS: dict[AuditReasonCode, str] = {
    AuditReasonCode.athlete_left_club: "Se retiró del club",
    AuditReasonCode.athlete_transferred: "Traslado a otro club",
    AuditReasonCode.athlete_season_inactive: "Inactivo esta temporada",
    AuditReasonCode.athlete_family_request: "Solicitud de la familia",
    AuditReasonCode.athlete_duplicate_record: "Registro duplicado",
    AuditReasonCode.athlete_data_correction: "Corrección de datos",
    AuditReasonCode.restore_mistaken_archive: "Archivado por error",
    AuditReasonCode.restore_returned_to_club: "Regresó al club",
    AuditReasonCode.cancel_weather: "Clima adverso",
    AuditReasonCode.cancel_venue_unavailable: "Sede no disponible",
    AuditReasonCode.cancel_insufficient_athletes: "Convocatoria insuficiente",
    AuditReasonCode.cancel_coach_unavailable: "Entrenador no disponible",
    AuditReasonCode.cancel_rescheduled: "Reprogramado",
    AuditReasonCode.cancel_organizer_cancelled: "Cancelado por el organizador",
    AuditReasonCode.account_staff_rotation: "Cambio de personal",
    AuditReasonCode.account_end_of_engagement: "Fin de vinculación",
    AuditReasonCode.account_security: "Motivo de seguridad",
    AuditReasonCode.account_reactivation: "Reincorporación",
    AuditReasonCode.parent_family_request: "Solicitud de la familia",
    AuditReasonCode.parent_duplicate_account: "Cuenta duplicada",
    AuditReasonCode.retention_24m: "Retención: 24 meses cumplidos",
}


# ---------------------------------------------------------------------------
# Five request-level sub-enums (contracts/audit-recording.md §3.1)
#
# Each is a strict subset of AuditReasonCode, written as
# ``AuditReasonCode.<member>.value`` rather than re-typed as a literal, so a
# code is spelled in exactly one place. Typing a request with the full
# AuditReasonCode instead would let e.g. cancel_weather reach an athlete
# archive — the closed sub-enum is the only place a 422 can come from.
# ---------------------------------------------------------------------------


class AthleteArchiveReasonCode(StrEnum):
    athlete_left_club = AuditReasonCode.athlete_left_club.value
    athlete_transferred = AuditReasonCode.athlete_transferred.value
    athlete_season_inactive = AuditReasonCode.athlete_season_inactive.value
    athlete_family_request = AuditReasonCode.athlete_family_request.value
    athlete_duplicate_record = AuditReasonCode.athlete_duplicate_record.value
    athlete_data_correction = AuditReasonCode.athlete_data_correction.value


class AthleteRestoreReasonCode(StrEnum):
    restore_mistaken_archive = AuditReasonCode.restore_mistaken_archive.value
    restore_returned_to_club = AuditReasonCode.restore_returned_to_club.value


class CancelReasonCode(StrEnum):
    cancel_weather = AuditReasonCode.cancel_weather.value
    cancel_venue_unavailable = AuditReasonCode.cancel_venue_unavailable.value
    cancel_insufficient_athletes = AuditReasonCode.cancel_insufficient_athletes.value
    cancel_coach_unavailable = AuditReasonCode.cancel_coach_unavailable.value
    cancel_rescheduled = AuditReasonCode.cancel_rescheduled.value
    cancel_organizer_cancelled = AuditReasonCode.cancel_organizer_cancelled.value


class AccountStateReasonCode(StrEnum):
    account_staff_rotation = AuditReasonCode.account_staff_rotation.value
    account_end_of_engagement = AuditReasonCode.account_end_of_engagement.value
    account_security = AuditReasonCode.account_security.value
    account_reactivation = AuditReasonCode.account_reactivation.value


class ParentRemovalReasonCode(StrEnum):
    parent_family_request = AuditReasonCode.parent_family_request.value
    parent_duplicate_account = AuditReasonCode.parent_duplicate_account.value


class AuditReasonGroup(StrEnum):
    """Exactly the five ``group`` keys of the sub-enums above.

    Iterated by ``GET /api/audit/reason-codes``
    (``contracts/audit-log-api.md`` §13/§14).
    """

    athlete_archive = "athlete_archive"
    athlete_restore = "athlete_restore"
    cancel = "cancel"
    account = "account"
    parent_removal = "parent_removal"


AUDIT_REASON_GROUPS: dict[AuditReasonGroup, type[StrEnum]] = {
    AuditReasonGroup.athlete_archive: AthleteArchiveReasonCode,
    AuditReasonGroup.athlete_restore: AthleteRestoreReasonCode,
    AuditReasonGroup.cancel: CancelReasonCode,
    AuditReasonGroup.account: AccountStateReasonCode,
    AuditReasonGroup.parent_removal: ParentRemovalReasonCode,
}


# ---------------------------------------------------------------------------
# VALUE_ALLOWLIST — the only fields whose values may reach diff_json (§2.5)
#
# Default for every entity not listed and every field not listed: names only
# in changed_fields, no value anywhere. Admissible categories: enum states,
# booleans/flags, dates of events (never a birth date), foreign-key
# identifiers, small counters/versions.
# ---------------------------------------------------------------------------


VALUE_ALLOWLIST: dict[str, frozenset[str]] = {
    AuditEntityType.athlete: frozenset(
        {
            "club_id",
            "club_join_date",
            "parental_consent_obtained",
            "deleted_reason_code",
        }
    ),
    AuditEntityType.user: frozenset({"role", "is_active", "can_login"}),
    AuditEntityType.club_member: frozenset({"club_id", "role_in_club"}),
    AuditEntityType.training_session: frozenset(
        {"status", "session_kind", "scheduled_date", "duration_min", "calendar_event_id"}
    ),
    AuditEntityType.training_session_coach: frozenset({"coach_user_id"}),
    AuditEntityType.session_attendance: frozenset({"status", "archived_at"}),
    AuditEntityType.calendar_event: frozenset(
        {
            "status",
            "event_type",
            "start_at",
            "end_at",
            "all_day",
            "race_event_id",
            "cancellation_reason_code",
        }
    ),
    AuditEntityType.event_attendance: frozenset({"rsvp_status", "actual_status"}),
    AuditEntityType.monthly_report: frozenset(
        {"status", "year", "month", "approved_by_user_id"}
    ),
    # `hidden_blocks` stores the *list of block keys* the coach hid — block
    # keys are static identifiers ("resumen", "carrera", …), never content.
    # This is the one JSON column whose value is admissible; the privacy
    # test asserts each element is a member of the known key set rather than
    # free text.
    AuditEntityType.athlete_monthly_newsletter: frozenset(
        {"status", "year", "month", "edit_version", "hidden_blocks"}
    ),
    AuditEntityType.athlete_ai_insight: frozenset(
        {"coach_approved", "confidence", "is_fallback", "prompt_version", "season", "valida_num"}
    ),
    AuditEntityType.agent_run: frozenset({"status", "prompt_version", "graph_name"}),
    AuditEntityType.race_import: frozenset({"status", "kind", "event_id", "series_id"}),
    AuditEntityType.race_result: frozenset({"deleted_at", "category_id", "competitor_id"}),
    AuditEntityType.race_competitor: frozenset({"athlete_id"}),
    AuditEntityType.strava_connection: frozenset({"athlete_id"}),
    AuditEntityType.anthropometric_record: frozenset({"evaluation_date", "growth_source"}),
}


# ---------------------------------------------------------------------------
# CLUB_OPTIONAL and META_ALLOWLIST (contracts/audit-recording.md §1.7)
# ---------------------------------------------------------------------------


CLUB_OPTIONAL: frozenset[tuple[AuditEntityType, AuditAction]] = frozenset(
    {
        (AuditEntityType.user, AuditAction.update),  # password-reset consumption, profile self-edit
        (AuditEntityType.club, AuditAction.create),  # the club does not exist yet
        (AuditEntityType.audit_log, AuditAction.purge),  # cross-club by definition
    }
)


#: Closed set of the background-job slugs allowed in ``meta_json.job``. A new
#: background job cannot ship its first audit row without an edit to this
#: table — that is the review gate, not an inconvenience.
AUDIT_JOB_SLUGS: frozenset[str] = frozenset(
    {
        "strava_reconcile",
        "orphan_run_reconciliation",
        "anthropometry_backfill",
        "lms_seed",
        "resend_webhook",
        "strava_webhook",
        "interval_match",
        "agent_run_complete",
        "audit_retention",
        "duplicate_cleanup",
    }
)


#: Closed set of ``meta_json`` keys. An unbounded dict is a PII channel —
#: there is no free-text meta key, no ``note``, no ``message``, no
#: ``filename``. This is the union of every ``meta_json`` key the nine
#: contracts of this feature emit; extending one contract's audit table
#: without extending this set is a defect caught by the unit lane, not
#: production (contracts/audit-recording.md §1.7).
META_ALLOWLIST: frozenset[str] = frozenset(
    {
        "document_kind",
        "recipients_count",
        "athlete_count",
        "convocados_count",
        "removed_count",
        "cutoff",
        "period",
        "job",
        "rows",
        "event_type",
        "coach_user_id",
        "target_user_id",
        "parent_user_id",
        "related_entity_id",
        "results_count",
        "competitors_count",
        "previous_status",
        "new_status",
        "event_date",
        "role",
        "role_in_club",
        "set_password_email",
        "step_id",
        "has_edits",
        "stale",
        "supersedes_run_id",
        "race_event_id",
        "is_revision",
        "block",
    }
)


# ---------------------------------------------------------------------------
# REASON_REQUIRED — (entity_type, action) pairs that must carry a reason_code
# (contracts/audit-recording.md §1.5, verbatim from data-model.md §2.4)
# ---------------------------------------------------------------------------


REASON_REQUIRED: frozenset[tuple[str, AuditAction]] = frozenset(
    {
        (AuditEntityType.athlete, AuditAction.archive),
        (AuditEntityType.athlete, AuditAction.restore),
        (AuditEntityType.calendar_event, AuditAction.cancel),
        (AuditEntityType.training_session, AuditAction.cancel),
        (AuditEntityType.user, AuditAction.deactivate),
        (AuditEntityType.user, AuditAction.delete),
        (AuditEntityType.audit_log, AuditAction.purge),
    }
)


# ---------------------------------------------------------------------------
# Errors (contracts/audit-recording.md §1.5)
# ---------------------------------------------------------------------------


class AuditContractError(RuntimeError):
    """A programming error: the caller violated the ``record_audit`` contract.

    Must never be reachable from a well-formed request — the coverage test
    (contracts/audit-recording.md §8/§9) is what proves that. Maps to a
    generic 500 (``backend/app/main.py:68-81``); never surfaced verbatim.
    """


class AuditReasonRequired(ValueError):
    """``(entity_type, action)`` is in ``REASON_REQUIRED`` and no
    ``reason_code`` was supplied. Maps to 422 with the es-CO copy
    ``"Debes seleccionar un motivo para esta acción."``
    """


# ---------------------------------------------------------------------------
# Request-id resolution — defers to app.services.request_context when it
# exists (T011). Imported lazily so this module has no hard dependency on a
# sibling task that may not have landed yet; once request_context.py is in
# place this transparently starts reading the real ContextVar.
# ---------------------------------------------------------------------------


def _current_request_id() -> str | None:
    try:
        from app.services.request_context import current_request_id
    except ImportError:  # pragma: no cover - only until T011 lands
        return None
    return current_request_id()


# ---------------------------------------------------------------------------
# compute_changed_fields (contracts/audit-recording.md §2)
# ---------------------------------------------------------------------------


_UNSET = object()


def _normalise(value: Any) -> Any:
    """Normalise one value for comparison and storage (§2.2).

    Applied to both sides of a diff before comparison and before the value
    ever reaches ``diff_json``. Raises ``AuditContractError`` for anything
    that cannot be serialised — an unserialisable value must never reach a
    JSON column.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (set, frozenset, tuple)):
        return sorted(list(value))
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    raise AuditContractError(
        f"Unserialisable value of type {type(value).__name__} reached "
        "compute_changed_fields/_normalise"
    )


def snapshot(obj: Any, *fields: str) -> dict[str, Any]:
    """Read the listed attributes off an ORM object into a plain dict.

    Call it BEFORE mutating the object; SQLAlchemy attribute history is not
    used, so the caller keeps full control of what is compared (§2).
    """
    return {field: getattr(obj, field) for field in fields}


def compute_changed_fields(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    allow_list: frozenset[str],
) -> tuple[list[str], dict[str, tuple[Any, Any]]]:
    """Return ``(changed_fields, diff)`` for one entity (§2).

    ``changed_fields`` lists EVERY field whose normalised value changed.
    ``diff`` carries the before/after pair ONLY for fields in ``allow_list``.
    A key present in only one mapping is compared against ``_UNSET`` and is
    therefore skipped: it means the caller did not snapshot it, not that it
    changed.
    """
    keys = set(before.keys()) | set(after.keys())
    changed: list[str] = []
    diff: dict[str, tuple[Any, Any]] = {}
    for key in keys:
        before_raw = before.get(key, _UNSET)
        after_raw = after.get(key, _UNSET)
        if before_raw is _UNSET or after_raw is _UNSET:
            continue
        before_norm = _normalise(before_raw)
        after_norm = _normalise(after_raw)
        if before_norm == after_norm:
            continue
        changed.append(key)
        if key in allow_list:
            diff[key] = (before_norm, after_norm)
    changed.sort()
    return changed, diff


# ---------------------------------------------------------------------------
# record_audit — the single write entry point (contracts/audit-recording.md §1)
# ---------------------------------------------------------------------------


_JOB_SLUG_RE = re.compile(r"^[a-z_]{3,40}$")


async def record_audit(
    db: AsyncSession,
    *,
    action: AuditAction,
    entity_type: AuditEntityType,
    entity_id: int,
    actor: User | None,
    actor_kind: AuditActorKind = AuditActorKind.user,
    club_id: int | None,
    athlete_id: int | None = None,
    changed_fields: Sequence[str] | None = None,
    diff: Mapping[str, tuple[Any, Any]] | None = None,
    reason_code: AuditReasonCode | None = None,
    meta: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog | None:
    """Queue one append-only audit row in the caller's transaction.

    Calls ``db.add()`` and returns. It never flushes, never commits and never
    opens a session of its own, so the row shares fate with the business
    write (FR-001, spec.md:168). Returns ``None`` only for the documented
    no-op of §1.4 rule R7.
    """
    # 1. validate
    if not isinstance(action, AuditAction):
        raise AuditContractError(f"Unknown AuditAction: {action!r}")
    try:
        entity_type = AuditEntityType(entity_type)
    except ValueError as exc:
        raise AuditContractError(f"Unknown AuditEntityType: {entity_type!r}") from exc
    if entity_id is None or entity_id <= 0:
        raise AuditContractError(f"entity_id must be a positive int, got {entity_id!r}")

    # 2. actor coherence
    if actor_kind == AuditActorKind.user and actor is None:
        raise AuditContractError("actor_kind=user requires a non-null actor")
    if actor_kind != AuditActorKind.user and actor is not None:
        raise AuditContractError(
            f"actor_kind={actor_kind!r} requires actor=None, got {actor!r}"
        )
    actor_role: UserRole | None = actor.role if actor is not None else None

    # 3. request_id
    resolved_request_id = request_id or _current_request_id()
    if not resolved_request_id:
        raise AuditContractError(
            "No request_id in scope and none passed explicitly to record_audit"
        )

    # 4. reason gate
    if (entity_type, action) in REASON_REQUIRED and reason_code is None:
        raise AuditReasonRequired(
            f"reason_code is required for ({entity_type!r}, {action!r})"
        )

    # 5. no-op gate (R7)
    if action == AuditAction.update and not changed_fields and not diff:
        return None

    # 6. minimise
    resolved_changed_fields = sorted(set(changed_fields or (diff or {}).keys()))

    allowed_values = VALUE_ALLOWLIST.get(entity_type, frozenset())
    diff_json: dict[str, dict[str, Any]] | None = None
    if diff:
        diff_json = {
            key: {"before": pair[0], "after": pair[1]}
            for key, pair in diff.items()
            if key in allowed_values
        }
        if not diff_json:
            diff_json = None

    meta_json: dict[str, Any] | None = None
    if meta:
        for key, value in meta.items():
            if key not in META_ALLOWLIST:
                raise AuditContractError(f"Unknown meta_json key: {key!r}")
            if key == "job":
                slug = value.value if isinstance(value, Enum) else value
                if not isinstance(slug, str) or not _JOB_SLUG_RE.match(slug):
                    raise AuditContractError(
                        f"Invalid meta_json.job slug: {value!r}"
                    )
                if slug not in AUDIT_JOB_SLUGS:
                    raise AuditContractError(f"Unlisted meta_json.job slug: {slug!r}")
        meta_json = dict(meta)

    resolved_reason_code = reason_code.value if isinstance(reason_code, Enum) else reason_code

    # 7. add
    row = AuditLog(
        occurred_at=datetime.now(timezone.utc),
        actor_user_id=actor.id if actor is not None else None,
        actor_kind=actor_kind,
        actor_role=actor_role,
        club_id=club_id,
        athlete_id=athlete_id,
        entity_type=entity_type.value,
        entity_id=entity_id,
        action=action,
        changed_fields=resolved_changed_fields,
        diff_json=diff_json,
        reason_code=resolved_reason_code,
        request_id=resolved_request_id,
        meta_json=meta_json,
    )
    db.add(row)

    # 8. log — counts only, never names or values (§7)
    logging.getLogger(__name__).debug(
        "audit_recorded",
        extra={
            "entity_type": entity_type.value,
            "action": action.value,
            "changed_fields_count": len(resolved_changed_fields),
            "diff_keys_count": len(diff_json) if diff_json else 0,
            "meta_keys_count": len(meta_json) if meta_json else 0,
        },
    )

    # 9. return
    return row


# ---------------------------------------------------------------------------
# Route-registry coverage (contracts/audit-recording.md §4, §7)
#
# AUDITED_ROUTES is the hand-maintained source of truth: one entry per
# mounted route whose method is in {POST, PUT, PATCH, DELETE}, plus every
# member of MUTATING_GETS (§4.13) and the two adjudicated read-only GETs of
# §4.14. It is never derived by walking ``app.routes`` — a registry that
# regenerated itself from the thing it is meant to gate could never miss a
# newly merged mutating route, which is the exact defect T4.1 exists to
# catch (contracts/audit-recording.md §9).
#
# Wave 1 (T017/T018): every one of the 110 keys is ``Exempt``. The eleven
# genuine exemptions of §4.14 carry their real, reviewed reason; the other
# 99 carry "pending instrumentation" — Phase 3 replaces those one at a time
# with an ``Audited(...)`` entry as each site is instrumented. Nothing here
# is a claim that a route is already audited.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Audited:
    """A route that must have already queued at least one ``AuditLog`` row
    for one of ``entities`` by the time its handler returns successfully.
    """

    entities: frozenset[AuditEntityType]
    min_rows: int = 1


@dataclass(frozen=True, slots=True)
class Exempt:
    """A route that intentionally writes no audit row. ``reason`` is the
    verbatim §4.14 sentence (or, for wave 1, the standard placeholder) and
    must be at least 20 characters (T4.3).
    """

    reason: str


AuditPolicy = Audited | Exempt


#: The nine mutating/exporting GETs of §4.13 — the route-walk of T4.1 only
#: scans {POST, PUT, PATCH, DELETE} and would miss all of them.
MUTATING_GETS: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/athletes/{athlete_id}/report/pdf"),
        ("GET", "/api/athletes/{athlete_id}/clearance/docx"),
        ("GET", "/api/clubs/{club_id}/monthly-reports/{year}/{month}/pdf"),
        ("GET", "/api/clubs/{club_id}/monthly-reports/{year}/{month}/docx"),
        ("GET", "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/pdf"),
        (
            "GET",
            "/api/parents/me/athletes/{athlete_id}/newsletters/{newsletter_id}/pdf",
        ),
        ("GET", "/api/intervals/sessions/{training_session_id}/instructivo"),
        ("GET", "/api/race-analysis/runs/{run_id}/pdf"),
        ("GET", "/api/integrations/strava/callback"),
    }
)

_PENDING = "pending instrumentation"

#: §4.1 Auth and profile — 9 keys, 4 genuinely exempt (login/refresh/
#: password-reset request/change-email request), 5 pending.
_AUTH_PROFILE: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/auth/login"): Exempt(
        "Read-only credential check; no row is written."
    ),
    ("POST", "/api/auth/refresh"): Exempt(
        "Token exchange in memory; no row is written."
    ),
    ("POST", "/api/auth/parent-register"): Exempt(_PENDING),
    ("POST", "/api/auth/password-reset/request"): Exempt(
        "Writes only a single-use reset token. Recording it (success or "
        "failure) would turn the history into an account-enumeration oracle."
    ),
    ("POST", "/api/auth/password-reset/confirm"): Exempt(_PENDING),
    ("PATCH", "/api/profile/basic"): Exempt(_PENDING),
    ("POST", "/api/profile/change-password"): Exempt(_PENDING),
    ("POST", "/api/profile/change-email/request"): Exempt(
        "Writes only a pending-verification token; the account is unchanged "
        "and the response is deliberately neutral against enumeration. The "
        "applied change is audited at /change-email/confirm."
    ),
    ("POST", "/api/profile/change-email/confirm"): Exempt(_PENDING),
}

#: §4.2 Staff and clubs — 6 keys, all pending.
_STAFF_CLUBS: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/users"): Exempt(_PENDING),
    ("PATCH", "/api/users/{user_id}"): Exempt(_PENDING),
    ("DELETE", "/api/users/{user_id}"): Exempt(_PENDING),
    ("POST", "/api/clubs/"): Exempt(_PENDING),
    ("PATCH", "/api/clubs/{club_id}"): Exempt(_PENDING),
    ("POST", "/api/clubs/{club_id}/members"): Exempt(_PENDING),
}

#: §4.3 Athletes and their records — 7 keys, all pending.
#:
#: `POST /api/athletes/{athlete_id}/restore` is spec'd in §4.3 ("new,
#: admin-only") but not yet mounted — contract `athlete-archive.md` lands it
#: in a later task. It is intentionally NOT in this registry today; adding
#: an entry for a route that does not exist would fail T4.2 ("every
#: registry key resolves to a mounted route"). `POST
#: /api/athletes/{athlete_id}/report/email` is real today and is listed only
#: in §4.13's table (for symmetry with the GET export beside it), so it is
#: declared here rather than invented a home in that GET-only section.
_ATHLETES: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/athletes"): Exempt(_PENDING),
    ("PATCH", "/api/athletes/{athlete_id}"): Exempt(_PENDING),
    ("DELETE", "/api/athletes/{athlete_id}"): Exempt(_PENDING),
    ("POST", "/api/athletes/{athlete_id}/anthropometry"): Exempt(_PENDING),
    ("POST", "/api/ai/athletes/{athlete_id}/phv-explanation"): Exempt(_PENDING),
    (
        "POST",
        "/api/ai/athletes/{athlete_id}/measurements/{record_id}/explanation",
    ): Exempt(_PENDING),
    ("POST", "/api/athletes/{athlete_id}/report/email"): Exempt(_PENDING),
}

#: §4.4 Parent links and consent — 5 keys, all pending.
_PARENTS_CONSENT: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/parent-athletes"): Exempt(_PENDING),
    ("POST", "/api/parent-athletes/invite"): Exempt(_PENDING),
    ("DELETE", "/api/parent-athletes/{relation_id}"): Exempt(_PENDING),
    ("POST", "/api/me/consent/renew"): Exempt(_PENDING),
    ("POST", "/api/me/consent/withdraw"): Exempt(_PENDING),
}

#: §4.5 Calendar — 5 keys, all pending.
_CALENDAR: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/calendar/events"): Exempt(_PENDING),
    ("PATCH", "/api/calendar/events/{event_id}"): Exempt(_PENDING),
    ("DELETE", "/api/calendar/events/{event_id}"): Exempt(_PENDING),
    ("DELETE", "/api/calendar/events/{event_id}/permanent"): Exempt(_PENDING),
    ("POST", "/api/calendar/events/{event_id}/rsvp"): Exempt(_PENDING),
}

#: §4.6 Training sessions — 10 keys, all pending.
_TRAINING_SESSIONS: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/training-sessions"): Exempt(_PENDING),
    ("PATCH", "/api/training-sessions/{session_id}"): Exempt(_PENDING),
    ("POST", "/api/training-sessions/{session_id}/execute"): Exempt(_PENDING),
    ("DELETE", "/api/training-sessions/{session_id}"): Exempt(_PENDING),
    ("PUT", "/api/training-sessions/{session_id}/attendance"): Exempt(_PENDING),
    (
        "PATCH",
        "/api/training-sessions/{session_id}/attendance/{athlete_id}",
    ): Exempt(_PENDING),
    ("POST", "/api/training-sessions/{session_id}/route-file"): Exempt(_PENDING),
    ("POST", "/api/training-sessions/{session_id}/media"): Exempt(_PENDING),
    (
        "DELETE",
        "/api/training-sessions/{session_id}/media/{media_id}",
    ): Exempt(_PENDING),
    (
        "PATCH",
        "/api/training-sessions/{session_id}/media/{media_id}",
    ): Exempt(_PENDING),
}

#: §4.7 Monthly reports and the club project profile — 5 keys, all pending.
#: The plain-read `GET /api/parents/training/monthly-summary/{year}/{month}`
#: is *not* in this registry — it is a plain read, not a mutating/exporting
#: GET (§4.7 note).
_MONTHLY_REPORTS: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/clubs/{club_id}/monthly-reports"): Exempt(_PENDING),
    (
        "PATCH",
        "/api/clubs/{club_id}/monthly-reports/{year}/{month}/blocks",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/clubs/{club_id}/monthly-reports/{year}/{month}/blocks/{block_key}/regenerate",
    ): Exempt(_PENDING),
    ("PUT", "/api/clubs/{club_id}/project-profile"): Exempt(_PENDING),
    ("PATCH", "/api/clubs/{club_id}/project-profile"): Exempt(_PENDING),
}

#: §4.8 Family newsletters — 8 keys, all pending.
_NEWSLETTERS: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/clubs/{club_id}/monthly-newsletters/batch"): Exempt(_PENDING),
    ("POST", "/api/athletes/{athlete_id}/monthly-newsletters"): Exempt(_PENDING),
    (
        "PATCH",
        "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/regenerate-block",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/approve",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/send",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/athletes/{athlete_id}/monthly-newsletters/attach-insights",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/parents/me/athletes/{athlete_id}/newsletters/{newsletter_id}/read",
    ): Exempt(_PENDING),
}

#: §4.9 AI runs and insights — 12 keys, 3 genuinely exempt, 9 pending.
_AI_RUNS: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/race-analysis/runs"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/runs/{run_id}/hitl/{step_id}"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/runs/{run_id}/invalidate"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/runs/{run_id}/cancel"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/runs/{run_id}/re-execute"): Exempt(_PENDING),
    (
        "POST",
        "/api/race-analysis/race-events/{race_event_id}/runs",
    ): Exempt(_PENDING),
    ("POST", "/api/race-analysis/chat"): Exempt(
        "Stateless LLM call; no DB write (routers/race_analysis.py:1209-1210)."
    ),
    ("POST", "/api/clubs/{club_id}/session-assistant/clarify"): Exempt(
        "Stateless LLM call; no DB write (routers/session_assistant.py:106-165)."
    ),
    ("POST", "/api/clubs/{club_id}/session-assistant/draft"): Exempt(
        "Stateless LLM call; no DB write (routers/session_assistant.py:173)."
    ),
    ("POST", "/api/athletes/{athlete_id}/race-analysis/runs"): Exempt(_PENDING),
    (
        "POST",
        "/api/athletes/{athlete_id}/race-analysis/season-summary",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/athletes/{athlete_id}/race-analysis/insights/{insight_id}/answer",
    ): Exempt(_PENDING),
}

#: §4.10 Race results domain — 18 keys, all pending.
_RACE_RESULTS: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/race-analysis/race-series/"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/imports/parse"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/imports/{parse_id}/dry-run"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/imports/{parse_id}/commit"): Exempt(_PENDING),
    ("POST", "/api/race-analysis/race-events/"): Exempt(_PENDING),
    ("PATCH", "/api/race-analysis/race-events/{race_event_id}"): Exempt(_PENDING),
    ("DELETE", "/api/race-analysis/race-events/{race_event_id}"): Exempt(_PENDING),
    (
        "DELETE",
        "/api/race-analysis/race-events/{race_event_id}/cleanup",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/race-analysis/race-events/{race_event_id}/roster",
    ): Exempt(_PENDING),
    (
        "PATCH",
        "/api/race-analysis/race-events/{race_event_id}/roster/{entry_id}",
    ): Exempt(_PENDING),
    (
        "DELETE",
        "/api/race-analysis/race-events/{race_event_id}/roster/{entry_id}",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/race-analysis/race-events/{race_event_id}/calendar-link",
    ): Exempt(_PENDING),
    (
        "POST",
        "/api/race-analysis/race-events/{race_event_id}/calendar-event",
    ): Exempt(_PENDING),
    (
        "PATCH",
        "/api/race-analysis/race-events/{race_event_id}/conditions",
    ): Exempt(_PENDING),
    (
        "PUT",
        "/api/race-analysis/race-events/race-results/{result_id}/coach-note",
    ): Exempt(_PENDING),
    (
        "DELETE",
        "/api/race-analysis/race-events/race-results/{result_id}/coach-note",
    ): Exempt(_PENDING),
    ("POST", "/api/race-competitors/{competitor_id}/link"): Exempt(_PENDING),
    ("DELETE", "/api/race-competitors/{competitor_id}/link"): Exempt(_PENDING),
}

#: §4.11 Interval training — 8 keys, all pending.
_INTERVALS: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/intervals/structures"): Exempt(_PENDING),
    ("PUT", "/api/intervals/structures/{structure_id}"): Exempt(_PENDING),
    ("DELETE", "/api/intervals/structures/{structure_id}"): Exempt(_PENDING),
    (
        "POST",
        "/api/intervals/structures/{structure_id}/recalculate",
    ): Exempt(_PENDING),
    ("POST", "/api/intervals/templates"): Exempt(_PENDING),
    ("PUT", "/api/intervals/templates/{template_id}"): Exempt(_PENDING),
    ("PATCH", "/api/intervals/templates/{template_id}/archive"): Exempt(_PENDING),
    ("POST", "/api/intervals/templates/{template_id}/attach"): Exempt(_PENDING),
}

#: §4.12 Strava, activities and webhooks — 6 keys, 2 genuinely exempt,
#: 4 pending. Mounted only when ``settings.strava_enabled``; declared
#: unconditionally, T4.2 skips the missing routes when the flag is off.
_STRAVA: dict[tuple[str, str], AuditPolicy] = {
    ("POST", "/api/athletes/{athlete_id}/strava/connect"): Exempt(
        "Builds the OAuth redirect URL only; the write happens in the "
        "audited callback."
    ),
    ("DELETE", "/api/athletes/{athlete_id}/strava/connection"): Exempt(_PENDING),
    ("POST", "/api/integrations/strava/webhook"): Exempt(
        "The handler itself only ACKs (routers/strava_integration.py:376) "
        "and writes nothing. The rows are written after the response by "
        "_process_webhook_event_deferred (:346-374), which has no route of "
        "its own and is specified in the §3.3 non-HTTP caller table."
    ),
    ("POST", "/api/integrations/strava/reconcile"): Exempt(_PENDING),
    ("PATCH", "/api/activities/{activity_id}/link"): Exempt(_PENDING),
    ("POST", "/api/webhooks/resend"): Exempt(_PENDING),
}

#: §4.13 — the nine ``MUTATING_GETS`` keys, all pending in wave 1.
_MUTATING_GET_ENTRIES: dict[tuple[str, str], AuditPolicy] = {
    key: Exempt(_PENDING) for key in MUTATING_GETS
}

#: §4.14 — the two adjudicated read GETs that a POST/PUT/PATCH/DELETE walk
#: and ``MUTATING_GETS`` would never reach on their own (§4.14, penultimate
#: paragraph). Declared with their real, reviewed reason from day one — they
#: are not pending instrumentation, they are settled "this is not an export"
#: verdicts.
_ADJUDICATED_READS: dict[tuple[str, str], AuditPolicy] = {
    (
        "GET",
        "/api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/render",
    ): Exempt(
        "In-app preview of the family e-mail surface (?surface=email, the "
        "only accepted value), admin/coach only "
        "(routers/athlete_monthly_newsletters.py:849-858). It renders HTML "
        "into the coach's own screen; nothing is produced, stored or sent, "
        "so it is a read under FR-005, not an export."
    ),
    ("GET", "/api/training-sessions/{session_id}/media"): Exempt(
        "Media listing for one session "
        "(routers/training_sessions.py:929-950): stored metadata, already "
        "narrowed per role. No file leaves the system and no document is "
        "generated, so FR-005's 'plain page reads MUST NOT be recorded' "
        "governs."
    ),
}

#: The single combined registry (contracts/audit-recording.md §7): 110 keys
#: in wave 1, every one of them ``Exempt``. Phase 3 flips entries to
#: ``Audited(...)`` one at a time as each write site is instrumented.
AUDITED_ROUTES: dict[tuple[str, str], AuditPolicy] = {
    **_AUTH_PROFILE,
    **_STAFF_CLUBS,
    **_ATHLETES,
    **_PARENTS_CONSENT,
    **_CALENDAR,
    **_TRAINING_SESSIONS,
    **_MONTHLY_REPORTS,
    **_NEWSLETTERS,
    **_AI_RUNS,
    **_RACE_RESULTS,
    **_INTERVALS,
    **_STRAVA,
    **_MUTATING_GET_ENTRIES,
    **_ADJUDICATED_READS,
}


# ---------------------------------------------------------------------------
# AUDIT_STRICT flush detector — test lane only (§7, plan.md Complexity
# Tracking).
#
# A session-level `after_flush` listener, active only under
# `APP_ENV=test` + `AUDIT_STRICT=true`. It inspects every instance in
# `session.new | session.dirty | session.deleted` for one belonging to an
# auditable table (`_AUDIT_STRICT_TABLES` below) and fails the test when the
# same flush queued no `AuditLog` row — or, when a `request_id` is bound in
# scope, no `AuditLog` row carrying that exact `request_id`.
#
# It is a DETECTOR, never the recording mechanism: it is blind to the ~20
# Core statements that bypass the ORM identity map (`routers/athletes.py:
# 359-366`, `routers/users.py:333-346`, `services/training/attendance.py:41`,
# `services/calendar/events.py:207,452,484`, `routers/ai.py:428,584`, the raw
# `text()` `agent_runs` layer at `routers/race_analysis.py:635,930,1679`).
# Off by default so it never runs outside an opted-in test.
# ---------------------------------------------------------------------------


#: Table name -> entity type for every auditable table (data-model.md §2.3),
#: keyed by the actual SQLAlchemy ``__tablename__`` rather than the (mostly
#: singular) ``AuditEntityType`` value. ``audit_log`` itself is excluded on
#: purpose: queuing an ``AuditLog`` row must never itself require a second
#: ``AuditLog`` row about it.
_AUDIT_STRICT_TABLES: dict[str, AuditEntityType] = {
    "users": AuditEntityType.user,
    "clubs": AuditEntityType.club,
    "club_members": AuditEntityType.club_member,
    "athletes": AuditEntityType.athlete,
    "parent_athlete": AuditEntityType.parent_athlete,
    "parent_invites": AuditEntityType.parent_invite,
    "parental_consents": AuditEntityType.parental_consent,
    "anthropometric_records": AuditEntityType.anthropometric_record,
    "training_sessions": AuditEntityType.training_session,
    "training_session_coaches": AuditEntityType.training_session_coach,
    "session_attendance": AuditEntityType.session_attendance,
    "session_media": AuditEntityType.session_media,
    "calendar_events": AuditEntityType.calendar_event,
    "event_attendances": AuditEntityType.event_attendance,
    "monthly_reports": AuditEntityType.monthly_report,
    "club_project_profiles": AuditEntityType.club_project_profile,
    "athlete_monthly_newsletters": AuditEntityType.athlete_monthly_newsletter,
    "athlete_ai_insights": AuditEntityType.athlete_ai_insight,
    "agent_runs": AuditEntityType.agent_run,
    "race_imports": AuditEntityType.race_import,
    "race_series": AuditEntityType.race_series,
    "race_events": AuditEntityType.race_event,
    "race_event_roster": AuditEntityType.race_event_roster,
    "race_results": AuditEntityType.race_result,
    "race_competitors": AuditEntityType.race_competitor,
    "interval_structures": AuditEntityType.interval_structure,
    "interval_templates": AuditEntityType.interval_template,
    "strava_connections": AuditEntityType.strava_connection,
    "strava_activities": AuditEntityType.strava_activity,
    "athlete_ai_explanations": AuditEntityType.athlete_ai_explanation,
}


class AuditStrictViolation(AssertionError):
    """Raised by the ``AUDIT_STRICT`` flush detector (test lane only).

    Subclasses ``AssertionError`` so it surfaces as a normal pytest failure
    rather than an unrelated 500.
    """


def _audit_strict_enabled() -> bool:
    """Read live from the environment on every flush (not from a cached
    ``Settings`` instance) so a test can flip ``AUDIT_STRICT`` with
    ``monkeypatch.setenv`` without reloading the app.
    """
    return (
        os.environ.get("APP_ENV") == "test"
        and os.environ.get("AUDIT_STRICT", "").strip().lower() == "true"
    )


@event.listens_for(Session, "after_flush")
def _audit_strict_after_flush(session: Session, flush_context: Any) -> None:
    if not _audit_strict_enabled():
        return

    mutated_tables: set[str] = set()
    for obj in (*session.new, *session.dirty, *session.deleted):
        table_name = getattr(type(obj), "__tablename__", None)
        if table_name in _AUDIT_STRICT_TABLES:
            mutated_tables.add(table_name)
    if not mutated_tables:
        return

    pending_audit_rows = [obj for obj in session.new if isinstance(obj, AuditLog)]
    request_id = _current_request_id()

    if request_id is not None:
        matching = [row for row in pending_audit_rows if row.request_id == request_id]
    else:
        matching = pending_audit_rows

    if not matching:
        raise AuditStrictViolation(
            "AUDIT_STRICT: table(s) "
            f"{sorted(mutated_tables)} mutated in this flush "
            f"(request_id={request_id!r}) without a matching AuditLog row "
            "queued in the same unit of work. Call record_audit() before "
            "the write commits, or — if this mutation is a documented "
            "exemption — verify it is not one of _AUDIT_STRICT_TABLES."
        )


# ---------------------------------------------------------------------------
# Catálogo de frases en español (FR-008, contracts/audit-log-api.md §7)
# ---------------------------------------------------------------------------
#
# `sentence_es` se construye en tiempo de lectura y nunca se persiste (§7.1):
# un solo lugar para auditar la ausencia de PII (el escaneo de privacidad ya
# corre sobre `diff_json`/`meta_json`) y un solo lugar para mantener
# sincronizado con la matriz de instrumentación.

#: Verbos de acción, tercera persona singular, pretérito (§7.3).
AUDIT_ACTION_VERBS: dict[AuditAction, str] = {
    AuditAction.create: "creó",
    AuditAction.update: "actualizó",
    AuditAction.archive: "archivó",
    AuditAction.delete: "eliminó",
    AuditAction.restore: "restauró",
    AuditAction.approve: "aprobó",
    AuditAction.unapprove: "quitó la aprobación de",
    AuditAction.send: "envió",
    AuditAction.export: "descargó",
    AuditAction.cancel: "canceló",
    AuditAction.execute: "ejecutó",
    AuditAction.link: "vinculó",
    AuditAction.unlink: "desvinculó",
    AuditAction.role_change: "cambió el rol de",
    AuditAction.activate: "activó",
    AuditAction.deactivate: "desactivó",
    AuditAction.purge: "purgó",
}

#: Etiqueta es-CO por tipo de entidad, artículo incluido (§7.3).
AUDIT_ENTITY_LABELS: dict[AuditEntityType, str] = {
    AuditEntityType.user: "la cuenta",
    AuditEntityType.club: "el club",
    AuditEntityType.club_member: "la membresía del club",
    AuditEntityType.athlete: "la ficha del deportista",
    AuditEntityType.parent_athlete: "el vínculo con la familia",
    AuditEntityType.parent_invite: "la invitación a la familia",
    AuditEntityType.parental_consent: "el consentimiento de la familia",
    AuditEntityType.anthropometric_record: "la medición antropométrica",
    AuditEntityType.training_session: "la sesión de entrenamiento",
    AuditEntityType.training_session_coach: "el equipo técnico de la sesión",
    AuditEntityType.session_attendance: "el registro de asistencia",
    AuditEntityType.session_media: "el material de la sesión",
    AuditEntityType.calendar_event: "el evento del calendario",
    AuditEntityType.event_attendance: "la asistencia al evento",
    AuditEntityType.athlete_ai_explanation: "la explicación de IA",
    AuditEntityType.audit_log: "el historial de cambios",
    AuditEntityType.monthly_report: "el informe mensual del club",
    AuditEntityType.club_project_profile: "el perfil de proyecto del club",
    AuditEntityType.athlete_monthly_newsletter: "el boletín familiar",
    AuditEntityType.athlete_ai_insight: "el análisis de IA",
    AuditEntityType.agent_run: "el análisis de carrera",
    AuditEntityType.race_import: "la importación de resultados",
    AuditEntityType.race_series: "la serie de válidas",
    AuditEntityType.race_event: "la válida",
    AuditEntityType.race_event_roster: "la convocatoria de la válida",
    AuditEntityType.race_result: "el resultado de carrera",
    AuditEntityType.race_competitor: "el competidor de la carrera",
    AuditEntityType.interval_structure: "la estructura de intervalos",
    AuditEntityType.interval_template: "la plantilla de intervalos",
    AuditEntityType.strava_connection: "la conexión con Strava",
    AuditEntityType.strava_activity: "la actividad de Strava",
}

#: Etiquetas es-CO de `AuditDocumentKind`, para `{documento}` (§7.6).
AUDIT_DOCUMENT_LABELS: dict[AuditDocumentKind, str] = {
    AuditDocumentKind.growth_pdf: "el PDF de crecimiento",
    AuditDocumentKind.clearance_docx: "la autorización médica en DOCX",
    AuditDocumentKind.monthly_report_pdf: "el informe mensual en PDF",
    AuditDocumentKind.monthly_report_docx: "el informe mensual en DOCX",
    AuditDocumentKind.newsletter_pdf: "el boletín familiar en PDF",
    AuditDocumentKind.newsletter_email: "el boletín familiar por correo",
    AuditDocumentKind.race_analysis_pdf: "el análisis de carrera en PDF",
    AuditDocumentKind.session_instructivo_pdf: "el instructivo de la sesión en PDF",
}

#: Etiquetas es-CO por valor de rol (`UserRole` / `ClubRole` comparten los
#: mismos cuatro valores de cadena), para `{rol}` y `{rol_club}` (§7.2).
AUDIT_ROLE_LABELS: dict[str, str] = {
    "admin": "administrador",
    "coach": "entrenador",
    "parent": "familia",
    "athlete": "deportista",
}

#: Nombres de mes es-CO para `{periodo}` (`meta_json.period`, "AAAA-MM").
_PERIOD_MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _format_period_es(period: str) -> str | None:
    """Convierte ``"2026-03"`` en ``"marzo de 2026"``. ``None`` si no calza."""
    try:
        year_str, month_str = period.split("-", 1)
        year = int(year_str)
        month = int(month_str)
        if not 1 <= month <= 12:
            return None
    except (ValueError, AttributeError):
        return None
    return f"{_PERIOD_MONTHS_ES[month - 1]} de {year}"


def format_count_es(count: int) -> str:
    """Renderiza `{conteo}` con su sustantivo (§7.3): ``1`` → ``"1 registro"``,
    cualquier otro ``n`` → ``"{n} registros"``. Nunca se escribe el sustantivo
    aparte en una plantilla para no romper la concordancia en número.
    """
    noun = "registro" if count == 1 else "registros"
    return f"{count} {noun}"


#: Catálogo de plantillas (§7.5). Todo par no listado usa el genérico de
#: §7.4 (`"{actor} {verbo} {etiqueta}."`).
SENTENCE_TEMPLATES: dict[tuple[AuditEntityType, AuditAction], str] = {
    (AuditEntityType.athlete, AuditAction.create): "{actor} creó la ficha de un deportista.",
    (AuditEntityType.athlete, AuditAction.update): "{actor} actualizó la ficha de un deportista.",
    (AuditEntityType.athlete, AuditAction.archive): "{actor} archivó la ficha de un deportista ({motivo}).",
    (AuditEntityType.athlete, AuditAction.restore): "{actor} restauró la ficha de un deportista ({motivo}).",
    (AuditEntityType.athlete, AuditAction.export): "{actor} descargó {documento} de un deportista.",
    (AuditEntityType.athlete, AuditAction.link): "{actor} vinculó una cuenta de familia con un deportista.",
    (AuditEntityType.athlete, AuditAction.unlink): "{actor} desvinculó una cuenta de familia de un deportista.",
    (AuditEntityType.parental_consent, AuditAction.create): "{actor} registró el consentimiento de la familia.",
    (AuditEntityType.parental_consent, AuditAction.update): "{actor} actualizó el consentimiento de la familia.",
    (AuditEntityType.parent_athlete, AuditAction.link): "{actor} vinculó una cuenta de familia con un deportista.",
    (AuditEntityType.parent_athlete, AuditAction.unlink): "{actor} desvinculó una cuenta de familia de un deportista.",
    (AuditEntityType.parent_invite, AuditAction.create): "{actor} envió una invitación a una familia.",
    (AuditEntityType.parent_invite, AuditAction.delete): "{actor} anuló una invitación a una familia.",
    (AuditEntityType.anthropometric_record, AuditAction.create): "{actor} registró una medición antropométrica del {fecha}.",
    (AuditEntityType.anthropometric_record, AuditAction.update): "{actor} actualizó una medición antropométrica del {fecha}.",
    (AuditEntityType.anthropometric_record, AuditAction.delete): "{actor} eliminó una medición antropométrica del {fecha}.",
    (AuditEntityType.training_session, AuditAction.create): "{actor} creó la sesión de entrenamiento del {fecha}.",
    (AuditEntityType.training_session, AuditAction.update): "{actor} actualizó la sesión de entrenamiento del {fecha}.",
    (AuditEntityType.training_session, AuditAction.cancel): "{actor} canceló la sesión de entrenamiento del {fecha} ({motivo}).",
    (AuditEntityType.training_session, AuditAction.execute): "{actor} marcó como ejecutada la sesión de entrenamiento del {fecha}.",
    (AuditEntityType.training_session, AuditAction.delete): "{actor} eliminó la sesión de entrenamiento del {fecha}.",
    (AuditEntityType.training_session, AuditAction.export): "{actor} descargó {documento}.",
    (AuditEntityType.training_session_coach, AuditAction.create): "{actor} agregó un entrenador a la sesión.",
    (AuditEntityType.training_session_coach, AuditAction.delete): "{actor} quitó un entrenador de la sesión.",
    (AuditEntityType.session_attendance, AuditAction.create): "{actor} registró la asistencia de un deportista en la sesión.",
    (AuditEntityType.session_attendance, AuditAction.update): "{actor} actualizó el registro de asistencia de un deportista.",
    (AuditEntityType.session_attendance, AuditAction.archive): "{actor} archivó el registro de asistencia de un deportista retirado de la convocatoria.",
    (AuditEntityType.session_media, AuditAction.create): "{actor} subió material a una sesión.",
    (AuditEntityType.session_media, AuditAction.archive): "{actor} archivó material de una sesión.",
    (AuditEntityType.session_media, AuditAction.delete): "{actor} eliminó material de una sesión.",
    (AuditEntityType.calendar_event, AuditAction.create): "{actor} creó el evento del calendario del {fecha}.",
    (AuditEntityType.calendar_event, AuditAction.update): "{actor} actualizó el evento del calendario del {fecha}.",
    (AuditEntityType.calendar_event, AuditAction.cancel): "{actor} canceló el evento del calendario del {fecha} ({motivo}).",
    (AuditEntityType.calendar_event, AuditAction.delete): "{actor} eliminó el evento del calendario del {fecha}.",
    (AuditEntityType.calendar_event, AuditAction.link): "{actor} vinculó el evento del calendario con una válida.",
    (AuditEntityType.calendar_event, AuditAction.unlink): "{actor} desvinculó el evento del calendario de una válida.",
    (AuditEntityType.event_attendance, AuditAction.create): "{actor} registró la asistencia a un evento.",
    (AuditEntityType.event_attendance, AuditAction.update): "{actor} actualizó la asistencia a un evento.",
    (AuditEntityType.monthly_report, AuditAction.create): "{actor} generó el informe mensual de {periodo}.",
    (AuditEntityType.monthly_report, AuditAction.update): "{actor} actualizó el informe mensual de {periodo}.",
    (AuditEntityType.monthly_report, AuditAction.approve): "{actor} aprobó el informe mensual de {periodo}.",
    (AuditEntityType.monthly_report, AuditAction.unapprove): "{actor} quitó la aprobación del informe mensual de {periodo}.",
    (AuditEntityType.monthly_report, AuditAction.export): "{actor} descargó {documento} de {periodo}.",
    (AuditEntityType.monthly_report, AuditAction.send): "{actor} envió el informe mensual de {periodo}.",
    (AuditEntityType.club_project_profile, AuditAction.create): "{actor} creó el perfil de proyecto del club.",
    (AuditEntityType.club_project_profile, AuditAction.update): "{actor} actualizó el perfil de proyecto del club.",
    (AuditEntityType.athlete_monthly_newsletter, AuditAction.create): "{actor} generó el boletín familiar de {periodo}.",
    (AuditEntityType.athlete_monthly_newsletter, AuditAction.update): "{actor} editó el boletín familiar de {periodo}.",
    (AuditEntityType.athlete_monthly_newsletter, AuditAction.approve): "{actor} aprobó el boletín familiar de {periodo}.",
    (AuditEntityType.athlete_monthly_newsletter, AuditAction.unapprove): "{actor} quitó la aprobación del boletín familiar de {periodo}.",
    (AuditEntityType.athlete_monthly_newsletter, AuditAction.send): "{actor} envió a la familia el boletín de {periodo}.",
    (AuditEntityType.athlete_monthly_newsletter, AuditAction.export): "{actor} descargó {documento} de {periodo}.",
    (AuditEntityType.athlete_ai_insight, AuditAction.create): "{actor} generó un análisis de IA para un deportista.",
    (AuditEntityType.athlete_ai_insight, AuditAction.update): "{actor} actualizó un análisis de IA.",
    (AuditEntityType.athlete_ai_insight, AuditAction.approve): "{actor} aprobó un análisis de IA.",
    (AuditEntityType.athlete_ai_insight, AuditAction.archive): "{actor} archivó un análisis de IA.",
    (AuditEntityType.athlete_ai_explanation, AuditAction.create): "{actor} generó una explicación de IA.",
    (AuditEntityType.agent_run, AuditAction.create): "{actor} lanzó un análisis de carrera.",
    (AuditEntityType.agent_run, AuditAction.approve): "{actor} resolvió la decisión pendiente de un análisis de carrera.",
    (AuditEntityType.agent_run, AuditAction.unapprove): "{actor} rechazó la decisión pendiente de un análisis de carrera.",
    (AuditEntityType.agent_run, AuditAction.cancel): "{actor} canceló un análisis de carrera.",
    (AuditEntityType.agent_run, AuditAction.execute): "{actor} volvió a ejecutar un análisis de carrera.",
    (AuditEntityType.agent_run, AuditAction.export): "{actor} descargó {documento}.",
    (AuditEntityType.race_import, AuditAction.create): "{actor} inició una importación de resultados.",
    (AuditEntityType.race_import, AuditAction.execute): "{actor} confirmó una importación de resultados.",
    (AuditEntityType.race_import, AuditAction.update): "{actor} actualizó una importación de resultados.",
    (AuditEntityType.race_import, AuditAction.delete): "{actor} eliminó una importación de resultados.",
    (AuditEntityType.race_series, AuditAction.create): "{actor} creó una serie de válidas.",
    (AuditEntityType.race_series, AuditAction.update): "{actor} actualizó una serie de válidas.",
    (AuditEntityType.race_event, AuditAction.create): "{actor} creó una válida.",
    (AuditEntityType.race_event, AuditAction.update): "{actor} actualizó una válida.",
    (AuditEntityType.race_event, AuditAction.cancel): "{actor} canceló una válida ({motivo}).",
    (AuditEntityType.race_event_roster, AuditAction.create): "{actor} convocó a un deportista a una válida.",
    (AuditEntityType.race_event_roster, AuditAction.delete): "{actor} retiró a un deportista de la convocatoria de una válida.",
    (AuditEntityType.race_result, AuditAction.create): "{actor} agregó un resultado al acta.",
    (AuditEntityType.race_result, AuditAction.update): "{actor} corrigió un resultado del acta.",
    (AuditEntityType.race_result, AuditAction.delete): "{actor} retiró un resultado del acta.",
    (AuditEntityType.race_result, AuditAction.restore): "{actor} restauró un resultado del acta.",
    (AuditEntityType.race_competitor, AuditAction.link): "{actor} enlazó un competidor con un deportista del club.",
    (AuditEntityType.race_competitor, AuditAction.unlink): "{actor} deshizo el enlace de un competidor con un deportista del club.",
    (AuditEntityType.interval_structure, AuditAction.create): "{actor} creó una estructura de intervalos.",
    (AuditEntityType.interval_structure, AuditAction.update): "{actor} actualizó una estructura de intervalos.",
    (AuditEntityType.interval_template, AuditAction.create): "{actor} creó una plantilla de intervalos.",
    (AuditEntityType.interval_template, AuditAction.update): "{actor} actualizó una plantilla de intervalos.",
    (AuditEntityType.strava_connection, AuditAction.link): "{actor} conectó una cuenta de Strava a un deportista.",
    (AuditEntityType.strava_connection, AuditAction.unlink): "{actor} desconectó la cuenta de Strava de un deportista.",
    (AuditEntityType.strava_activity, AuditAction.create): "{actor} registró una actividad de Strava.",
    (AuditEntityType.strava_activity, AuditAction.link): "{actor} vinculó una actividad de Strava con una sesión.",
    (AuditEntityType.strava_activity, AuditAction.unlink): "{actor} desvinculó una actividad de Strava de una sesión.",
    (AuditEntityType.user, AuditAction.create): "{actor} creó una cuenta de {rol}.",
    (AuditEntityType.user, AuditAction.update): "{actor} actualizó los datos de una cuenta.",
    (AuditEntityType.user, AuditAction.activate): "{actor} activó una cuenta ({motivo}).",
    (AuditEntityType.user, AuditAction.deactivate): "{actor} desactivó una cuenta ({motivo}).",
    (AuditEntityType.user, AuditAction.role_change): "{actor} cambió el rol de una cuenta a {rol}.",
    (AuditEntityType.user, AuditAction.delete): "{actor} eliminó una cuenta de familia ({motivo}).",
    (AuditEntityType.club_member, AuditAction.create): "{actor} agregó una cuenta al club como {rol_club}.",
    (AuditEntityType.club_member, AuditAction.role_change): "{actor} cambió el rol en el club de una cuenta a {rol_club}.",
    (AuditEntityType.club_member, AuditAction.delete): "{actor} quitó una cuenta del club.",
    (AuditEntityType.club, AuditAction.update): "{actor} actualizó los datos del club.",
    (AuditEntityType.audit_log, AuditAction.purge): "{actor} purgó {conteo} del historial ({motivo}).",
}

#: Marcadores válidos dentro de una plantilla (§7.2). Cualquier otro es un
#: defecto de la plantilla, no un dato ausente.
_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _resolve_placeholder(
    name: str, entry: AuditLog, actor_display_name: str
) -> str | None:
    """Resuelve un marcador de §7.2 contra una fila de `audit_log` ya unida
    con el nombre del actor. ``None`` si el dato requerido no está presente
    — dispara la degradación al genérico de §7.4.
    """
    if name == "actor":
        return actor_display_name
    if name == "verbo":
        return AUDIT_ACTION_VERBS.get(entry.action)
    if name == "etiqueta":
        try:
            return AUDIT_ENTITY_LABELS.get(AuditEntityType(entry.entity_type))
        except ValueError:
            return None
    if name == "motivo":
        if not entry.reason_code:
            return None
        try:
            return AUDIT_REASON_LABELS.get(AuditReasonCode(entry.reason_code))
        except ValueError:
            return None
    if name == "periodo":
        meta = entry.meta_json or {}
        period = meta.get("period")
        return _format_period_es(period) if period else None
    if name == "documento":
        meta = entry.meta_json or {}
        kind = meta.get("document_kind")
        if not kind:
            return None
        try:
            return AUDIT_DOCUMENT_LABELS.get(AuditDocumentKind(kind))
        except ValueError:
            return None
    if name == "fecha":
        meta = entry.meta_json or {}
        event_date = meta.get("event_date")
        if event_date:
            return format_date_es(event_date)
        diff = entry.diff_json or {}
        for key in ("scheduled_date", "start_at"):
            value = diff.get(key)
            if isinstance(value, dict) and value.get("after"):
                return format_date_es(value["after"])
        return None
    if name == "rol":
        diff = entry.diff_json or {}
        role_value = None
        role_diff = diff.get("role")
        if isinstance(role_diff, dict):
            role_value = role_diff.get("after")
        if role_value is None:
            meta = entry.meta_json or {}
            role_value = meta.get("role")
        if not role_value:
            return None
        return AUDIT_ROLE_LABELS.get(role_value)
    if name == "rol_club":
        diff = entry.diff_json or {}
        role_diff = diff.get("role_in_club")
        role_value = role_diff.get("after") if isinstance(role_diff, dict) else None
        if not role_value:
            return None
        return AUDIT_ROLE_LABELS.get(role_value)
    if name == "conteo":
        meta = entry.meta_json or {}
        removed_count = meta.get("removed_count")
        if removed_count is None:
            return None
        return format_count_es(removed_count)
    return None


def render_sentence(entry: AuditLog, actor_display_name: str) -> str:
    """Compone `sentence_es` en tiempo de lectura (§7.1, §7.4).

    ``entry`` es la fila de `audit_log` (o cualquier objeto con los mismos
    atributos); ``actor_display_name`` ya viene resuelto por el `LEFT JOIN`
    de §6.1 o por la etiqueta de actor automático de §6.2 — esta función no
    toca la base de datos.
    """
    try:
        entity_type = AuditEntityType(entry.entity_type)
    except ValueError:
        entity_type = None

    template = (
        SENTENCE_TEMPLATES.get((entity_type, entry.action))
        if entity_type is not None
        else None
    )

    if template is not None:
        placeholders = _TEMPLATE_PLACEHOLDER_RE.findall(template)
        values: dict[str, str] = {}
        resolvable = True
        for name in placeholders:
            resolved = _resolve_placeholder(name, entry, actor_display_name)
            if resolved is None:
                resolvable = False
                break
            values[name] = resolved
        if resolvable:
            return template.format(**values)

    # Genérico de §7.4 — garantiza que nunca se muestre `{periodo}` ni `None`.
    verbo = AUDIT_ACTION_VERBS.get(entry.action, str(entry.action))
    etiqueta = (
        AUDIT_ENTITY_LABELS.get(entity_type, entry.entity_type)
        if entity_type is not None
        else entry.entity_type
    )
    return f"{actor_display_name} {verbo} {etiqueta}."
