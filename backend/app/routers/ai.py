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
    → 503; `LLMSchemaError` → 502; `LLMConfigError` → 500. **Excepción
    (feature 042, T043)**: en `phv-explanation` y
    `measurements/{record_id}/explanation`, `anthro.pipeline.run_analysis`
    absorbe internamente cualquier timeout/indisponibilidad del analista o
    del crítico y resuelve al camino determinista de fallback
    (`critic_verdict="fallback"`, `200`) — esos dos endpoints YA NO pueden
    devolver `503` por esa causa; solo `LLMSchemaError`(→502)/
    `LLMConfigError`(→500) siguen propagando, más el `503` de
    `AI_ENABLED=false` (`contracts/measurement-analysis-api.md` §5).
  - Caché: `(athlete_id, anthropometric_record_id, use_case)`. Una
    medición nueva cambia el `record_id` y por tanto invalida el caché
    implícitamente sin DELETE explícito.
  - **Consentimiento parental (Ley 1581/2012)**: antes de invocar al LLM
    se verifica que el atleta tenga consentimiento vigente con
    `third_party_sharing=True`. Si no, se devuelve **451** (Unavailable
    For Legal Reasons).
  - **Audiencia de la explicación PHV (feature 040, R-12) y del análisis por
    medición (feature 042, T043)**: `?audience=family|coach` en AMBOS pares
    de endpoints (`phv-explanation` y `measurements/{record_id}/explanation`
    — este último gana el parámetro en esta feature,
    `contracts/measurement-analysis-api.md` §0.1). `family` es el default
    (lo que ya consumían padres/coach). `coach` agrega números (velocidad
    cm/año, meses hasta/desde el PHV) que la versión familiar omite a
    propósito — solo coach/admin pueden pedirla; un padre que intente
    `?audience=coach` recibe 403 aunque tenga acceso al atleta. Cada
    audiencia cachea por separado (`use_case` distinto).
  - **Feature 042 (T043) — pipeline estructurado**: ambos pares de
    endpoints generan ahora vía `app.services.ai.anthro.pipeline.
    run_analysis` (reemplaza a `PHVExplainerUseCase`/
    `AnthropometricRecordExplainerUseCase`, que solo siguen vivas para sus
    propios tests unitarios — `contracts/measurement-analysis-api.md`,
    encabezado). El pipeline persiste y audita por su cuenta
    (`app/services/ai/anthro/persist.py`) — este router NUNCA vuelve a
    escribir `AthleteAIExplanation` ni la fila de auditoría directamente
    para estas dos rutas (data-model.md §6, invariante 5: las nueve
    columnas nuevas son de escritura exclusiva de `persist.py`); tras
    `run_analysis()` el router solo relee la fila ya persistida para
    construir la respuesta `v1|v2` (`schemas/ai.py`, T042).
  - **Compuerta familiar por rol, no por `audience` (FR-016)**: en las
    lecturas `GET` de ambos endpoints, un padre (`UserRole.parent`) nunca
    ve una fila cuyo `critic_verdict` sea `flagged`/`fallback`/`skipped`
    (recibe `204`, idéntico a "sin análisis todavía") — un coach que pida
    `?audience=family` para previsualizar SÍ ve el contenido real, marcado,
    porque el coach es el humano en el bucle (`measurement-analysis-api.md`
    §3). `critic_verdict IS NULL` (fila `"v1"` heredada) siempre se trata
    como entregable — esta feature no censura retroactivamente contenido
    anterior al crítico (data-model.md §6, invariante 3).
  - **Excepción de presupuesto de latencia (dos llamadas LLM secuenciales,
    plan.md §Complexity Tracking)**: cada `POST` de este archivo puede
    invocar al LLM hasta CUATRO veces en el peor caso (analista → crítico →
    reanálisis del analista → crítico del reanálisis; normalmente dos) vía
    `run_analysis()`. Esto excede a propósito el presupuesto general de
    escritura (p95 ≤ 1500 ms) — un único LLM call sin crítico fue
    rechazado por el owner (seguridad del contenido antes que latencia).
    Objetivo local: **p95 ≤ 45 s**. Si ese objetivo se excede en
    producción, la salida documentada es migrar este par de endpoints a un
    patrón submit-and-poll (como ya usa el stack de carreras,
    `routers/race_imports.py`) en vez de seguir bloqueando la respuesta
    HTTP — decisión del owner, no de este módulo; `latency_ms`
    (persistido por `persist.py`) es la métrica que permitiría detectar
    ese cruce.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
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
    AnthropometryInsightOut,
    PHVExplanationResponse,
)
from app.services.ai.anthro.guardrails_step import FAMILY_DELIVERABLE_VERDICTS
from app.services.ai.anthro.pipeline import run_analysis
from app.services.ai.errors import LLMConfigError, LLMSchemaError
from app.services.ai.use_cases.anthropometric_record_explainer import (
    USE_CASE_KEY as RECORD_USE_CASE,
)
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

