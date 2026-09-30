"""IMDERTY profile, "contacto principal" and sensitive-data services (feature 047, US2).

Source of truth: ``specs/047-imderty-attendance-sheet/contracts/api.md``
(athlete profile + sensitive data sections), ``data-model.md`` and
``research.md`` R7 (surnames), R8 (sensitive data) and R9 (primary contact).

Inputs / outputs / side effects:
- ``get_or_empty_profile`` is read-only; an athlete with no profile row gets
  an all-null profile (never a 404) plus a proposed surname split.
- ``upsert_profile``, ``set_primary_contact``, ``create_authorization``,
  ``withdraw_authorization`` and ``update_sensitive_data`` mutate the caller's
  session, queue exactly the audit rows they need through ``record_audit``
  (``changed_fields`` only — never ``diff``, so no value reaches
  ``diff_json``) and flush. They never commit: the request's ``get_db``
  owns the transaction, so a failure rolls every write back together.
- ``effective_phone`` / ``resolve_effective_phone`` are pure (FR-022 chain).

Errors are ``ImdertyProfileError`` subclasses carrying an HTTP
``status_code`` and a Spanish ``detail`` so the router maps them one-to-one
(``HTTPException(exc.status_code, exc.detail)``).

Privacy (Ley 1581, FR-010): no function here logs anything, and no error
detail ever echoes a submitted value (document number, surname, address,
phone, EPS or any sensitive value) — only the name of the problem.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from app.models.athlete import Athlete, ParentAthlete
from app.models.audit_log import AuditAction
from app.models.imderty import (
    AthleteImdertyProfile,
    AthleteSensitiveAuthorization,
    AthleteSensitiveData,
    ImdertyBarrio,
    ImdertyDisability,
    ImdertyDocumentType,
    ImdertyEthnicity,
)
from app.models.user import User
from app.schemas.imderty import (
    ImdertyBarrioSummary,
    ImdertyGuardianSummary,
    ImdertyProfileRead,
    ImdertyProfileSensitiveOut,
    ImdertyProfileUpdate,
    ImdertyProfileUpdateResult,
    ImdertySensitiveAuthorizationSummary,
    ImdertySurnameSplit,
    SensitiveAuthorizationCreate,
    SensitiveAuthorizationRead,
    SensitiveDataRead,
    SensitiveDataUpdate,
)
from app.services.audit import AuditEntityType, AuditReasonCode, record_audit
from app.services.imderty.surnames import propose_split, rebuilds

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Warning code returned by ``upsert_profile`` (FR-004: warn, never block).
DUPLICATE_DOCUMENT_WARNING = "duplicate_document_in_club"

#: Where the phone written to the sheet comes from (FR-022 chain).
PhoneSource = Literal["athlete", "primary_guardian", "first_guardian", "none"]

_DIGIT_ONLY_DOCUMENT_TYPES = frozenset(
    {ImdertyDocumentType.rc, ImdertyDocumentType.ti, ImdertyDocumentType.cc}
)

# Editable profile columns, in the order they appear on the form. The
# confirmation flag is handled separately.
_PROFILE_FIELDS: tuple[str, ...] = (
    "first_surname",
    "second_surname",
    "document_type",
    "document_number",
    "address",
    "barrio_id",
    "other_municipality",
    "school",
    "grade",
    "eps",
    "phone",
)
_TEXT_FIELDS = frozenset(
    {
        "first_surname",
        "second_surname",
        "document_number",
        "address",
        "school",
        "eps",
        "phone",
    }
)
_SURNAME_FIELDS = ("first_surname", "second_surname")
_SENSITIVE_FIELDS = ("ethnicity", "disability", "conflict_victim")

#: Loader options a caller of ``effective_phone`` must apply to its athlete
#: query (the function is sync and never triggers a lazy load).
EFFECTIVE_PHONE_LOAD_OPTIONS: tuple[LoaderOption, ...] = (
    selectinload(Athlete.imderty_profile),
    selectinload(Athlete.parents).selectinload(ParentAthlete.parent),
)


# ---------------------------------------------------------------------------
# Errors (router maps status_code/detail one-to-one)
# ---------------------------------------------------------------------------


class ImdertyProfileError(Exception):
    """Base error; ``detail`` never contains a submitted value."""

    status_code: int = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ProfileValidationError(ImdertyProfileError):
    status_code = 422


class GuardianNotLinkedError(ImdertyProfileError):
    status_code = 422

    def __init__(self) -> None:
        super().__init__("El acudiente no está vinculado a este deportista")


class AuthorizationDateInFutureError(ImdertyProfileError):
    status_code = 422

    def __init__(self) -> None:
        super().__init__("La fecha de autorización no puede ser futura")


class AuthorizationAlreadyActiveError(ImdertyProfileError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "Ya existe una autorización de datos sensibles vigente para este deportista"
        )


class NoActiveAuthorizationError(ImdertyProfileError):
    """404: withdraw or read without an active authorization."""

    status_code = 404

    def __init__(self) -> None:
        super().__init__(
            "No hay una autorización de datos sensibles vigente para este deportista"
        )


class AuthorizationRequiredError(ImdertyProfileError):
    """403: writing sensitive data without an active authorization."""

    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "Se requiere una autorización vigente del acudiente para editar datos sensibles"
        )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value: str | None) -> str | None:
    """Strip; an empty or whitespace-only string is stored as NULL."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _has_value(value: str | None) -> bool:
    return bool(value and value.strip())


