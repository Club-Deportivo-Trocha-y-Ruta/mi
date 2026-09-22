"""Carga histórica Copa Valle — stagea (nunca commitea) las válidas de un
manifiesto (feature 044, US5, T063 — contracts/historical-load.md §"Script").

Uso:
    cd backend
    python -m scripts.stage_race_history --manifest /ruta/fuera/del/repo/manifest.json --user-id 10 [--dry]

El manifiesto y los archivos referenciados viven **fuera del repositorio** —
el script se niega a leer una ruta que resuelva dentro de él (nunca se
versiona un PDF con nombres de menores, ver CLAUDE.md). Formato JSON, lista
de entradas:

    [
      {
        "season": 2024, "valida_num": 3, "event_date": "2024-06-14",
        "location": "Palmira", "event_name": "VALIDA III PALMIRA",
        "file": "/Users/coach/copa-valle-historico/2024/valida_3.pdf"
      },
      ...
    ]

Campos opcionales por entrada: ``series_name`` (default "Copa Valle de
Ciclomontañismo"), ``series_kind`` ("cup"/"championship", default "cup"),
``series_level`` ("departmental"/"national", default "departmental").

Cada entrada se stagea llamando a
``app.services.race.import_staging.stage_results_file`` — el mismo cuerpo
que usa ``POST /race-imports/parse`` (contracts/historical-load.md
§"Staging service") — así que el board de la UI y la revisión de
completitud/identidad ven estas válidas exactamente igual que si el coach
las hubiera subido a mano. El script **nunca commitea**: revisión y commit
pasan por la UI, donde la bitácora de auditoría queda a nombre de la
persona que decide (research R-12).

FR-024: un ``general_file`` en una entrada, o un ``file`` cuyo nombre
sugiere el acumulado de temporada de la Liga ("general"/"acumulad"), se
rechaza — el script solo acepta el archivo de resultados por válida.

FR-027: un archivo ya en staging (mismo sha256, aún ``pending``) se reporta
como "ya en staging" y no crea nada nuevo; uno ya ``committed`` se reporta
como tal — ninguno de los dos cuenta como fallo (permite reintentar tras
una interrupción a mitad del lote sin duplicar nada, ver T063).

Salida: solo ids, conteos y códigos de advertencia — nunca un nombre.
Código de salida ≠ 0 si alguna entrada falló al stagear.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from app.services.race.import_staging import stage_results_file
from app.services.request_context import AuditContext

#: Raíz del monorepo (backend/scripts/../.. = raíz del repo) — ningún
#: manifiesto ni archivo referenciado puede resolver dentro de este árbol.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Extensiones de RESULTADOS aceptadas — igual que el wizard (router).
_ALLOWED_EXTS = {"pdf", "csv", "tsv", "txt"}
_PDF_MAGIC = b"%PDF-"

#: Heurística FR-024: nombre de archivo que sugiere el acumulado de
#: temporada de la Liga (GENERAL), nunca el acta de una sola válida.
_GENERAL_FILENAME_HINTS = ("general", "acumulad")


class ManifestError(ValueError):
    """Manifiesto o ruta de archivo inválida — nunca se llega a stagear nada."""


@dataclass
class StageOutcome:
    """Resultado de una entrada — solo ids/conteos, nunca nombres."""

    index: int
    season: int
    valida_num: int
    ok: bool
    code: str  # "staged" | "already_staged" | "already_committed" | "rejected" | "error"
    parse_id: Optional[int] = None
    n_rows: Optional[int] = None
    warnings: list[str] = None  # type: ignore[assignment]
    detail: Optional[str] = None


def _assert_outside_repo(path: Path, *, what: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return resolved
    raise ManifestError(
        f"{what} resuelve DENTRO del repositorio ({resolved}); debe vivir "
        f"fuera de él (CLAUDE.md: cero PDFs oficiales versionados)."
    )


def _load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    _assert_outside_repo(manifest_path, what="El manifiesto")
    if not manifest_path.exists():
        raise ManifestError(f"Manifiesto no encontrado: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifiesto no es JSON válido: {exc}") from exc
    if not isinstance(data, list):
        raise ManifestError("El manifiesto debe ser una lista de entradas.")
    return data


def _validate_entry(entry: dict[str, Any], index: int) -> None:
    required = ("season", "valida_num", "event_date", "location", "event_name", "file")
    missing = [f for f in required if f not in entry]
    if missing:
        raise ManifestError(f"Entrada #{index}: faltan campos {missing}.")
    if "general_file" in entry:
        raise ManifestError(
            f"Entrada #{index}: 'general_file' no es soportado — el script "
            "solo stagea el archivo de resultados por válida (FR-024)."
        )


def _is_general_like_filename(file_path: Path) -> bool:
    name = file_path.name.lower()
    return any(hint in name for hint in _GENERAL_FILENAME_HINTS)


def _results_ext(file_path: Path) -> str:
    ext = file_path.suffix.lstrip(".").lower()
    if ext not in _ALLOWED_EXTS:
        raise ManifestError(
            f"Extensión no soportada: '{file_path.suffix}' "
            f"(permitidas: {sorted(_ALLOWED_EXTS)})."
        )
    return "csv" if ext in ("csv", "tsv", "txt") else "pdf"


async def _load_actor(db, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ManifestError(f"--user-id={user_id} no corresponde a ningún usuario.")
    if user.role not in (UserRole.admin, UserRole.coach):
        raise ManifestError(
            f"--user-id={user_id} tiene rol '{user.role.value}' — se requiere "
            "coach o admin."
        )
    return user


async def _stage_entry(
    index: int, entry: dict[str, Any], *, actor: User, dry: bool
) -> StageOutcome:
    season = int(entry["season"])
    valida_num = int(entry["valida_num"])
    file_path = _assert_outside_repo(Path(entry["file"]), what=f"Entrada #{index}: 'file'")

    if _is_general_like_filename(file_path):
        return StageOutcome(
            index=index, season=season, valida_num=valida_num, ok=False,
            code="rejected",
            detail="nombre de archivo sugiere acumulado GENERAL (FR-024)",
        )

    results_ext = _results_ext(file_path)
    if not file_path.exists():
        return StageOutcome(
            index=index, season=season, valida_num=valida_num, ok=False,
            code="error", detail=f"archivo no encontrado: {file_path}",
        )
    file_bytes = file_path.read_bytes()
    if results_ext == "pdf" and file_bytes[:5] != _PDF_MAGIC:
        return StageOutcome(
            index=index, season=season, valida_num=valida_num, ok=False,
            code="error", detail="magic bytes '%PDF-' ausentes",
        )

    if dry:
        return StageOutcome(
            index=index, season=season, valida_num=valida_num, ok=True,
            code="dry_run_skipped",
        )

    series_kind = RaceSeriesKind(entry.get("series_kind", "cup"))
    series_level = RaceSeriesLevel(entry.get("series_level", "departmental"))
    series_name = entry.get("series_name", "Copa Valle de Ciclomontañismo")

    async with AsyncSessionLocal() as db:
        actor_row = await _load_actor(db, actor.id)
        # Detectar "ya committed" ANTES de llamar al servicio: stage_results_file
        # lanza HTTPException 409 en ese caso — la traducimos a un resultado
        # informativo, no a un fallo (FR-027, "already-staged files are
        # reported as such and skipped").
        try:
            response = await stage_results_file(
                db,
                file_bytes=file_bytes,
                original_filename=file_path.name,
                results_ext=results_ext,
                series_name=series_name,
                season=season,
                valida_num=valida_num,
                event_name=str(entry["event_name"]),
                event_date=date.fromisoformat(str(entry["event_date"])),
                location=str(entry["location"]),
                series_kind=series_kind,
                series_level=series_level,
                actor=actor_row,
                ctx=AuditContext.for_user(actor_row),
            )
            await db.commit()
        except HTTPException as exc:
            await db.rollback()
            if exc.status_code == 409:
                already_committed = "commiteado" in str(exc.detail)
                return StageOutcome(
                    index=index, season=season, valida_num=valida_num, ok=True,
                    code="already_committed" if already_committed else "already_staged",
                    detail=str(exc.detail),
                )
            return StageOutcome(
                index=index, season=season, valida_num=valida_num, ok=False,
                code="error", detail=str(exc.detail),
            )

    warnings = [w.code for w in response.warnings]
    return StageOutcome(
        index=index, season=season, valida_num=valida_num, ok=True,
        code="staged", parse_id=response.parse_id,
        n_rows=response.n_rows_resultados, warnings=warnings,
    )


async def _run(manifest_path: Path, *, user_id: int, dry: bool) -> int:
    entries = _load_manifest(manifest_path)
    for i, entry in enumerate(entries, start=1):
        _validate_entry(entry, i)

    async with AsyncSessionLocal() as db:
        actor = await _load_actor(db, user_id)

    outcomes: list[StageOutcome] = []
    for i, entry in enumerate(entries, start=1):
        outcome = await _stage_entry(i, entry, actor=actor, dry=dry)
        outcomes.append(outcome)
        status_word = outcome.code
        extra = f" parse_id={outcome.parse_id}" if outcome.parse_id else ""
        extra += f" rows={outcome.n_rows}" if outcome.n_rows is not None else ""
        if outcome.warnings:
            extra += f" warnings={outcome.warnings}"
        if outcome.detail and not outcome.ok:
            extra += f" detail={outcome.detail!r}"
        print(
            f"[{outcome.index}/{len(entries)}] season={outcome.season} "
            f"valida={outcome.valida_num} -> {status_word}{extra}"
        )

    n_staged = sum(1 for o in outcomes if o.code == "staged")
    n_already = sum(1 for o in outcomes if o.code in ("already_staged", "already_committed"))
    n_rejected = sum(1 for o in outcomes if o.code == "rejected")
    n_errors = sum(1 for o in outcomes if o.code == "error")
    n_dry = sum(1 for o in outcomes if o.code == "dry_run_skipped")
    print(
        f"Resumen: staged={n_staged} already_staged_or_committed={n_already} "
        f"rejected={n_rejected} errors={n_errors} dry_run_skipped={n_dry}"
    )
    return 1 if (n_errors or n_rejected) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", required=True, type=Path,
        help="Ruta al manifiesto JSON (fuera del repositorio).",
    )
    parser.add_argument(
        "--user-id", required=True, type=int,
        help="Id del coach/admin a quien se atribuye la carga (auditoría).",
    )
    parser.add_argument(
        "--dry", action="store_true",
        help="Valida el manifiesto y los archivos, no stagea nada.",
    )
    args = parser.parse_args()

    try:
        exit_code = asyncio.run(
            _run(args.manifest, user_id=args.user_id, dry=args.dry)
        )
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
