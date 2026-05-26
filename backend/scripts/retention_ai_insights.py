"""Job de retencion 180d para ``athlete_ai_insights``.

Politica
========
Filas con ``deprecated_at < NOW() - INTERVAL N DAY`` (N=180 por default)
y ``pii_scrubbed_at IS NULL`` se actualizan:

- ``summary_text = '[scrubbed retention 180d]'``
- ``pii_scrubbed_at = NOW()``

Las filas **no se borran**: se mantiene el registro de versionado para
auditoria (que se publico cuando), pero el contenido textual queda
ofuscado. Idempotente: filas ya scrubeadas se filtran por
``pii_scrubbed_at IS NULL``, asi correr el script dos veces no
doble-redacta.

Logs estructurados
==================
Imprime conteo de filas afectadas por ``athlete_id`` para que el coach
pueda detectar concentraciones inesperadas (ej: un atleta con muchas
filas deprecated indica que su pipeline genera demasiadas versiones).

Uso
===

    cd backend
    source .venv/bin/activate

    # Dry-run (default, seguro): solo imprime, NO toca DB.
    python -m scripts.retention_ai_insights

    # Aplicar: corre el UPDATE.
    python -m scripts.retention_ai_insights --apply

    # Override threshold (debugging interno).
    python -m scripts.retention_ai_insights --days 90 --apply

Salida (exit codes)
===================
- ``0`` — OK (dry-run o apply exitoso).
- ``1`` — error de conexion DB o validacion.

Documentado en: ``docs/10-race-results/runbook-v2.md`` seccion 3.
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import typer
from sqlalchemy import func, select, update

app = typer.Typer(add_completion=False, help=__doc__)


SCRUBBED_SENTINEL = "[scrubbed retention 180d]"
DEFAULT_RETENTION_DAYS = 180


def _emit(label: str, msg: str) -> None:
    """Output con prefijo timestamp para que sea grep-friendly desde cron."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    typer.echo(f"[{ts}] {label:7} {msg}")


async def _run(days: int, apply: bool) -> int:
    """Ejecuta la logica de retencion. Devuelve numero de filas afectadas.

    Imports diferidos para que ``--help`` funcione sin cargar SQLAlchemy /
    settings (util cuando se invoca por error sin venv activo).
    """
    from app.database import AsyncSessionLocal
    from app.models.athlete_ai_insight import AthleteAiInsight

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    _emit("INFO", f"threshold = {days}d (cutoff = {cutoff.isoformat()})")
    _emit("INFO", f"mode      = {'APPLY' if apply else 'DRY-RUN'}")

    async with AsyncSessionLocal() as session:
        # Seleccion de candidatos (siempre — necesario para el report).
        stmt = (
            select(
                AthleteAiInsight.id,
                AthleteAiInsight.athlete_id,
                AthleteAiInsight.deprecated_at,
            )
            .where(AthleteAiInsight.deprecated_at.is_not(None))
            .where(AthleteAiInsight.deprecated_at < cutoff)
            .where(AthleteAiInsight.pii_scrubbed_at.is_(None))
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            _emit("OK", "0 filas elegibles para scrub. Nada que hacer.")
            return 0

        # Log estructurado: conteo por athlete (detector de anomalias).
        per_athlete = Counter(r.athlete_id for r in rows)
        _emit("INFO", f"total filas elegibles: {len(rows)}")
        for athlete_id, count in sorted(per_athlete.items()):
            _emit("ROW", f"athlete_id={athlete_id} elegibles={count}")

        if not apply:
            _emit("DRY", "no se ejecuta UPDATE. Usar --apply para aplicar.")
            return len(rows)

        # APPLY: UPDATE masivo. Idempotente por filtro pii_scrubbed_at IS NULL.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        upd = (
            update(AthleteAiInsight)
            .where(AthleteAiInsight.deprecated_at.is_not(None))
            .where(AthleteAiInsight.deprecated_at < cutoff)
            .where(AthleteAiInsight.pii_scrubbed_at.is_(None))
            .values(
                summary_text=SCRUBBED_SENTINEL,
                pii_scrubbed_at=now,
                updated_at=now,
            )
        )
        await session.execute(upd)
        await session.commit()
        _emit("DONE", f"{len(rows)} filas actualizadas (summary_text + pii_scrubbed_at)")
        return len(rows)


@app.command()
def main(
    days: int = typer.Option(
        DEFAULT_RETENTION_DAYS,
        "--days",
        help=(
            "Threshold en dias post deprecated_at. Default 180 (politica oficial). "
            "Bajarlo solo para debugging."
        ),
        min=1,
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Ejecutar UPDATE. Sin esta flag corre en dry-run (default seguro).",
    ),
) -> None:
    """Punto de entrada CLI."""
    try:
        affected = asyncio.run(_run(days=days, apply=apply))
    except KeyboardInterrupt:
        _emit("ABORT", "interrumpido por usuario")
        raise typer.Exit(code=1)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo aborta con exit 1
        _emit("ERROR", f"{type(exc).__name__}: {exc}")
        raise typer.Exit(code=1)

    _emit("EXIT", f"affected_rows={affected} apply={apply}")
    sys.exit(0)


if __name__ == "__main__":
    app()