# ---------------------------------------------------------------------------
# Phone (FR-022)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardianPhone:
    """One guardian link, in link order (earliest ``parent_athlete.id`` first)."""

    link_id: int
    phone: str | None
    is_primary: bool


def resolve_effective_phone(
    own_phone: str | None, guardians: Sequence[GuardianPhone]
) -> tuple[str | None, PhoneSource]:
    """FR-022 chain: athlete's own phone → "contacto principal" → first linked
    guardian (earliest link) → blank.

    A guardian without a phone is skipped to the next step of the chain.
    """
    if _has_value(own_phone):
        return own_phone.strip(), "athlete"  # type: ignore[union-attr]

    ordered = sorted(guardians, key=lambda g: g.link_id)
    primary = next((g for g in ordered if g.is_primary), None)
    if primary is not None and _has_value(primary.phone):
        return primary.phone.strip(), "primary_guardian"  # type: ignore[union-attr]

    if ordered and _has_value(ordered[0].phone):
        first = ordered[0]
        source: PhoneSource = "primary_guardian" if first.is_primary else "first_guardian"
        return first.phone.strip(), source  # type: ignore[union-attr]

    return None, "none"


def _guardian_phones(athlete_id: int, links: Sequence[ParentAthlete]) -> list[GuardianPhone]:
    return [
        GuardianPhone(
            link_id=link.id,
            phone=link.parent.phone if link.parent is not None else None,
            is_primary=link.primary_contact_key == athlete_id,
        )
        for link in links
    ]


def effective_phone(athlete: Athlete) -> tuple[str | None, PhoneSource]:
    """Phone for the sheet's column T and its source (FR-022).

    ``athlete.imderty_profile`` and ``athlete.parents`` (with
    ``ParentAthlete.parent``) must already be loaded — use
    ``EFFECTIVE_PHONE_LOAD_OPTIONS`` on the query. Pure, never logs.
    """
    profile = athlete.imderty_profile
    own_phone = profile.phone if profile is not None else None
    return resolve_effective_phone(own_phone, _guardian_phones(athlete.id, athlete.parents))


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _load_profile(db: AsyncSession, athlete_id: int) -> AthleteImdertyProfile | None:
    result = await db.execute(
        select(AthleteImdertyProfile).where(AthleteImdertyProfile.athlete_id == athlete_id)
    )
    return result.scalar_one_or_none()