# Feature 042 (T043), contracts/measurement-analysis-api.md §0.1: el análisis
# por medición gana la misma partición por audiencia que el PHV. La clave
# familiar (`RECORD_USE_CASE`) NO cambia — así una fila "v1" existente se
# upgradea en el mismo lugar (mismo `id`) la primera vez que un coach pide
# "Regenerar" tras esta feature, sin dejar una fila v1 huérfana. La clave de
# coach es nueva — no existían filas de coach para este endpoint antes de 042.
_RECORD_COACH_USE_CASE = "anthropometric_record_explainer_coach"


def _use_case_for_audience(audience: Literal["family", "coach"]) -> str:
    return _PHV_COACH_USE_CASE if audience == "coach" else _PHV_USE_CASE


def _record_use_case_for_audience(audience: Literal["family", "coach"]) -> str:
    return _RECORD_COACH_USE_CASE if audience == "coach" else RECORD_USE_CASE


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
# Feature 042 (T043) — persistencia y auditoría de las explicaciones de IA
#
# Desde esta feature, `anthro.pipeline.run_analysis()` (llamado por ambos
# `POST` de este archivo) hace su PROPIA persistencia (upsert de las nueve
# columnas nuevas + prosa en `text`) y su PROPIA fila de auditoría
# (`app/services/ai/anthro/persist.py`, T038 — mismo criterio §4.3 del
# proyecto: solo el hecho `create`/`update` y los identificadores, nunca el
# texto ni ningún dato del menor). Este router YA NO escribe
# `AthleteAIExplanation` ni `audit_log` directamente para estas dos rutas —
# hacerlo sería un doble-write que violaría data-model.md §6, invariante 5
# ("las nueve columnas nuevas son de escritura exclusiva de persist.py").
# Tras `run_analysis()`, el router solo RELEE la fila ya persistida
# (`_explanation_row_or_404`) para construir la respuesta `v1|v2`.
# ---------------------------------------------------------------------------


async def _explanation_row_or_404(db: AsyncSession, explanation_id: int) -> AthleteAIExplanation:
    """Relee la fila que `persist.py` (dentro de `run_analysis`) acaba de escribir.

    `404` aquí sería un bug de orquestación (el id viene de
    `persisted_explanation_id`, devuelto por la MISMA transacción que hizo el
    upsert), nunca una condición de negocio esperada — se usa `scalar_one()`
    a propósito para que ese bug falle ruidoso en vez de silenciarse como un
    `None`.
    """
    result = await db.execute(
        select(AthleteAIExplanation).where(AthleteAIExplanation.id == explanation_id)
    )
    return result.scalar_one()


def _map_structured_fields(
    cached: AthleteAIExplanation, *, current_user: User
) -> dict[str, object]:
    """Deriva los seis campos `v1|v2` (`schemas/ai.py`, T042) desde una fila cacheada.

    Compartido por los cuatro handlers (`GET`/`POST` × PHV/medición) — una
    sola función que sabe leer `AthleteAIExplanation` evita que la lectura
    de caché y la respuesta recién generada puedan divergir en cómo
    interpretan `schema_version`/`critic_verdict` (`contracts/measurement-
    analysis-api.md` §2).

    Colisión de nombres (data-model.md §0): `cached.schema_version` es el
    discriminador de FORMATO DE FILA (`NULL` | `"v2"`) — nunca lo confundas
    con `AnthropometryInsightV1.schema_version` (versión del payload,
    siempre `"v1"` hoy), que vive DENTRO de `cached.structured_json` y ni
    siquiera se lee aquí (el propio `AnthropometryInsightOut` no tiene ese
    campo — T042, deliberado).
    """
    is_row_v2 = cached.schema_version == "v2"
    structured = None
    if is_row_v2 and cached.structured_json:
        structured = AnthropometryInsightOut.model_validate(cached.structured_json)

    # §4 del contrato: `trace_id` solo para coach/admin. `cached.
    # langfuse_trace_id` ya es `None` cuando `LANGFUSE_ENABLED=false` (el
    # caso siempre-verdadero en producción) o cuando la corrida no llegó a
    # abrir su span — este router no vuelve a chequear ese flag, solo el rol.
    is_coach_viewer = current_user.role in (UserRole.coach, UserRole.admin)
    trace_id = cached.langfuse_trace_id if is_coach_viewer else None

    return {
        "schema_version": "v2" if is_row_v2 else "v1",
        "structured": structured,
        "critic_verdict": cached.critic_verdict,
        "is_fallback": cached.critic_verdict == "fallback",
        "prompt_version": cached.prompt_version,
        "trace_id": trace_id,
    }


