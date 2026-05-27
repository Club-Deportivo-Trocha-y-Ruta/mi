"""Otorga consentimiento Ley 1581 (third_party_sharing=True) para atletas.

Uso operativo destinado a desbloquear pruebas de features con IA (boletines,
explicaciones PHV) en entornos donde el flujo de aceptación de padres aún no
está operativo. NO usar para evadir consentimientos reales: cada padre real
debe seguir firmando vía /api/privacy/consents.

Modos de uso (correr desde backend/):

    # Otorgar a un atleta puntual usando un padre vinculado existente
    python -m scripts.grant_ai_consent --athlete-id 12 --parent-id 5

    # Otorgar a todos los atletas que tengan al menos un padre vinculado,
    # firmando con el primer padre vinculado de cada uno
    python -m scripts.grant_ai_consent --all

    # Lista explícita
    python -m scripts.grant_ai_consent --athlete-id 12 --athlete-id 14 --athlete-id 23

    # Sólo simular (no commitea)
    python -m scripts.grant_ai_consent --all --dry-run

Reglas:
- Idempotente: si el consentimiento vigente ya tiene third_party_sharing=True,
  no inserta nada.
- Append-only: si hay consentimiento vigente con third_party_sharing=False,
  lo marca como supersedido (withdrawn_at=now, reason='superseded by ops grant')
  y crea uno nuevo con los tres flags en True.
- Usa la política de privacidad activa (más reciente, no deprecada).
- Requiere que exista al menos un ParentAthlete para el atleta; si no, falla.

Trazabilidad:
- consent_method = 'ops_script_grant'
- ip_address = '127.0.0.1'
- user_agent = 'grant_ai_consent.py'
- Imprime un resumen por atleta: granted | already_ok | skipped | failed.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import (
    Athlete,
    ParentalConsent,
    ParentAthlete,
    PrivacyPolicy,
)


GRANT_METHOD = "ops_script_grant"
GRANT_REASON = "superseded by ops grant (ai consent unlock)"
GRANT_IP = "127.0.0.1"
GRANT_UA = "grant_ai_consent.py"


async def _active_policy(db: AsyncSession) -> PrivacyPolicy:
    stmt = (
        select(PrivacyPolicy)
        .where(PrivacyPolicy.deprecated_at.is_(None))
        .order_by(PrivacyPolicy.effective_date.desc())
        .limit(1)
    )
    policy = (await db.execute(stmt)).scalar_one_or_none()
    if policy is None:
        raise RuntimeError("No hay política de privacidad activa. Corre seed o crea una versión.")
    return policy


async def _pick_parent(db: AsyncSession, athlete_id: int, parent_id: int | None) -> int | None:
    """Resuelve el parent_user_id a usar para el INSERT."""
    if parent_id is not None:
        stmt = select(ParentAthlete).where(
            ParentAthlete.parent_id == parent_id,
            ParentAthlete.athlete_id == athlete_id,
        )
        link = (await db.execute(stmt)).scalar_one_or_none()
        return parent_id if link else None

    stmt = (
        select(ParentAthlete.parent_id)
        .where(ParentAthlete.athlete_id == athlete_id)
        .order_by(ParentAthlete.parent_id)
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    return row[0] if row else None


async def _current_consent(db: AsyncSession, parent_id: int, athlete_id: int) -> ParentalConsent | None:
    stmt = (
        select(ParentalConsent)
        .where(
            ParentalConsent.parent_user_id == parent_id,
            ParentalConsent.athlete_id == athlete_id,
            ParentalConsent.withdrawn_at.is_(None),
        )
        .order_by(ParentalConsent.consented_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _grant_for_athlete(
    db: AsyncSession,
    athlete_id: int,
    parent_id: int | None,
    policy: PrivacyPolicy,
    dry_run: bool,
) -> tuple[str, str]:
    """Devuelve (status, mensaje). status ∈ {granted, already_ok, skipped, failed}."""
    athlete = await db.get(Athlete, athlete_id)
    if athlete is None:
        return "failed", f"atleta {athlete_id} no existe"

    resolved_parent = await _pick_parent(db, athlete_id, parent_id)
    if resolved_parent is None:
        return "failed", (
            f"atleta {athlete_id} sin ParentAthlete vinculado"
            if parent_id is None
            else f"padre {parent_id} no está vinculado al atleta {athlete_id}"
        )

    existing = await _current_consent(db, resolved_parent, athlete_id)
    if existing is not None and existing.third_party_sharing:
        return "already_ok", f"atleta {athlete_id} ya tiene consent IA vigente (padre {resolved_parent})"

    if dry_run:
        action = "renew" if existing else "create"
        return "granted", f"[dry-run] {action} para atleta {athlete_id} con padre {resolved_parent}"

    now = datetime.now(timezone.utc)

    if existing is not None:
        existing.withdrawn_at = now
        existing.withdrawal_reason = GRANT_REASON
        await db.flush()

    new_consent = ParentalConsent(
        parent_user_id=resolved_parent,
        athlete_id=athlete_id,
        consent_version=policy.version,
        policy_id=policy.id,
        consented_at=now,
        consent_method=GRANT_METHOD,
        ip_address=GRANT_IP,
        user_agent=GRANT_UA,
        data_collection=True,
        training_tracking=False,
        anthropometry=True,
        third_party_sharing=True,
    )
    db.add(new_consent)
    await db.flush()
    return "granted", f"consent IA otorgado a atleta {athlete_id} (padre {resolved_parent})"


async def _collect_targets(db: AsyncSession, ids: list[int], all_flag: bool) -> list[int]:
    if all_flag:
        stmt = select(Athlete.id).order_by(Athlete.id)
        return [row[0] for row in (await db.execute(stmt)).all()]
    return ids


async def run(
    athlete_ids: list[int],
    parent_id: int | None,
    all_flag: bool,
    dry_run: bool,
) -> int:
    async with AsyncSessionLocal() as db:
        try:
            policy = await _active_policy(db)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        targets = await _collect_targets(db, athlete_ids, all_flag)
        if not targets:
            print("ERROR: ningún atleta seleccionado. Usa --athlete-id o --all.", file=sys.stderr)
            return 2

        print(f"Política activa: {policy.version} (id={policy.id})")
        print(f"Atletas objetivo: {len(targets)} — dry_run={dry_run}")
        print("-" * 60)

        counters = {"granted": 0, "already_ok": 0, "skipped": 0, "failed": 0}

        for athlete_id in targets:
            status, msg = await _grant_for_athlete(db, athlete_id, parent_id, policy, dry_run)
            counters[status] = counters.get(status, 0) + 1
            print(f"[{status:>10}] {msg}")

        if dry_run:
            await db.rollback()
            print("-" * 60)
            print("DRY-RUN: ningún cambio commiteado.")
        else:
            await db.commit()
            print("-" * 60)
            print("COMMIT OK.")

        print(
            "Resumen: granted={granted} already_ok={already_ok} "
            "skipped={skipped} failed={failed}".format(**counters)
        )
        return 1 if counters["failed"] else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Otorga third_party_sharing=True a atletas para desbloquear features IA.")
    parser.add_argument(
        "--athlete-id",
        type=int,
        action="append",
        default=[],
        help="ID de atleta. Puede repetirse. Mutuamente excluyente con --all.",
    )
    parser.add_argument(
        "--parent-id",
        type=int,
        default=None,
        help="ID del padre que firma. Si se omite, usa el primer ParentAthlete del atleta.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Aplica a todos los atletas con padre vinculado.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula sin commitear.",
    )
    args = parser.parse_args()

    if args.all and args.athlete_id:
        parser.error("--all y --athlete-id son mutuamente excluyentes")
    if not args.all and not args.athlete_id:
        parser.error("debes pasar --athlete-id <id> (repetible) o --all")
    return args


def main() -> None:
    args = _parse_args()
    code = asyncio.run(
        run(
            athlete_ids=args.athlete_id,
            parent_id=args.parent_id,
            all_flag=args.all,
            dry_run=args.dry_run,
        )
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