async def _load_links(db: AsyncSession, athlete_id: int) -> list[ParentAthlete]:
    """Guardian links of the athlete, earliest first, with the fresh
    ``primary_contact_key`` (``populate_existing`` — the primary-contact write
    uses Core UPDATEs that bypass the identity map)."""
    result = await db.execute(
        select(ParentAthlete)
        .options(selectinload(ParentAthlete.parent))
        .where(ParentAthlete.athlete_id == athlete_id)
        .order_by(ParentAthlete.id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def get_active_authorization(
    db: AsyncSession, athlete_id: int
) -> AthleteSensitiveAuthorization | None:
    """The athlete's active authorization (at most one, by ``active_key``)."""
    result = await db.execute(
        select(AthleteSensitiveAuthorization).where(
            AthleteSensitiveAuthorization.athlete_id == athlete_id,
            AthleteSensitiveAuthorization.active_key.is_not(None),
            AthleteSensitiveAuthorization.withdrawn_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _load_sensitive_data(
    db: AsyncSession, athlete_id: int
) -> AthleteSensitiveData | None:
    result = await db.execute(
        select(AthleteSensitiveData).where(AthleteSensitiveData.athlete_id == athlete_id)
    )
    return result.scalar_one_or_none()


def _guardian_summaries(
    athlete_id: int, links: Sequence[ParentAthlete]
) -> list[ImdertyGuardianSummary]:
    return [
        ImdertyGuardianSummary(
            user_id=link.parent_id,
            display_name=link.parent.display_name if link.parent is not None else "",
            has_phone=link.parent is not None and _has_value(link.parent.phone),
            is_primary_contact=link.primary_contact_key == athlete_id,
        )
        for link in links
    ]


def _authorization_summary(
    authorization: AthleteSensitiveAuthorization | None,
) -> ImdertySensitiveAuthorizationSummary | None:
    if authorization is None:
        return None
    return ImdertySensitiveAuthorizationSummary(
        id=authorization.id,
        guardian_user_id=authorization.guardian_user_id,
        authorized_on=authorization.authorized_on,
        active=authorization.is_active,
    )


def _split_is_confirmed(profile: AthleteImdertyProfile | None, last_name: str) -> bool:
    """Confirmed only while the stored split still rebuilds ``last_name``."""
    if profile is None or profile.surname_split_confirmed_at is None:
        return False
    if not profile.first_surname:
        return False
    return rebuilds(last_name, profile.first_surname, profile.second_surname)


async def _build_read(db: AsyncSession, athlete: Athlete) -> ImdertyProfileRead:
    profile = await _load_profile(db, athlete.id)
    links = await _load_links(db, athlete.id)
    authorization = await get_active_authorization(db, athlete.id)

    barrio: ImdertyBarrio | None = None
    if profile is not None and profile.barrio_id is not None:
        barrio = await db.get(ImdertyBarrio, profile.barrio_id)

    proposed_first, proposed_second = propose_split(athlete.last_name or "")
    own_phone = profile.phone if profile is not None else None
    _, phone_source = resolve_effective_phone(
        own_phone, _guardian_phones(athlete.id, links)
    )

    return ImdertyProfileRead(
        athlete_id=athlete.id,
        first_surname=profile.first_surname if profile else None,
        second_surname=profile.second_surname if profile else None,
        surname_split=ImdertySurnameSplit(
            confirmed=_split_is_confirmed(profile, athlete.last_name or ""),
            proposed_first=proposed_first or None,
            proposed_second=proposed_second,
        ),
        document_type=profile.document_type if profile else None,
        document_number=profile.document_number if profile else None,
        address=profile.address if profile else None,
        barrio=ImdertyBarrioSummary.model_validate(barrio) if barrio else None,
        other_municipality=bool(profile.other_municipality) if profile else False,
        school=profile.school if profile else None,
        grade=profile.grade if profile else None,
        eps=profile.eps if profile else None,
        phone=profile.phone if profile else None,
        guardians=_guardian_summaries(athlete.id, links),
        effective_phone_source=phone_source,
        sensitive=ImdertyProfileSensitiveOut(
            authorization=_authorization_summary(authorization)
        ),
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def get_or_empty_profile(db: AsyncSession, athlete: Athlete) -> ImdertyProfileRead:
    """The athlete's IMDERTY profile; all nulls (never 404) when never saved.

    Sensitive **values** are never included — only the authorization summary.
    """
    return await _build_read(db, athlete)


async def _has_duplicate_document(
    db: AsyncSession, athlete: Athlete, document_number: str
) -> bool:
    """Another non-archived athlete of the same club holds this number."""
    result = await db.execute(
        select(AthleteImdertyProfile.athlete_id)
        .join(Athlete, Athlete.id == AthleteImdertyProfile.athlete_id)
        .where(
            Athlete.club_id == athlete.club_id,
            Athlete.id != athlete.id,
            Athlete.deleted_at.is_(None),
            AthleteImdertyProfile.document_number == document_number,
        )
        .limit(1)
    )
    return result.first() is not None


async def upsert_profile(
    db: AsyncSession,
    athlete: Athlete,
    body: ImdertyProfileUpdate,
    actor: User,
) -> ImdertyProfileUpdateResult:
    """Create (lazily) or update the profile from ``body``.

    Only the fields present in the request body are applied, so a client that
    omits a key never wipes it. Validates on the merged state:

    - digits only for R.C / T.I / C.C numbers (FR-004);
    - a barrio and "otro municipio" are mutually exclusive, and a newly
      chosen barrio must exist and be active;
    - ``confirm_surname_split=True`` requires a first surname and a split
      that rebuilds ``athletes.last_name`` (research R7). Editing the
      surnames without confirming clears a previous confirmation.

    Returns the profile plus ``warnings=["duplicate_document_in_club"]`` when
    another athlete of the club holds the same number (a warning, not a block).
    Audit: one ``update`` row with ``changed_fields`` only.
    """
    profile = await _load_profile(db, athlete.id)
    is_new = profile is None

    current: dict[str, Any] = {
        field: (getattr(profile, field) if profile is not None else None)
        for field in _PROFILE_FIELDS
    }
    if current["other_municipality"] is None:
        current["other_municipality"] = False

    submitted = body.model_dump(include=set(_PROFILE_FIELDS) & body.model_fields_set)
    for field in _TEXT_FIELDS & submitted.keys():
        submitted[field] = _clean_text(submitted[field])

    merged = {**current, **submitted}
    # A newly chosen barrio implies "not another municipality" and vice
    # versa, unless the client sent both (then the check below rejects it).
    if "barrio_id" in submitted and "other_municipality" not in submitted:
        if merged["barrio_id"] is not None:
            merged["other_municipality"] = False
    if "other_municipality" in submitted and "barrio_id" not in submitted:
        if merged["other_municipality"]:
            merged["barrio_id"] = None

    # --- validation (merged state) ---------------------------------------
    if merged["other_municipality"] and merged["barrio_id"] is not None:
        raise ProfileValidationError(
            "No se puede indicar un barrio y marcar «otro municipio» al mismo tiempo"
        )

    document_type = merged["document_type"]
    document_number = merged["document_number"]
    if (
        document_type in _DIGIT_ONLY_DOCUMENT_TYPES
        and document_number is not None
        and not document_number.isdigit()
    ):
        raise ProfileValidationError(
            "El número de documento debe contener solo dígitos para este tipo de documento"
        )

    if merged["barrio_id"] is not None and merged["barrio_id"] != current["barrio_id"]:
        barrio = await db.get(ImdertyBarrio, merged["barrio_id"])
        if barrio is None or not barrio.is_active:
            raise ProfileValidationError("El barrio seleccionado no está disponible")

    surnames_changed = any(merged[f] != current[f] for f in _SURNAME_FIELDS)
    confirm_now = body.confirm_surname_split
    if confirm_now:
        if not merged["first_surname"]:
            raise ProfileValidationError(
                "Para confirmar la separación de apellidos se requiere el primer apellido"
            )
        if not rebuilds(
            athlete.last_name or "", merged["first_surname"], merged["second_surname"]
        ):
            raise ProfileValidationError(
                "Los apellidos separados no coinciden con el apellido registrado del deportista"
            )

    # --- apply -------------------------------------------------------------
    if profile is None:
        profile = AthleteImdertyProfile(athlete_id=athlete.id, other_municipality=False)
        db.add(profile)

    changed_fields = [f for f in _PROFILE_FIELDS if merged[f] != current[f]]
    for field in changed_fields:
        setattr(profile, field, merged[field])

    was_confirmed = profile.surname_split_confirmed_at is not None
    if confirm_now:
        if not was_confirmed or surnames_changed:
            profile.surname_split_confirmed_at = _utcnow()
            profile.surname_split_confirmed_by_user_id = actor.id
            changed_fields += [
                "surname_split_confirmed_at",
                "surname_split_confirmed_by_user_id",
            ]
    elif surnames_changed and was_confirmed:
        profile.surname_split_confirmed_at = None
        profile.surname_split_confirmed_by_user_id = None
        changed_fields += [
            "surname_split_confirmed_at",
            "surname_split_confirmed_by_user_id",
        ]

    if changed_fields or is_new:
        profile.updated_by_user_id = actor.id

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.athlete_imderty_profile,
        entity_id=athlete.id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=changed_fields,
    )
    await db.flush()

    warnings: list[str] = []
    if profile.document_number and await _has_duplicate_document(
        db, athlete, profile.document_number
    ):
        warnings.append(DUPLICATE_DOCUMENT_WARNING)

    read = await _build_read(db, athlete)
    return ImdertyProfileUpdateResult(**read.model_dump(), warnings=warnings)


async def clear_surname_confirmation(db: AsyncSession, athlete_id: int) -> bool:
    """Clear a confirmed split (hook for ``PATCH /api/athletes/{id}`` when
    ``last_name`` changes, T031). Returns whether a confirmation was cleared.
    Does not audit: the caller's athlete ``update`` row already names
    ``last_name``.
    """
    profile = await _load_profile(db, athlete_id)
    if profile is None or profile.surname_split_confirmed_at is None:
        return False
    profile.surname_split_confirmed_at = None
    profile.surname_split_confirmed_by_user_id = None
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# "Contacto principal" (FR-022a, research R9)
# ---------------------------------------------------------------------------


async def set_primary_contact(
    db: AsyncSession,
    athlete: Athlete,
    guardian_user_id: int | None,
    actor: User,
) -> list[ImdertyGuardianSummary]:
    """Mark ``guardian_user_id`` as the athlete's only "contacto principal";
    ``None`` clears the mark.

    Raises ``GuardianNotLinkedError`` (422) when the user is not a guardian
    linked to the athlete. The previous key is cleared before the new one is
    set, in the same transaction, so the UNIQUE ``primary_contact_key`` never
    sees two rows for the athlete. Audit: one ``update`` row per link whose
    mark changed (``changed_fields=["primary_contact_key"]``).
    """
    links = await _load_links(db, athlete.id)
    target: ParentAthlete | None = None
    if guardian_user_id is not None:
        target = next((link for link in links if link.parent_id == guardian_user_id), None)
        if target is None:
            raise GuardianNotLinkedError()

    to_clear = [
        link
        for link in links
        if link.primary_contact_key is not None and (target is None or link.id != target.id)
    ]
    to_set = target if target is not None and target.primary_contact_key is None else None

    # Audit rows are queued before any write so they share its unit of work
    # (``parent_athlete`` is an AUDIT_STRICT table).
    for link in [*to_clear, *([to_set] if to_set is not None else [])]:
        await record_audit(
            db,
            action=AuditAction.update,
            entity_type=AuditEntityType.parent_athlete,
            entity_id=link.id,
            actor=actor,
            club_id=athlete.club_id,
            athlete_id=athlete.id,
            changed_fields=["primary_contact_key"],
        )

    # ``primary_contact_key`` is UNIQUE, so ``to_clear`` holds at most one
    # link in practice; one keyed UPDATE per link keeps it explicit.
    for link in to_clear:
        await db.execute(
            update(ParentAthlete)
            .where(ParentAthlete.id == link.id)
            .values(primary_contact_key=None)
            .execution_options(synchronize_session=False)
        )
    if to_set is not None:
        await db.execute(
            update(ParentAthlete)
            .where(ParentAthlete.id == to_set.id)
            .values(primary_contact_key=athlete.id)
            .execution_options(synchronize_session=False)
        )
    await db.flush()

    return _guardian_summaries(athlete.id, await _load_links(db, athlete.id))


async def list_guardians(db: AsyncSession, athlete: Athlete) -> list[ImdertyGuardianSummary]:
    """Guardians of the athlete (earliest link first) with the primary mark."""
    return _guardian_summaries(athlete.id, await _load_links(db, athlete.id))


# ---------------------------------------------------------------------------
# Sensitive-data authorization (FR-006, FR-007, research R8)
# ---------------------------------------------------------------------------


def _authorization_read(authorization: AthleteSensitiveAuthorization) -> SensitiveAuthorizationRead:
    return SensitiveAuthorizationRead(
        id=authorization.id,
        guardian_user_id=authorization.guardian_user_id,
        authorized_on=authorization.authorized_on,
        active=authorization.is_active,
    )


async def create_authorization(
    db: AsyncSession,
    athlete: Athlete,
    body: SensitiveAuthorizationCreate,
    actor: User,
) -> SensitiveAuthorizationRead:
    """Record the guardian's express authorization and create the sensitive
    data row with the official defaults (FR-008): ethnicity
    ``NO SABE NO RESPONDE``, disability ``N/A``, victim ``None``.

    409 when an active authorization exists; 422 when the guardian is not
    linked to the athlete or the date is in the future. Audit: ``create``.
    """
    if body.authorized_on > date.today():
        raise AuthorizationDateInFutureError()

    if await get_active_authorization(db, athlete.id) is not None:
        raise AuthorizationAlreadyActiveError()

    linked = await db.execute(
        select(ParentAthlete.id).where(
            ParentAthlete.athlete_id == athlete.id,
            ParentAthlete.parent_id == body.guardian_user_id,
        )
    )
    if linked.first() is None:
        raise GuardianNotLinkedError()

    authorization = AthleteSensitiveAuthorization(
        athlete_id=athlete.id,
        guardian_user_id=body.guardian_user_id,
        authorized_on=body.authorized_on,
        recorded_by_user_id=actor.id,
        recorded_at=_utcnow(),
        active_key=athlete.id,
    )
    db.add(authorization)
    await db.flush()

    # A row can only exist under an active authorization; none should be
    # left over, but a stale one would violate the 1:1 PK.
    await db.execute(
        delete(AthleteSensitiveData).where(AthleteSensitiveData.athlete_id == athlete.id)
    )
    db.add(
        AthleteSensitiveData(
            athlete_id=athlete.id,
            authorization_id=authorization.id,
            ethnicity=ImdertyEthnicity.NO_SABE_NO_RESPONDE,
            disability=ImdertyDisability.NA,
            conflict_victim=None,
            updated_by_user_id=actor.id,
        )
    )

    await record_audit(
        db,
        action=AuditAction.create,
        entity_type=AuditEntityType.athlete_sensitive_authorization,
        entity_id=authorization.id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=["guardian_user_id", "authorized_on"],
    )
    await db.flush()
    return _authorization_read(authorization)


async def withdraw_authorization(
    db: AsyncSession,
    athlete: Athlete,
    actor: User,
) -> SensitiveAuthorizationRead:
    """Withdraw the active authorization and **erase** the three values (FR-007).

    Sets ``withdrawn_at/by`` and ``active_key=NULL`` and deletes
    ``athlete_sensitive_data`` in the same transaction. 404 when there is no
    active authorization. Audit: ``update`` with field names only and
    ``reason_code=withdrawn``.
    """
    authorization = await get_active_authorization(db, athlete.id)
    if authorization is None:
        raise NoActiveAuthorizationError()

    await db.execute(
        delete(AthleteSensitiveData).where(AthleteSensitiveData.athlete_id == athlete.id)
    )
    authorization.withdrawn_at = _utcnow()
    authorization.withdrawn_by_user_id = actor.id
    authorization.active_key = None

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.athlete_sensitive_authorization,
        entity_id=authorization.id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=["active_key", "withdrawn_at", "withdrawn_by_user_id"],
        reason_code=AuditReasonCode.withdrawn,
    )
    await db.flush()
    return _authorization_read(authorization)


# ---------------------------------------------------------------------------
# Sensitive data (values)
# ---------------------------------------------------------------------------


async def get_sensitive_data(db: AsyncSession, athlete: Athlete) -> SensitiveDataRead:
    """The three values; ``NoActiveAuthorizationError`` (404) without an
    active authorization."""
    if await get_active_authorization(db, athlete.id) is None:
        raise NoActiveAuthorizationError()
    data = await _load_sensitive_data(db, athlete.id)
    if data is None:
        raise NoActiveAuthorizationError()
    return SensitiveDataRead.model_validate(data)


async def update_sensitive_data(
    db: AsyncSession,
    athlete: Athlete,
    body: SensitiveDataUpdate,
    actor: User,
) -> SensitiveDataRead:
    """Set the three values; ``AuthorizationRequiredError`` (403) without an
    active authorization. Values are already validated against the official
    lists by the schema enums. Audit: ``update`` with ``changed_fields`` only.
    """
    authorization = await get_active_authorization(db, athlete.id)
    if authorization is None:
        raise AuthorizationRequiredError()

    data = await _load_sensitive_data(db, athlete.id)
    changed_fields: list[str]
    if data is None:
        data = AthleteSensitiveData(
            athlete_id=athlete.id,
            authorization_id=authorization.id,
            ethnicity=body.ethnicity,
            disability=body.disability,
            conflict_victim=body.conflict_victim,
        )
        db.add(data)
        changed_fields = list(_SENSITIVE_FIELDS)
    else:
        changed_fields = [f for f in _SENSITIVE_FIELDS if getattr(data, f) != getattr(body, f)]
        for field in changed_fields:
            setattr(data, field, getattr(body, field))
        data.authorization_id = authorization.id
    if changed_fields:
        data.updated_by_user_id = actor.id

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.athlete_sensitive_data,
        entity_id=athlete.id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=changed_fields,
    )
    await db.flush()
    return SensitiveDataRead.model_validate(data)
