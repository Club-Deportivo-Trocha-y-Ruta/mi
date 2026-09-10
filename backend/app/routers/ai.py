"""Endpoints `/api/ai/*` — capa de IA.

Convenciones:
  - Padres NO llaman directamente a los endpoints POST. Reciben outputs vía
    `NotificationService` cuando el coach lo solicita. Bloqueado a nivel
    de router con un guard explícito (defense in depth). En cambio SÍ
    pueden leer la caché de los atletas a los que tienen acceso (GET).
  - Si la capa está apagada (`AI_ENABLED=false`) los endpoints que generan
    devuelven **503**. Los endpoints de lectura de caché siguen sirviendo
    contenido previamente generado: el coach debe poder ver lo que se
    generó ayer aunque hoy el LLM esté caído.
  - Errores de la capa se mapean: `LLMTimeoutError`/`LLMUnavailableError`
    → 503; `LLMSchemaError` → 502; `LLMConfigError` → 500.
  - Caché: `(athlete_id, anthropometric_record_id, use_case)`. Una
    medición nueva cambia el `record_id` y por tanto invalida el caché
    implícitamente sin DELETE explícito.
  - **Consentimiento parental (Ley 1581/2012)**: antes de invocar al LLM
    se verifica que el atleta tenga consentimiento vigente con
    `third_party_sharing=True`. Si no, se devuelve **451** (Unavailable
    For Legal Reasons).
  - **Audiencia de la explicación PHV (feature 040, R-12)**: `?audience=
    family|coach` en los endpoints de `phv-explanation`. `family` es el
    default (lo que ya consumían padres/coach). `coach` agrega números
    (velocidad cm/año, meses hasta/desde el PHV) que la versión familiar
    omite a propósito — solo coach/admin pueden pedirla; un padre que
    intente `?audience=coach` recibe 403 aunque tenga acceso al atleta.
    Cada audiencia cachea por separado (`use_case` distinto).
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_anthropometric_record_explainer_use_case,
    get_current_user,
    get_db,
    get_phv_explainer_use_case,
    require_role,
    verify_athlete_access,
)
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.user import User, UserRole
from app.schemas.ai import (
    AIHealthResponse,
    AIStatusResponse,
    AnthropometricRecordExplanationResponse,
    PHVExplanationResponse,
)
from app.services.ai.errors import (
    LLMConfigError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.ai.use_cases.anthropometric_record_explainer import (
    USE_CASE_KEY as RECORD_USE_CASE,
    AnthropometricRecordExplainerUseCase,
)
from app.services.ai.use_cases.phv_explainer import PHVExplainerUseCase
from app.services.audit import AuditAction, AuditEntityType, record_audit
from app.services.privacy import athlete_has_ai_processing_consent
from app.services.race.ai.budget_guard import _sum_cost_last_30d
from app.services.race.ai.runner import has_capacity

logger = logging.getLogger(__name__)
router = APIRouter()

_PHV_USE_CASE = "phv_explainer"
# Feature 040 (R-12): variante para entrenador — mismo texto base, con
# números (velocidad cm/año, meses hasta/desde el PHV) que la versión
# familiar omite. `use_case` distinto → fila de caché distinta, misma
# clave única `(athlete_id, anthropometric_record_id, use_case)`.
_PHV_COACH_USE_CASE = "phv_explanation_coach"


def _use_case_for_audience(audience: Literal["family", "coach"]) -> str:
    return _PHV_COACH_USE_CASE if audience == "coach" else _PHV_USE_CASE


def _ensure_audience_allowed(
    audience: Literal["family", "coach"], current_user: User
) -> None:
    """Solo coach/admin pueden pedir la variante para entrenador.

    Los padres siempre reciben `audience="family"` (es el default y el
    frontend ni siquiera les ofrece el selector) — esta es la barrera
    real (defense in depth) para que un padre no pueda leer la variante
    del entrenador vía query param directo, aunque tenga ownership del
    atleta.
    """
    if audience == "coach" and current_user.role not in (
        UserRole.coach,
        UserRole.admin,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Solo el entrenador o el administrador pueden ver la "
                "explicación en modo entrenador."
            ),
        )


# RBAC de `/status` (feature 033) — mismo patrón que
# `race_analysis.py:115` (`_coach_or_admin`): coach y admin pueden leer
# el hint pre-lanzamiento; padres quedan afuera (defensa en profundidad,
# igual que `_forbid_parents` más abajo en este archivo).
_coach_or_admin = require_role([UserRole.coach, UserRole.admin])

# Ventana "reciente" para `est_wait_seconds` — deliberadamente más corta
# que los 30 días del budget guard: buscamos un típico *reciente*, no
# diluido por runs de hace semanas (contracts/ai-identity.md §4).
_RECENT_LATENCY_WINDOW_DAYS = 7


def _forbid_parents(current_user: User) -> None:
    """Defense in depth — los padres no consumen estos endpoints directamente."""
    if current_user.role == UserRole.parent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los padres no pueden consultar la explicación directamente.",
        )


async def _ensure_ai_consent(athlete_id: int, db: AsyncSession) -> None:
    """Bloquea con 451 si el atleta no tiene consentimiento IA vigente."""
    allowed = await athlete_has_ai_processing_consent(athlete_id, db)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=(
                "Falta consentimiento parental vigente con autorización para "
                "compartir datos con terceros (procesamiento con IA). "
                "Solicita a la familia renovar el consentimiento."
            ),
        )


# ---------------------------------------------------------------------------
# Auditoría de las explicaciones de IA
# (T030, contracts/audit-recording.md §4.3 — fila `athlete_ai_explanation`)
#
# Privacidad (Ley 1581, menores): estas dos rutas son justo donde es fácil
# filtrar un dato del menor. La fila de auditoría registra **el hecho y los
# identificadores** — quién generó una explicación, para qué atleta y sobre
# qué medición — y NUNCA el contenido: ni el texto narrativo, ni el
# `age_group`, ni el `maturation_status`, ni ninguna medida antropométrica.
# La garantía es doble:
#   1. `AuditEntityType.athlete_ai_explanation` no tiene entrada en
#      `VALUE_ALLOWLIST`, así que `record_audit` deja `diff_json` en `None`
#      aunque alguien pase un `diff` por error (§1.2 paso 6, R4).
#   2. Acá jamás se construye un `diff`: solo viajan NOMBRES de columna en
#      `changed_fields`, igual que `coach_answer_text` en §4.9.
# `meta.related_entity_id` lleva el id de la medición: es un identificador,
# no una medida.
# ---------------------------------------------------------------------------


#: Columnas que el `on_duplicate_key_update` reescribe SIEMPRE en una
#: regeneración. Se emiten como lista fija (no como diff calculado) a
#: propósito: comparar el texto anterior con el nuevo exigiría cargar la
#: narrativa del menor solo para decidir si hubo cambio, y una regeneración
#: que devolviera texto idéntico caería en la regla R7 (`update` sin cambios
#: no escribe fila) y perdería el rastro de que el entrenador la pidió.
_EXPLANATION_REWRITTEN_FIELDS = (
    "age_group",
    "generated_at",
    "generated_by_user_id",
    "maturation_status",
    "model",
    "provider",
    "text",
)


async def _cached_explanation_id(
    db: AsyncSession,
    *,
    athlete_id: int,
    anthropometric_record_id: int,
    use_case: str,
) -> int | None:
    """Id de la fila de caché `(athlete_id, record_id, use_case)`, o `None`.

    Pre-SELECT del upsert: decide si la fila de auditoría es `create` o
    `update` (§4.3) y, cuando ya existía, aporta el `entity_id` sin depender
    del `lastrowid` de un `INSERT ... ON DUPLICATE KEY UPDATE`.
    """
    result = await db.execute(
        select(AthleteAIExplanation.id).where(
            AthleteAIExplanation.athlete_id == athlete_id,
            AthleteAIExplanation.anthropometric_record_id == anthropometric_record_id,
            AthleteAIExplanation.use_case == use_case,
        )
    )
    return result.scalar_one_or_none()


async def _record_explanation_audit(
    db: AsyncSession,
    *,
    athlete: Athlete,
    anthropometric_record_id: int,
    use_case: str,
    actor: User,
    previous_id: int | None,
) -> None:
    """Encola la fila de auditoría de una explicación de IA recién generada.

    Debe llamarse DESPUÉS del upsert y ANTES de retornar: comparte la
    transacción del write de negocio, que comitea `get_db`
    (`app/dependencies.py:21`) al terminar el handler — la regla
    transaccional de §1.3 se cumple por construcción en estas dos rutas
    porque el router no comitea por su cuenta.

    Args:
        db: sesión async activa, la misma del upsert.
        athlete: atleta ya resuelto por `verify_athlete_access`; aporta
            `club_id` (paso 2 de la escalera de §1.6) y `athlete_id`.
        anthropometric_record_id: medición a la que se ancla la explicación.
        use_case: clave de caché (`phv_explainer` / `phv_explanation_coach` /
            el `use_case` por medición).
        actor: usuario coach/admin autenticado.
        previous_id: id devuelto por el pre-SELECT; `None` cuando la fila no
            existía y por tanto la acción es `create`.
    """
    entity_id = previous_id
    if entity_id is None:
        entity_id = await _cached_explanation_id(
            db,
            athlete_id=athlete.id,
            anthropometric_record_id=anthropometric_record_id,
            use_case=use_case,
        )
    await record_audit(
        db,
        action=AuditAction.create if previous_id is None else AuditAction.update,
        entity_type=AuditEntityType.athlete_ai_explanation,
        entity_id=entity_id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=(
            None if previous_id is None else list(_EXPLANATION_REWRITTEN_FIELDS)
        ),
        meta={"related_entity_id": anthropometric_record_id},
    )


async def _latest_record(
    db: AsyncSession, athlete_id: int
) -> AnthropometricRecord | None:
    result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete_id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_record_or_404(
    db: AsyncSession, athlete_id: int, record_id: int
) -> AnthropometricRecord:
    """Valida que el record pertenece al atleta; 404 si no."""
    result = await db.execute(
        select(AnthropometricRecord).where(
            AnthropometricRecord.id == record_id,
            AnthropometricRecord.athlete_id == athlete_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medición no encontrada o no pertenece a este atleta.",
        )
    return record


def _aware_utc(dt: datetime) -> datetime:
    """MySQL DATETIME no almacena tzinfo. Reaplicamos UTC antes de serializar."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/health", response_model=AIHealthResponse)
