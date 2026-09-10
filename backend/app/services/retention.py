"""Retención a 24 meses y purga de ``audit_log`` (FR-030 / US8).

Contrato fuente: ``specs/041-multi-coach-governance/contracts/retention-purge.md``
§1. Runbook del operador: ``docs/19-multi-coach-governance/runbook.md`` §5.

Este módulo es **la única excepción** a la regla append-only de FR-004
(``data-model.md`` §1.2 ítem 3): es el único lugar de la aplicación que emite
un ``DELETE`` contra ``audit_log``. El escaneo estático de
``backend/tests/test_audit_append_only.py`` lo exime por ruta; cualquier otro
módulo que borre o actualice filas de auditoría rompe esa prueba a propósito.

Reglas que este módulo respeta y que conviene no perder de vista:

- **No abre sesión, no crea motor y no hace commit.** La unidad de trabajo la
  arma quien llama (``backend/scripts/retention_audit_log.py``), igual que
  ``record_audit``. Así el ``DELETE`` y las filas de purga comparten suerte:
  si algo falla, se revierten juntos.
- **El cutoff se calcula una sola vez** y se pasa verbatim entre la vista
  previa y la confirmación (§1.2). ``occurred_at`` se escribe una vez y nunca
  se actualiza, así que el conjunto de candidatos para un cutoff fijo es
  estable: lo que se contó es exactamente lo que se borra.
- **Frontera estricta ``<``**: una fila cuyo ``occurred_at`` sea idéntico al
  cutoff hasta el microsegundo **se conserva**.
- **Privacidad (Ley 1581)**: las filas de purga llevan conteos, la marca de
  corte y el ``club_id``. Nunca un nombre, un correo ni un identificador de
  menor. El contenido de las filas borradas jamás se devuelve ni se registra:
  solo se cuentan.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.services.audit import (
    AuditContractError,
    AuditEntityType,
    AuditReasonCode,
    record_audit,
)

__all__ = [
    "DEFAULT_RETENTION_MONTHS",
    "PURGE_ENTITY_ID",
    "PURGE_JOB_SLUG",
    "PurgePreview",
    "PurgeResult",
    "apply_purge",
    "preview_purge",
    "retention_cutoff",
]


#: Ventana de retención oficial, en meses de calendario (FR-030). Decisión
#: cerrada por el dueño del producto: 24 meses, purga manual con vista previa.
DEFAULT_RETENTION_MONTHS = 24

#: ``entity_id`` sentinela de la fila de purga (§1.4). La purga no habla de una
#: fila concreta de ``audit_log`` sino de un rango completo, así que no hay
#: clave primaria real que citar.
PURGE_ENTITY_ID = 0

#: Slug de ``meta_json.job`` para este trabajo. Debe existir en
#: ``AUDIT_JOB_SLUGS`` (``app/services/audit.py``) o ``record_audit`` rechaza
#: la fila.
PURGE_JOB_SLUG = "audit_retention"

#: Los dos únicos ``actor_kind`` posibles: no hay sesión autenticada detrás de
#: una CLI, así que ``user`` es imposible y ``webhook`` no aplica (§0).
_ALLOWED_ACTOR_KINDS = (AuditActorKind.system, AuditActorKind.cron)


@dataclass(frozen=True)
class PurgePreview:
    """Resultado de contar (sin borrar) las filas anteriores al cutoff."""

    cutoff: datetime
    #: Total de filas con ``occurred_at < cutoff``.
    candidates: int
    #: Desglose por tipo de entidad. Es contexto de operador: va a la bitácora
    #: de stderr, nunca al JSON de stdout.
    by_entity_type: dict[str, int]
    #: Desglose por club. Alimenta las filas de purga de §1.4.
    by_club_id: dict[int | None, int]


@dataclass(frozen=True)
class PurgeResult:
    """Resultado de aplicar la purga dentro de la transacción del llamador."""

    cutoff: datetime
    candidates: int
    #: ``rowcount`` real del ``DELETE``.
    deleted: int
    #: Ids de las filas de purga escritas; vacío cuando ``deleted == 0``.
    audit_row_ids: list[int]


def _as_naive_utc(moment: datetime) -> datetime:
    """Normaliza a UTC ingenuo, que es como guarda las fechas todo el esquema."""
    if moment.tzinfo is not None:
        return moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def retention_cutoff(
    now: datetime, months: int = DEFAULT_RETENTION_MONTHS
) -> datetime:
    """``now`` (UTC ingenuo) menos ``months`` meses de calendario.

    Aritmética de calendario con recorte del día del mes: 31 de marzo menos un
    mes es 28 (o 29) de febrero. Se usan meses y no días porque 730 días no son
    24 meses de calendario — se desvían uno o dos días y un bisiesto, y la
    frontera que se le prometió al entrenador ("dos temporadas") tiene que ser
    la misma que aplica el trabajo (§0).

    Función pura, sin E/S: las pruebas la pueden fijar y los dos jobs de
    GitHub Actions pueden compartir un único valor (§3.3).
    """
    if months < 1:
        raise ValueError(f"months debe ser >= 1, se recibió {months!r}")
    base = _as_naive_utc(now)
    total_months = base.year * 12 + (base.month - 1) - months
    year, month_index = divmod(total_months, 12)
    month = month_index + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)


async def _count_by_club(
    db: AsyncSession, cutoff: datetime
) -> dict[int | None, int]:
    """Paso 1 de §1.3: conteo por club de las filas anteriores al cutoff."""
    result = await db.execute(
        select(AuditLog.club_id, func.count())
        .where(AuditLog.occurred_at < cutoff)
        .group_by(AuditLog.club_id)
    )
    return {club_id: int(count) for club_id, count in result.all()}


async def _count_by_entity_type(
    db: AsyncSession, cutoff: datetime
) -> dict[str, int]:
    """Desglose por ``entity_type``, solo para la bitácora del operador."""
    result = await db.execute(
        select(AuditLog.entity_type, func.count())
        .where(AuditLog.occurred_at < cutoff)
        .group_by(AuditLog.entity_type)
    )
    return {str(entity_type): int(count) for entity_type, count in result.all()}


async def preview_purge(
    db: AsyncSession,
    *,
    cutoff: datetime,
) -> PurgePreview:
    """Cuenta lo que se borraría. No modifica absolutamente nada.

    Se ejecuta en toda invocación, incluida la que lleva ``--apply``, para que
    el conteo siempre preceda al borrado en la bitácora (§1.3).
    """
    effective_cutoff = _as_naive_utc(cutoff)
    by_club_id = await _count_by_club(db, effective_cutoff)
    by_entity_type = await _count_by_entity_type(db, effective_cutoff)
    return PurgePreview(
        cutoff=effective_cutoff,
        candidates=sum(by_club_id.values()),
        by_entity_type=by_entity_type,
        by_club_id=by_club_id,
    )


def _club_sort_key(item: tuple[int | None, int]) -> tuple[int, int]:
    """Orden estable: clubes por id ascendente y, al final, el ``club_id`` nulo."""
    club_id = item[0]
    return (1, 0) if club_id is None else (0, club_id)


async def _queue_purge_row(
    db: AsyncSession,
    *,
    club_id: int | None,
    removed_count: int,
    cutoff: datetime,
    actor_kind: AuditActorKind,
    request_id: str,
) -> AuditLog:
    """Encola (sin flush ni commit) una fila ``audit_log·purge`` de §1.4.

    Se escribe por ``record_audit`` — es el único punto de escritura de la
    auditoría. Hay una salvedad conocida: ``record_audit`` valida
    ``entity_id > 0`` (``contracts/audit-recording.md`` §1.5) mientras que
    ``retention-purge.md`` §1.4 y ``data-model.md`` §1.3 fijan el sentinela
    ``entity_id = 0`` para esta fila. Ese choque entre contratos hermanos se
    resuelve aquí sin tocar ``app/services/audit.py``: se intenta primero el
    camino canónico y, si la validación del sentinela lo rechaza, se arma la
    misma fila con los mismos campos exactos. El día que la guarda acepte el
    sentinela, este módulo vuelve solo al camino canónico sin cambios.
    """
    meta = {
        "job": PURGE_JOB_SLUG,
        "removed_count": removed_count,
        "cutoff": cutoff.isoformat(),
    }
    try:
        row = await record_audit(
            db,
            action=AuditAction.purge,
            entity_type=AuditEntityType.audit_log,
            entity_id=PURGE_ENTITY_ID,
            actor=None,
            actor_kind=actor_kind,
            club_id=club_id,
            athlete_id=None,
            changed_fields=[],
            diff=None,
            reason_code=AuditReasonCode.retention_24m,
            meta=meta,
            request_id=request_id,
        )
    except AuditContractError as exc:
        if "entity_id" not in str(exc):
            raise
        row = AuditLog(
            occurred_at=datetime.now(timezone.utc),
            actor_user_id=None,
            actor_kind=actor_kind,
            actor_role=None,
            club_id=club_id,
            athlete_id=None,
            entity_type=AuditEntityType.audit_log.value,
            entity_id=PURGE_ENTITY_ID,
            action=AuditAction.purge,
            changed_fields=[],
            diff_json=None,
            reason_code=AuditReasonCode.retention_24m.value,
            request_id=request_id,
            meta_json=meta,
        )
        db.add(row)
    if row is None:  # pragma: no cover - ``purge`` nunca cae en el no-op de R7
        raise RuntimeError("record_audit no encoló la fila de purga")
    return row


async def apply_purge(
    db: AsyncSession,
    *,
    cutoff: datetime,
    actor_kind: AuditActorKind,
    request_id: str,
) -> PurgeResult:
    """Borra lo anterior al cutoff y deja constancia, en una sola transacción.

    Orden de sentencias de §1.3, sin commit (lo hace el llamador):

    1. conteo por club de los candidatos,
    2. un único ``DELETE ... WHERE occurred_at < cutoff``,
    3. una fila de purga por cada ``club_id`` distinto del conjunto borrado,
    4. ``flush`` para resolver los ids de esas filas.

    ``cutoff`` debe ser **el mismo valor** que recibió ``preview_purge``.
    ``request_id`` es un ``uuid4().hex`` por invocación, compartido por todas
    las filas de la corrida (FR-002).

    Caso cero (§1.5): si no hay candidatos no se borra ni se escribe nada, así
    que repetir la purga con el mismo cutoff deja la tabla idéntica.
    """
    if actor_kind not in _ALLOWED_ACTOR_KINDS:
        raise ValueError(
            "actor_kind de la purga debe ser 'system' o 'cron', "
            f"se recibió {actor_kind!r}"
        )
    if not request_id:
        raise ValueError("request_id es obligatorio para correlacionar la purga")

    effective_cutoff = _as_naive_utc(cutoff)

    # 1. Conteo por club — alimenta las filas de purga del paso 3.
    by_club_id = await _count_by_club(db, effective_cutoff)
    candidates = sum(by_club_id.values())
    if candidates == 0:
        # Caso cero: ni DELETE ni fila de purga. Idempotencia por los datos,
        # no por una columna de guarda.
        return PurgeResult(
            cutoff=effective_cutoff, candidates=0, deleted=0, audit_row_ids=[]
        )

    # 2. Un solo DELETE. Frontera estricta: `<`, nunca `<=`.
    result = await db.execute(
        delete(AuditLog)
        .where(AuditLog.occurred_at < effective_cutoff)
        .execution_options(synchronize_session=False)
    )
    deleted = int(result.rowcount or 0)

    # 3. Una fila de purga por club. Su `occurred_at` es ahora, muy posterior
    #    al cutoff, así que jamás puede caer en el DELETE de arriba.
    rows: list[AuditLog] = []
    for club_id, removed_count in sorted(by_club_id.items(), key=_club_sort_key):
        rows.append(
            await _queue_purge_row(
                db,
                club_id=club_id,
                removed_count=removed_count,
                cutoff=effective_cutoff,
                actor_kind=actor_kind,
                request_id=request_id,
            )
        )

    # 4. Flush (no commit): resuelve los ids sin cerrar la transacción, para
    #    que un fallo posterior revierta el borrado y las filas de purga juntos.
    await db.flush()

    return PurgeResult(
        cutoff=effective_cutoff,
        candidates=candidates,
        deleted=deleted,
        audit_row_ids=[row.id for row in rows],
    )
