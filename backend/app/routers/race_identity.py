"""Router ``/api/race-identity/*`` — revisión de identidad de competidores
(feature 044, US4, FR-016…FR-022).

Contrato: ``specs/044-race-history-backfill/contracts/identity-review-api.md``.
Servicio: ``app/services/race/identity_review.py`` (candidatos, decisiones,
reversión) y ``app/services/race/identity_resolver.py`` (usado por el
ingestor). Este router es solo la cáscara HTTP: traduce las excepciones de
dominio del servicio a códigos de estado y arma las respuestas con
``candidate_view``/``record_view`` — nunca desde JSON crudo.

Endpoints:

| Método | Path                              | Propósito                          |
|--------|-----------------------------------|-------------------------------------|
| POST   | ``/rebuild``                      | Recalcula la cola sobre todo el universo |
| GET    | ``/candidates``                   | Cola paginada, ``score DESC``       |
| GET    | ``/summary``                      | ``{pending, same_person, different_people}`` |
| POST   | ``/candidates/{id}/decide``       | Registra la decisión del coach      |
| POST   | ``/candidates/{id}/reverse``      | Devuelve un candidato decidido a ``pending`` |

RBAC: ``require_role([admin, coach])`` en los cinco — padres y atletas
bloqueados (403). El commit de un import histórico (``POST
/api/race-analysis/imports/{id}/commit``) corre este mismo ``rebuild`` como
candado antes de mutar nada (``routers/race_imports.py`` T050); este router
es la superficie que el coach usa para resolver la cola manualmente.

Privacidad: fuera del asistente de importación, ``IdentityRecordRead``
(``left``/``right``) es el único schema que serializa ``city`` — coach/admin
only, nunca a un padre.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.user import User, UserRole
from app.routers.race_imports import IDENTITY_REBUILD_TIMEOUT_S, load_identity_rows
from app.schemas.race_identity import (
    IdentityCandidatePageRead,
    IdentityCandidateRead,
    IdentityDecisionIn,
    IdentityDecisionOut,
    IdentityReversalOut,
    IdentitySummaryRead,
    RebuildResultRead,
)
from app.services.race import identity_review
from app.services.race.identity_review import (
    CandidateNotDecided,
    CandidateNotFound,
    CandidateNotPending,
    IdentityDecisionConflict,
)

logger = logging.getLogger(__name__)

router = APIRouter()

#: Mensajes es-CO por código de ``IdentityDecisionConflict`` (contrato
#: §Candidate rules). Nunca lleva nombre, club ni ciudad — el código ya es
#: suficiente para que el coach entienda qué revisar manualmente.
_CONFLICT_MESSAGES: dict[str, str] = {
    "linked_to_different_athletes": (
        "No se puede fusionar: los dos lados ya están vinculados a atletas "
        "distintos del club."
    ),
    "shared_valida": (
        "No se puede fusionar: ambos compitieron en la misma válida — no "
        "pueden ser la misma persona."
    ),
    "already_same_competitor": "Los dos lados ya son el mismo competidor.",
    "linked_competitor_ambiguous": (
        "Este competidor está vinculado a un deportista del club. "
        "Desvincúlalo, decide y vuelve a vincularlo."
    ),
}


# ---------------------------------------------------------------------------
# POST /rebuild
# ---------------------------------------------------------------------------


@router.post("/rebuild", response_model=RebuildResultRead)
async def rebuild_identity_candidates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RebuildResultRead:
    """Recalcula la cola de revisión sobre competidores existentes + imports
    en staging.

    Idempotente por ``pair_hash``: nunca reinicia una decisión ya tomada. El
    contrato fija un presupuesto de trabajo real ≤ 10 s; esta ruta corta en
    ``IDENTITY_REBUILD_TIMEOUT_S`` (30 s) para no bloquear la petición
    indefinidamente bajo carga — un timeout no persiste nada (``rebuild``
    solo hace ``flush`` tras terminar el cálculo completo).
    """
    try:
        result = await identity_review.rebuild(
            db, rows_loader=load_identity_rows, timeout_s=IDENTITY_REBUILD_TIMEOUT_S
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "identity_rebuild_timeout",
                "message": (
                    "El recálculo de identidad tardó demasiado. Intenta de "
                    "nuevo en unos minutos."
                ),
            },
        )
    return RebuildResultRead(
        created=result.created,
        unchanged=result.unchanged,
        pending=result.pending,
        removed=result.removed,
        imports_unreadable=result.imports_unreadable,
    )


# ---------------------------------------------------------------------------
# GET /candidates
# ---------------------------------------------------------------------------


@router.get("/candidates", response_model=IdentityCandidatePageRead)
async def list_identity_candidates(
    state: str | None = Query(default=None, description="pending | same_person | different_people"),
    kind: str | None = Query(default=None, description="same_person_suspect | homonym_suspect"),
    page: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> IdentityCandidatePageRead:
    """Cola paginada, ``score DESC`` y luego ``id``. ``page_size`` fijo (20,
    contrato) — el frontend no lo negocia."""
    try:
        result = await identity_review.list_candidates(
            db, state=state, kind=kind, page=page
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "state/kind inválido. state permitido: pending, same_person, "
                "different_people. kind permitido: same_person_suspect, "
                "homonym_suspect."
            ),
        )
    return IdentityCandidatePageRead(
        items=[IdentityCandidateRead(**item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


# ---------------------------------------------------------------------------
# GET /summary
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=IdentitySummaryRead)
async def get_identity_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> IdentitySummaryRead:
    """Alimenta el banner del candado de commit en la pantalla de revisión."""
    counts = await identity_review.summary(db)
    return IdentitySummaryRead(**counts)


# ---------------------------------------------------------------------------
# POST /candidates/{id}/decide
# ---------------------------------------------------------------------------


@router.post("/candidates/{candidate_id}/decide", response_model=IdentityDecisionOut)
async def decide_identity_candidate(
    candidate_id: int,
    body: IdentityDecisionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> IdentityDecisionOut:
    """Registra la decisión del coach sobre un candidato ``pending``.

    Si ambos lados ya son competidores confirmados y distintos, ``same_person``
    los fusiona en el acto (firmas y resultados al competidor más antiguo).
    """
    try:
        outcome = await identity_review.decide(
            db, candidate_id, body.answer.value, actor=current_user
        )
    except CandidateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"candidato {candidate_id} no existe.",
        )
    except CandidateNotPending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "candidate_not_pending",
                "message": "Este candidato ya fue decidido.",
            },
        )
    except IdentityDecisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "message": _CONFLICT_MESSAGES.get(
                    exc.code, "No se puede aplicar la decisión sin perder datos."
                ),
            },
        )
    return IdentityDecisionOut(
        id=outcome.candidate_id,
        state=outcome.state,
        merged=outcome.merged,
        results_moved=outcome.results_moved,
    )


# ---------------------------------------------------------------------------
# POST /candidates/{id}/reverse
# ---------------------------------------------------------------------------


@router.post("/candidates/{candidate_id}/reverse", response_model=IdentityReversalOut)
async def reverse_identity_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> IdentityReversalOut:
    """Devuelve un candidato decidido a ``pending`` y deshace su efecto si ya
    se había confirmado (contrato §Reversal semantics)."""
    try:
        outcome = await identity_review.reverse(db, candidate_id, actor=current_user)
    except CandidateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"candidato {candidate_id} no existe.",
        )
    except CandidateNotDecided:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "candidate_not_decided",
                "message": "Este candidato está pendiente; no hay nada que revertir.",
            },
        )
    return IdentityReversalOut(
        id=outcome.candidate_id,
        state=outcome.state,
        split=outcome.split,
        results_moved=outcome.results_moved,
        links_cleared=outcome.links_cleared,
    )