async def ai_health(
    _admin=Depends(require_role([UserRole.admin])),
) -> AIHealthResponse:
    return AIHealthResponse(
        enabled=settings.ai_enabled,
        provider=settings.ai_provider,
        model=settings.ai_model,
    )


async def _recent_p50_latency_seconds(
    db: AsyncSession, days: int = _RECENT_LATENCY_WINDOW_DAYS
) -> int:
    """Duración típica reciente de un run completo, en segundos.

    Misma extracción JSON que `admin_ai_usage()` (`race_analysis.py`
    ~línea 1431) sobre `athlete_ai_insights.metrics_snapshot_json`, pero
    acotada a una ventana corta (default 7 días, no los 30 del budget
    guard) para que el estimado refleje performance *reciente*. Es un
    típico, no una promesa de cola — el frontend lo presenta con "≈".
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        text(
            """
            SELECT
              CAST(JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.latency_ms_total') AS UNSIGNED) AS lat
            FROM athlete_ai_insights
            WHERE generated_at >= :cutoff
              AND JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.latency_ms_total') IS NOT NULL
            """
        ),
        {"cutoff": cutoff},
    )
    rows = result.fetchall() if hasattr(result, "fetchall") else (result.all() if hasattr(result, "all") else [])
    latencies: list[int] = []
    for r in rows:
        try:
            v = r._mapping.get("lat") if hasattr(r, "_mapping") else (getattr(r, "lat", None) or r[0])
            if v is not None:
                latencies.append(int(v))
        except (TypeError, ValueError):
            continue

    if not latencies:
        return 0
    p50_ms = statistics.median(latencies)
    return round(p50_ms / 1000)


@router.get("/status", response_model=AIStatusResponse)
async def ai_status(
    db: AsyncSession = Depends(get_db),
    _coach: User = Depends(_coach_or_admin),
) -> AIStatusResponse:
    """Hint pre-lanzamiento (presupuesto/backpressure) — feature 033.

    Read-only, coach-safe (sin montos en dólares, sin identificadores de
    atletas). Los umbrales replican EXACTAMENTE los del enforcement real
    (`check_budget()` en `budget_guard.py`) para que este hint nunca
    prometa algo que el endpoint de lanzamiento real luego contradiga.
    """
    current_usd_30d = await _sum_cost_last_30d(db)
    budget_usd_30d = settings.race_ai_budget_usd_30d

    if budget_usd_30d <= 0:
        # Defensivo: un presupuesto mal configurado a 0 se trata como
        # agotado, nunca como división por cero.
        budget_remaining_pct = 0
        is_exhausted = True
    else:
        budget_remaining_pct = round(
            max(0.0, 1 - current_usd_30d / budget_usd_30d) * 100
        )
        # `is_exhausted` usa la comparación CRUDA (sin redondear), la
        # misma que dispara `BudgetExceededError` en `check_budget()`
        # (`current >= max_cost_usd_30d`). Derivar "exhausted" del
        # `budget_remaining_pct` YA REDONDEADO puede reportar 0% (y por
        # tanto "exhausted") para un remanente real ínfimo pero positivo
        # (p.ej. gasto=$19.99 de $20 → 0.05% real, redondea a 0) mientras
        # que `check_budget()` con esos mismos números NO bloquearía el
        # lanzamiento — exactamente la deriva que T005's property test
        # existe para atrapar. Anclar `is_exhausted` a la comparación
        # cruda garantiza que este hint y el bloqueo duro NUNCA diverjan.
        is_exhausted = current_usd_30d >= budget_usd_30d

    if is_exhausted:
        budget_status = "exhausted"
    elif budget_remaining_pct < 20:
        budget_status = "warning"
    else:
        budget_status = "ok"

    return AIStatusResponse(
        budget_status=budget_status,
        budget_remaining_pct=budget_remaining_pct,
        concurrency_available=has_capacity(),
        est_wait_seconds=await _recent_p50_latency_seconds(db),
    )


# ---------------------------------------------------------------------------
# PHV explanation (global del atleta)
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/phv-explanation",
    responses={
        200: {"model": PHVExplanationResponse},
        204: {"description": "No hay explicación cacheada para la última medición."},
    },
)
async def get_phv_explanation_cached(
    audience: Literal["family", "coach"] = Query(
        "family",
        description=(
            "'family' (default) es la explicación para padres. 'coach' "
            "agrega velocidad cm/año y meses hasta/desde el PHV — solo "
            "coach/admin."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Devuelve la explicación cacheada para la última medición del atleta.

    Importante: este endpoint NO chequea `ai_enabled`. La idea es que las
    explicaciones generadas previamente sigan disponibles aunque el LLM
    esté caído ahora.

    Padres pueden leer el caché de sus atletas — `verify_athlete_access`
    (barrera real) ya valida el vínculo padre↔atleta. No se expone
    `generated_by_user_id` en el schema, así que no hay fuga de identidad
    del coach. `audience="coach"` está vedado a padres (`_ensure_audience_allowed`).
    """
    _ensure_audience_allowed(audience, current_user)

    latest = await _latest_record(db, athlete.id)
    if latest is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    result = await db.execute(
        select(AthleteAIExplanation).where(
            AthleteAIExplanation.athlete_id == athlete.id,
            AthleteAIExplanation.anthropometric_record_id == latest.id,
            AthleteAIExplanation.use_case == _use_case_for_audience(audience),
        )
    )
    cached = result.scalar_one_or_none()
    if cached is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    payload = PHVExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=_aware_utc(cached.generated_at),
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
    )
    return Response(
        content=payload.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/athletes/{athlete_id}/phv-explanation",
    response_model=PHVExplanationResponse,
)
async def phv_explanation(
    audience: Literal["family", "coach"] = Query(
        "family",
        description=(
            "'family' (default) es la explicación para padres. 'coach' "
            "agrega velocidad cm/año y meses hasta/desde el PHV — solo "
            "coach/admin."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
    use_case: PHVExplainerUseCase = Depends(get_phv_explainer_use_case),
) -> PHVExplanationResponse:
    _forbid_parents(current_user)
    _ensure_audience_allowed(audience, current_user)

    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )

    await _ensure_ai_consent(athlete.id, db)

    # Última medición + hasta 3 anteriores para construir tendencia.
    result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete.id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
        .limit(4)
    )
    history = list(result.scalars().all())
    if not history:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El atleta no tiene mediciones antropométricas registradas.",
        )

    try:
        explanation = await use_case.run(
            athlete=athlete,
            latest_record=history[0],
            history=history,
            audience=audience,
        )
    except (LLMTimeoutError, LLMUnavailableError) as exc:
        logger.warning("ai.unavailable type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )
    except LLMSchemaError as exc:
        logger.warning("ai.schema_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="La respuesta del modelo no cumplió las reglas del club.",
        )
    except LLMConfigError as exc:
        logger.error("ai.config_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuración de IA inválida.",
        )

    resolved_use_case = _use_case_for_audience(audience)
    previous_id = await _cached_explanation_id(
        db,
        athlete_id=athlete.id,
        anthropometric_record_id=history[0].id,
        use_case=resolved_use_case,
    )

    now = datetime.now(timezone.utc)
    stmt = mysql_insert(AthleteAIExplanation).values(
        athlete_id=athlete.id,
        anthropometric_record_id=history[0].id,
        use_case=resolved_use_case,
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
        generated_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_duplicate_key_update(
        text=stmt.inserted.text,
        model=stmt.inserted.model,
        provider=stmt.inserted.provider,
        generated_at=stmt.inserted.generated_at,
        age_group=stmt.inserted.age_group,
        maturation_status=stmt.inserted.maturation_status,
        generated_by_user_id=stmt.inserted.generated_by_user_id,
        updated_at=now,
    )
    await db.execute(stmt)

    # §4.3: `athlete_ai_explanation`·`create` cuando el pre-SELECT no encontró
    # nada, `update` cuando sí. Solo el hecho y los identificadores.
    await _record_explanation_audit(
        db,
        athlete=athlete,
        anthropometric_record_id=history[0].id,
        use_case=resolved_use_case,
        actor=current_user,
        previous_id=previous_id,
    )

    return PHVExplanationResponse(
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
    )


# ---------------------------------------------------------------------------
# Análisis particular por medición
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/measurements/{record_id}/explanation",
    responses={
        200: {"model": AnthropometricRecordExplanationResponse},
        204: {"description": "No hay análisis cacheado para esta medición."},
    },
)
async def get_measurement_explanation_cached(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
) -> Response:
    """Devuelve el análisis cacheado para una medición concreta del atleta.

    No verifica `ai_enabled`: análisis previos siguen accesibles aunque el
    LLM esté caído. Padres pueden leer el caché de sus atletas vinculados.
    """
    record = await _get_record_or_404(db, athlete.id, record_id)

    result = await db.execute(
        select(AthleteAIExplanation).where(
            AthleteAIExplanation.athlete_id == athlete.id,
            AthleteAIExplanation.anthropometric_record_id == record.id,
            AthleteAIExplanation.use_case == RECORD_USE_CASE,
        )
    )
    cached = result.scalar_one_or_none()
    if cached is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # El cache no almacena los campos derivados (deltas) — los recalculamos
    # baratos desde la medición previa.
    delta_h, delta_w, num_prev = await _delta_summary(db, athlete.id, record)

    payload = AnthropometricRecordExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=_aware_utc(cached.generated_at),
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
        record_id=record.id,
        num_previous_measurements=num_prev,
        delta_height_cm=delta_h,
        delta_weight_kg=delta_w,
    )
    return Response(
        content=payload.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/athletes/{athlete_id}/measurements/{record_id}/explanation",
    response_model=AnthropometricRecordExplanationResponse,
)
async def measurement_explanation(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
    use_case: AnthropometricRecordExplainerUseCase = Depends(
        get_anthropometric_record_explainer_use_case
    ),
) -> AnthropometricRecordExplanationResponse:
    _forbid_parents(current_user)

    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )

    await _ensure_ai_consent(athlete.id, db)

    target = await _get_record_or_404(db, athlete.id, record_id)

    # Todas las mediciones previas a target (estrictamente anteriores).
    result = await db.execute(
        select(AnthropometricRecord)
        .where(
            AnthropometricRecord.athlete_id == athlete.id,
            AnthropometricRecord.evaluation_date < target.evaluation_date,
        )
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    priors = list(result.scalars().all())

    try:
        explanation = await use_case.run(
            athlete=athlete,
            target_record=target,
            prior_records=priors,
        )
    except (LLMTimeoutError, LLMUnavailableError) as exc:
        logger.warning("ai.unavailable type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )
    except LLMSchemaError as exc:
        logger.warning("ai.schema_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="La respuesta del modelo no cumplió las reglas del club.",
        )
    except LLMConfigError as exc:
        logger.error("ai.config_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuración de IA inválida.",
        )

    previous_id = await _cached_explanation_id(
        db,
        athlete_id=athlete.id,
        anthropometric_record_id=target.id,
        use_case=RECORD_USE_CASE,
    )

    now = datetime.now(timezone.utc)
    stmt = mysql_insert(AthleteAIExplanation).values(
        athlete_id=athlete.id,
        anthropometric_record_id=target.id,
        use_case=RECORD_USE_CASE,
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
        generated_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_duplicate_key_update(
        text=stmt.inserted.text,
        model=stmt.inserted.model,
        provider=stmt.inserted.provider,
        generated_at=stmt.inserted.generated_at,
        age_group=stmt.inserted.age_group,
        maturation_status=stmt.inserted.maturation_status,
        generated_by_user_id=stmt.inserted.generated_by_user_id,
        updated_at=now,
    )
    await db.execute(stmt)

    # §4.3: mismo criterio create/update que la explicación PHV. Los deltas de
    # talla y peso que van en el response NUNCA entran a la fila.
    await _record_explanation_audit(
        db,
        athlete=athlete,
        anthropometric_record_id=target.id,
        use_case=RECORD_USE_CASE,
        actor=current_user,
        previous_id=previous_id,
    )

    return AnthropometricRecordExplanationResponse(
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
        record_id=target.id,
        num_previous_measurements=explanation.num_previous_measurements,
        delta_height_cm=explanation.delta_height_cm,
        delta_weight_kg=explanation.delta_weight_kg,
    )


async def _delta_summary(
    db: AsyncSession,
    athlete_id: int,
    target: AnthropometricRecord,
) -> tuple[float | None, float | None, int]:
    """Devuelve (delta_height_cm, delta_weight_kg, num_previous) para el response
    de lectura de caché. None si no hay medición previa."""
    result = await db.execute(
        select(AnthropometricRecord)
        .where(
            AnthropometricRecord.athlete_id == athlete_id,
            AnthropometricRecord.evaluation_date < target.evaluation_date,
        )
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    priors = list(result.scalars().all())
    num_prev = len(priors)
    if not priors:
        return None, None, 0
    previous = priors[0]
    delta_h = round(
        float(target.standing_height_cm - previous.standing_height_cm), 1
    )
    delta_w = round(float(target.weight_kg - previous.weight_kg), 1)
    return delta_h, delta_w, num_prev