def _family_gate_blocks(cached: AthleteAIExplanation, *, current_user: User) -> bool:
    """`True` si esta fila NUNCA debe llegar a un padre (FR-016, data-model.md §3).

    Compuerta keyed en el ROL del solicitante, no en `?audience=` —
    `contracts/measurement-analysis-api.md` §3: un coach que pida
    `audience=family` para previsualizar SIGUE viendo el contenido real
    (marcado), porque el coach es el humano en el bucle. `critic_verdict
    IS NULL` (fila `"v1"` heredada, nunca pasó por el crítico) siempre se
    trata como entregable — invariante 3 de `data-model.md` §6: esta
    feature no censura retroactivamente contenido anterior al crítico.
    """
    if current_user.role != UserRole.parent:
        return False
    verdict = cached.critic_verdict
    return verdict is not None and verdict not in FAMILY_DELIVERABLE_VERDICTS


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

    Feature 042 (T043): la compuerta familiar de FR-016 se aplica AQUÍ,
    después de leer la fila — un padre cuya última fila esté
    `flagged`/`fallback`/`skipped` recibe el mismo `204` que "sin análisis
    todavía" (`_family_gate_blocks`, `contracts/measurement-analysis-api.md`
    §3), nunca el contenido marcado.
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
    if cached is None or _family_gate_blocks(cached, current_user=current_user):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    payload = PHVExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=_aware_utc(cached.generated_at),
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
        **_map_structured_fields(cached, current_user=current_user),
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
) -> PHVExplanationResponse:
    """Genera (o regenera) el análisis PHV vía `anthro.pipeline.run_analysis`.

    Feature 042 (T043): reemplaza a `PHVExplainerUseCase.run()`. Ver el
    docstring del módulo para la compuerta familiar (keyed en rol, no en
    `audience`) y la excepción de presupuesto de latencia (dos llamadas LLM
    secuenciales, p95 ≤ 45 s local).
    """
    _forbid_parents(current_user)
    _ensure_audience_allowed(audience, current_user)

    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )

    await _ensure_ai_consent(athlete.id, db)

    # Historial COMPLETO del atleta (no solo las últimas 4 mediciones,
    # como antes de esta feature) — el pipeline necesita la serie
    # longitudinal completa para su grounding (FR-003); la compactación en
    # checkpoints anuales más allá de 16 puntos (`context_builders.py::
    # HISTORY_MAX_POINTS`) es la válvula de presupuesto de tokens, no un
    # límite de cuántas mediciones puede leer este endpoint.
    result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete.id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    history = list(result.scalars().all())
    if not history:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El atleta no tiene mediciones antropométricas registradas.",
        )
    target_record = history[0]

    resolved_use_case = _use_case_for_audience(audience)
    pipeline_state = {
        "athlete": athlete,
        "target_record": target_record,
        "history_records": history,
        "audience": audience,
        "use_case": resolved_use_case,
        "club_id": athlete.club_id,
        "db": db,
        "actor": current_user,
    }

    try:
        pipeline_result = await run_analysis(pipeline_state)
    except LLMSchemaError as exc:
        # measurement-analysis-api.md §5: "502 — Unchanged mapping; now can
        # also fire from guardrails_step.py" — la defensa final rechazó el
        # texto renderizado; nada se persistió.
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
    # Nota deliberada (contracts/measurement-analysis-api.md §5, "Behaviour
    # change to flag explicitly"): un timeout del analista/crítico YA NO
    # propaga como excepción — `run_analysis()` lo resuelve internamente al
    # camino determinista de fallback (`critic_verdict="fallback"`) y
    # retorna `200`. Este `except` de `LLMTimeoutError`/`LLMUnavailableError`
    # deliberadamente NO existe más en esta ruta.

    cached = await _explanation_row_or_404(db, pipeline_result["persisted_explanation_id"])

    return PHVExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=_aware_utc(cached.generated_at),
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
        **_map_structured_fields(cached, current_user=current_user),
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
    audience: Literal["family", "coach"] = Query(
        "family",
        description=(
            "'family' (default) es el análisis para padres. 'coach' agrega "
            "lo que la versión familiar omite a propósito — solo "
            "coach/admin (feature 042, contracts/measurement-analysis-api.md §0.1)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Devuelve el análisis cacheado para una medición concreta del atleta.

    No verifica `ai_enabled`: análisis previos siguen accesibles aunque el
    LLM esté caído. Padres pueden leer el caché de sus atletas vinculados;
    `audience="coach"` está vedado a padres (`_ensure_audience_allowed`).

    Feature 042 (T043): mismo endpoint, ahora con `?audience=` (antes solo
    lo tenía `phv-explanation`) y con la misma compuerta familiar por rol
    (`_family_gate_blocks`, FR-016) que el endpoint PHV.
    """
    _ensure_audience_allowed(audience, current_user)

    record = await _get_record_or_404(db, athlete.id, record_id)

    result = await db.execute(
        select(AthleteAIExplanation).where(
            AthleteAIExplanation.athlete_id == athlete.id,
            AthleteAIExplanation.anthropometric_record_id == record.id,
            AthleteAIExplanation.use_case == _record_use_case_for_audience(audience),
        )
    )
    cached = result.scalar_one_or_none()
    if cached is None or _family_gate_blocks(cached, current_user=current_user):
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
        **_map_structured_fields(cached, current_user=current_user),
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
    audience: Literal["family", "coach"] = Query(
        "family",
        description=(
            "'family' (default) es el análisis para padres. 'coach' agrega "
            "lo que la versión familiar omite a propósito — solo "
            "coach/admin (feature 042, contracts/measurement-analysis-api.md §0.1)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
) -> AnthropometricRecordExplanationResponse:
    """Genera (o regenera) el análisis por medición vía `anthro.pipeline.run_analysis`.

    Feature 042 (T043): reemplaza a `AnthropometricRecordExplainerUseCase.run()`.
    Ver el docstring del módulo para la compuerta familiar y la excepción de
    presupuesto de latencia (dos llamadas LLM secuenciales, p95 ≤ 45 s local).
    """
    _forbid_parents(current_user)
    _ensure_audience_allowed(audience, current_user)

    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )

    await _ensure_ai_consent(athlete.id, db)

    target = await _get_record_or_404(db, athlete.id, record_id)

    # Todas las mediciones ESTRICTAMENTE anteriores a target — nunca
    # mediciones posteriores, aunque ya existan: analizar una medición
    # pasada no debe apoyarse en datos que todavía no existían en ese
    # momento (mismo criterio que `AnthropometricRecordExplainerUseCase`
    # antes de esta feature). `context.build_context` (paso 1 del
    # pipeline) agrega `target` a esta lista por su cuenta.
    result = await db.execute(
        select(AnthropometricRecord)
        .where(
            AnthropometricRecord.athlete_id == athlete.id,
            AnthropometricRecord.evaluation_date < target.evaluation_date,
        )
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    priors = list(result.scalars().all())

    resolved_use_case = _record_use_case_for_audience(audience)
    pipeline_state = {
        "athlete": athlete,
        "target_record": target,
        "history_records": priors,
        "audience": audience,
        "use_case": resolved_use_case,
        "club_id": athlete.club_id,
        "db": db,
        "actor": current_user,
    }

    try:
        pipeline_result = await run_analysis(pipeline_state)
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
    # Ver la misma nota deliberada en `phv_explanation` — un timeout ya no
    # propaga como excepción, resuelve a `200` con `critic_verdict="fallback"`.

    cached = await _explanation_row_or_404(db, pipeline_result["persisted_explanation_id"])

    # El cache no almacena los campos derivados (deltas) — los recalculamos
    # baratos desde la medición previa, igual que el `GET`.
    delta_h, delta_w, num_prev = await _delta_summary(db, athlete.id, target)

    return AnthropometricRecordExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=_aware_utc(cached.generated_at),
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
        record_id=target.id,
        num_previous_measurements=num_prev,
        delta_height_cm=delta_h,
        delta_weight_kg=delta_w,
        **_map_structured_fields(cached, current_user=current_user),
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
