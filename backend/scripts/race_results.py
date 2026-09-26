"""CLI de resultados (amendment 2026-09-26, US5 — ``contracts/results-skill-cli.md``).

    python -m scripts.race_results <mask|profile-check|apply|compare|stage> [opciones]

El mismo código corre contra la base local y contra producción — solo
cambia el destino (``app.services.race.results_skill.target.resolve_target``,
la única frontera entre este script y la base de producción). Local es el
default, sin fricción; producción exige ``--target production --confirm
produccion`` más un stack completo (SFTP configurado, cabeza de Alembic
igual a la del repositorio).

Disciplina de stdout/stderr (FR-045, FR-049): ninguna línea de este
script, en ningún subcomando, imprime jamás un nombre, ciudad, club,
dorsal, tiempo o puntaje — solo rutas, ids, conteos, códigos, ordinales,
números de página y etiquetas estructurales. Una excepción se reporta como
``NombreDeClase: código``, nunca con su mensaje crudo (que podría llevar,
por ejemplo, un valor de fila reflejado por una librería de terceros).

Import tardío (crítico, ver ``results_skill/target.py``): ningún módulo
``app.*`` se importa a nivel de módulo aquí — cada subcomando importa lo
que necesita dentro de su función, después de que ``resolve_target`` haya
tenido la oportunidad de cargar ``backend/.env.production`` en el entorno
del proceso. ``mask``/``profile-check``/``apply`` no llaman a
``resolve_target`` en absoluto: no tocan una base de datos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date as date_type, datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Raíz del repositorio / guardas de ruta (portadas de scripts/stage_race_history.py)
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    for candidate in (backend_dir, *backend_dir.parents):
        if (candidate / ".git").exists():
            return candidate
    return backend_dir


_REPO_ROOT = _find_repo_root()


class CliError(Exception):
    """Rechazo con código de salida explícito — el mensaje ya va scrubbed
    cuando corresponde (el caller de ``main`` decide)."""

    def __init__(self, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _assert_outside_repo(path: Path, *, what: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        return resolved
    raise CliError(
        f"{what} resuelve DENTRO del repositorio; debe vivir fuera de él "
        "(CLAUDE.md: cero PDFs oficiales versionados).",
        exit_code=2,
    )


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
_PDF_MAGIC = b"%PDF-"
_ALLOWED_RESULTS_SUFFIXES = {"pdf": "pdf", "csv": "csv", "tsv": "csv", "txt": "csv"}
_DOCUMENT_SCHEMA_VERSION = 1
ENGINE_VERSION = "results_skill/1"

#: Guarda de revisión (contracts/results-skill-cli.md, T147): mientras la
#: fase 18 (commit de revisiones, T173-T176) no esté servida, una lectura
#: distinta de una válida ya commiteada NO se stagea — el commit de esa
#: revisión hoy solo agregaría filas, nunca actualizaría ni borraría
#: (revision-via-skill.md, "Current state"). T175 pone esto en ``False``.
REVISION_STAGING_AVAILABLE = False

_RUN_META_FILENAME = "run.json"


# ---------------------------------------------------------------------------
# Helpers de run folder
# ---------------------------------------------------------------------------


def _output_root() -> Path:
    """``output/race-results/`` a nivel de repositorio (quickstart.md §9.4:
    desde ``backend/`` se referencia como ``../output/race-results/<run>``).
    ``output/`` está en ``.gitignore``."""
    return _REPO_ROOT / "output" / "race-results"


def _new_run_dir(file_bytes: bytes) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sha8 = hashlib.sha256(file_bytes).hexdigest()[:8]
    run_dir = _output_root() / f"{stamp}-{sha8}"
    (run_dir / "masked").mkdir(parents=True, exist_ok=True)
    (run_dir / "private").mkdir(parents=True, exist_ok=True)
    return run_dir


def _results_ext_from_path(path: Path) -> str:
    suffix = path.suffix.lstrip(".").lower()
    ext = _ALLOWED_RESULTS_SUFFIXES.get(suffix)
    if ext is None:
        raise CliError(
            f"Extensión no soportada: '{path.suffix}' (permitidas: pdf, csv, tsv, txt).",
            exit_code=2,
        )
    return ext


def _write_report(run_dir: Path, payload: dict[str, Any]) -> None:
    (run_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_source_meta(run_dir: Path) -> dict[str, Any]:
    source_path = run_dir / "private" / "source.json"
    if not source_path.exists():
        raise CliError(
            f"No existe {source_path.name} en el run — corra 'mask' primero.",
            exit_code=2,
        )
    return json.loads(source_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# mask
# ---------------------------------------------------------------------------


def cmd_mask(args: argparse.Namespace) -> int:
    from app.services.race.results_skill.masking import (
        ScannedPdfError,
        UnsupportedFileError,
        build_masked_view,
        render_masked_view,
    )

    file_path = _assert_outside_repo(Path(args.file), what="--file")
    if not file_path.exists():
        raise CliError(f"Archivo no encontrado: {file_path}", exit_code=2)

    results_ext = _results_ext_from_path(file_path)
    file_bytes = file_path.read_bytes()

    if results_ext == "pdf" and file_bytes[:5] != _PDF_MAGIC:
        raise CliError("El archivo no tiene el magic bytes '%PDF-' esperado.", exit_code=2)

    try:
        view = build_masked_view(file_bytes, results_ext)
    except ScannedPdfError:
        raise CliError("El PDF no tiene capa de texto (escaneado).", exit_code=4)
    except UnsupportedFileError as exc:
        raise CliError(str(exc), exit_code=2)

    run_dir = _new_run_dir(file_bytes)
    rendered = render_masked_view(view)
    (run_dir / "masked" / "view.txt").write_text(rendered, encoding="utf-8")

    n_pages = len(view.pages)
    n_lines_structural = sum(1 for p in view.pages for line in p.lines if line.kind == "S")
    n_lines_content = sum(1 for p in view.pages for line in p.lines if line.kind == "C")
    summary = {
        "format": view.format,
        "sha256_prefix": view.sha256,
        "pages": n_pages,
        "lines_structural": n_lines_structural,
        "lines_content": n_lines_content,
    }
    (run_dir / "masked" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    source_meta = {
        "path": str(file_path),
        "sha256": hashlib.sha256(file_bytes).hexdigest(),
        "results_ext": results_ext,
    }
    (run_dir / "private" / "source.json").write_text(
        json.dumps(source_meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"run: {run_dir}")
    print(f"format: {view.format}")
    if view.format == "pdf":
        print(f"pages: {n_pages}")
    else:
        print(f"rows: {len(view.pages[0].lines) if view.pages else 0}")
    print(f"lines_structural: {n_lines_structural}")
    print(f"lines_content: {n_lines_content}")

    _write_report(
        run_dir,
        {"subcommand": "mask", "exit_code": 0, "run_dir": str(run_dir), **summary},
    )
    return 0


# ---------------------------------------------------------------------------
# profile-check
# ---------------------------------------------------------------------------


def cmd_profile_check(args: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from app.services.race.results_skill.profile import load_profile

    try:
        load_profile(args.profile)
    except ValidationError as exc:
        print("violaciones:")
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"])
            print(f"  {loc}: {error['type']}")
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"{type(exc).__name__}: perfil inválido", file=sys.stderr)
        return 2

    print("ok")
    return 0


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def _document_report_lines(document) -> list[str]:
    from app.services.race.completeness import check_category

    lines: list[str] = []
    for index, category in enumerate(document.categories, start=1):
        report = check_category(category)
        n_rows = len(category.rows)
        status_counts: dict[str, int] = {}
        for row in category.rows:
            raw = (row.time_raw or "").strip().upper()
            if raw in ("DNF", "DSQ", "DNS"):
                key = raw.lower()
            elif raw == "":
                key = "sin_tiempo"
            else:
                key = "finished"
            status_counts[key] = status_counts.get(key, 0) + 1

        label = category.header_raw if category.code is None else f"<estructural #{index}>"
        code = category.code or "—"
        if report.status == "ok":
            completeness_txt = "ok"
        elif report.status == "acknowledged":
            completeness_txt = "acknowledged"
        else:
            parts = []
            if report.missing:
                parts.append(f"faltan {report.missing}")
            if report.duplicated:
                parts.append(f"repetidas {report.duplicated}")
            completeness_txt = "; ".join(parts) or "inconsistent"
        status_txt = " ".join(f"{k}={v}" for k, v in sorted(status_counts.items()))
        lines.append(
            f"[{index}] {label} code={code} rows={n_rows} completeness={completeness_txt} {status_txt}".rstrip()
        )
    return lines


def cmd_apply(args: argparse.Namespace) -> int:
    from app.services.race.results_skill.apply import apply_profile
    from app.services.race.results_skill.masking import leak_count
    from app.services.race.results_skill.profile import load_profile, profile_sha256
    from app.services.race.staged_document import document_to_json

    run_dir = Path(args.run)
    source_meta = _load_source_meta(run_dir)
    file_path = Path(source_meta["path"])
    if not file_path.exists():
        raise CliError(f"Archivo original ya no existe: {file_path}", exit_code=6)
    file_bytes = file_path.read_bytes()
    current_sha256 = hashlib.sha256(file_bytes).hexdigest()
    if current_sha256 != source_meta["sha256"]:
        raise CliError(
            "El archivo cambió desde 'mask' (sha256 no coincide).", exit_code=6
        )
    results_ext = source_meta["results_ext"]

    try:
        profile = load_profile(args.profile)
    except (FileNotFoundError, ValueError) as exc:
        raise CliError(f"{type(exc).__name__}: perfil inválido", exit_code=2)

    document = apply_profile(file_bytes, results_ext, profile)

    rendered_view = (run_dir / "masked" / "view.txt").read_text(encoding="utf-8")
    leaks = leak_count(rendered_view, document)

    profile_path = Path(args.profile)
    if not profile_path.suffix:
        from app.services.race.results_skill.profile import PROFILES_DIR

        profile_path = PROFILES_DIR / f"{profile.profile_id}.json"
    sha = profile_sha256(profile_path)

    document_payload = {
        "schema_version": _DOCUMENT_SCHEMA_VERSION,
        "profile": {
            "profile_id": profile.profile_id,
            "profile_sha256": sha,
            "engine_version": ENGINE_VERSION,
        },
        "document": document_to_json(document),
    }
    (run_dir / "private" / "document.json").write_text(
        json.dumps(document_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    n_categories = len(document.categories)
    n_rows = sum(len(c.rows) for c in document.categories)

    for line in _document_report_lines(document):
        print(line)
    for row in document.unreadable_rows:
        print(f"ilegible: (page={row.page}, ordinal={row.ordinal})")
    print(f"total_categorias: {n_categories}")
    print(f"total_filas: {n_rows}")
    print(f"fuga: {leaks}")

    report = {
        "subcommand": "apply",
        "categories": n_categories,
        "rows": n_rows,
        "unreadable_rows": len(document.unreadable_rows),
        "leak_count": leaks,
    }

    if leaks > 0:
        report["exit_code"] = 3
        _write_report(run_dir, report)
        return 3
    if n_rows == 0:
        report["exit_code"] = 5
        _write_report(run_dir, report)
        return 5

    report["exit_code"] = 0
    _write_report(run_dir, report)
    return 0


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------

_EXPLICIT_MANIFEST_KEYS = frozenset(
    {
        "series_name",
        "series_kind",
        "series_level",
        "season",
        "valida_num",
        "event_name",
        "event_date",
        "location",
    }
)
_EVENT_MANIFEST_KEYS = frozenset({"race_event_id"})


def _load_manifest_dict(manifest_path: Path) -> dict[str, Any]:
    _assert_outside_repo(manifest_path, what="--manifest")
    if not manifest_path.exists():
        raise CliError(f"Manifiesto no encontrado: {manifest_path}", exit_code=2)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"Manifiesto no es JSON válido: {exc}", exit_code=2)
    if not isinstance(data, dict):
        raise CliError("El manifiesto debe ser un objeto JSON.", exit_code=2)
    return data


async def _resolve_header(db, manifest: dict[str, Any]):
    from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
    from app.services.race.import_staging import StageHeader

    keys = set(manifest)
    if "race_event_id" in keys:
        if keys - _EVENT_MANIFEST_KEYS:
            raise CliError(
                f"Manifiesto con 'race_event_id' no admite otras claves: {sorted(keys - _EVENT_MANIFEST_KEYS)}",
                exit_code=2,
            )
        from sqlalchemy import select

        from app.models.race_event import RaceEvent
        from app.models.race_series import RaceSeries

        event = (
            await db.execute(select(RaceEvent).where(RaceEvent.id == manifest["race_event_id"]))
        ).scalar_one_or_none()
        if event is None:
            raise CliError(
                f"race_event_id={manifest['race_event_id']} no existe en el destino.",
                exit_code=2,
            )
        series = (
            await db.execute(select(RaceSeries).where(RaceSeries.id == event.series_id))
        ).scalar_one()
        return StageHeader(
            series_name=series.name,
            series_kind=series.kind,
            series_level=series.level,
            season=series.season_year,
            valida_num=event.sequence_number,
            event_name=event.name,
            event_date=event.event_date,
            location=event.location or "",
        )

    unknown = keys - _EXPLICIT_MANIFEST_KEYS
    if unknown:
        raise CliError(f"Manifiesto tiene clave(s) desconocida(s): {sorted(unknown)}", exit_code=2)
    missing = _EXPLICIT_MANIFEST_KEYS - keys
    if missing:
        raise CliError(f"Manifiesto le faltan clave(s): {sorted(missing)}", exit_code=2)

    try:
        event_date = date_type.fromisoformat(str(manifest["event_date"]))
    except ValueError as exc:
        raise CliError(f"'event_date' no es una fecha ISO válida: {exc}", exit_code=2)

    try:
        series_kind = RaceSeriesKind(manifest["series_kind"])
        series_level = RaceSeriesLevel(manifest["series_level"])
    except ValueError as exc:
        raise CliError(f"'series_kind'/'series_level' inválido: {exc}", exit_code=2)

    return StageHeader(
        series_name=str(manifest["series_name"]),
        series_kind=series_kind,
        series_level=series_level,
        season=int(manifest["season"]),
        valida_num=int(manifest["valida_num"]),
        event_name=str(manifest["event_name"]),
        event_date=event_date,
        location=str(manifest["location"]),
    )


async def _load_actor(db, user_id: int):
    from sqlalchemy import select

    from app.models.user import User, UserRole

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise CliError(f"--user-id={user_id} no corresponde a ningún usuario.", exit_code=10)
    if not user.is_active:
        raise CliError(f"--user-id={user_id} está inactivo.", exit_code=10)
    if user.role not in (UserRole.admin, UserRole.coach):
        raise CliError(
            f"--user-id={user_id} tiene rol '{user.role.value}' — se requiere coach o admin.",
            exit_code=10,
        )
    return user


def _load_run_document(run_dir: Path):
    from app.services.race.staged_document import StagedProfileMeta, document_from_json

    doc_path = run_dir / "private" / "document.json"
    if not doc_path.exists():
        raise CliError(
            f"No existe {doc_path.name} en el run — corra 'apply' primero.", exit_code=2
        )
    payload = json.loads(doc_path.read_text(encoding="utf-8"))
    document = document_from_json(payload["document"])
    profile_meta = StagedProfileMeta(**payload["profile"])
    return document, profile_meta


# ---------------------------------------------------------------------------
# stage
# ---------------------------------------------------------------------------


def cmd_stage(args: argparse.Namespace) -> int:
    import asyncio

    from app.services.race.results_skill.target import TargetError, resolve_target

    env_dir = Path(__file__).resolve().parents[1]

    async def _run() -> int:
        try:
            target = await resolve_target(args.target, args.confirm, env_dir)
        except TargetError as exc:
            print(str(exc), file=sys.stderr)
            return 11 if exc.code == "schema_head_mismatch" else 9

        scrub = target.scrub
        run_dir = Path(args.run)
        try:
            manifest = _load_manifest_dict(Path(args.manifest))
            source_meta = _load_source_meta(run_dir)
            document, profile_meta = _load_run_document(run_dir)

            file_path = Path(source_meta["path"])
            if not file_path.exists():
                raise CliError(f"Archivo original ya no existe: {file_path}", exit_code=6)
            file_bytes = file_path.read_bytes()
            if hashlib.sha256(file_bytes).hexdigest() != source_meta["sha256"]:
                raise CliError("El archivo cambió desde 'mask' (sha256 no coincide).", exit_code=6)
            results_ext = source_meta["results_ext"]
            if results_ext == "pdf" and file_bytes[:5] != _PDF_MAGIC:
                raise CliError("Evidencia sin magic bytes '%PDF-' válido.", exit_code=2)
            if len(file_bytes) > MAX_EVIDENCE_BYTES:
                raise CliError("Evidencia supera 8 MB.", exit_code=2)

            from fastapi import HTTPException

            from app.services.race.import_staging import stage_extracted_results
            from app.services.request_context import AuditContext

            # Sesión #1, solo de previsualización — SIEMPRE termina en
            # rollback (nunca escribe), incluso en el camino "real" más
            # abajo. Ver nota sobre expiración: ``rollback()`` expira los
            # objetos ORM de la sesión, así que ``actor``/``header`` de
            # esta sesión NUNCA se reutilizan después de cerrarla — la
            # sesión #2, más abajo, los vuelve a cargar frescos.
            async with target.session() as db:
                actor = await _load_actor(db, args.user_id)
                header = await _resolve_header(db, manifest)
                ctx = AuditContext.for_user(actor)
                try:
                    preview = await stage_extracted_results(
                        db,
                        document=document,
                        profile=profile_meta,
                        file_bytes=file_bytes,
                        original_filename=file_path.name,
                        results_ext=results_ext,
                        header=header,
                        actor=actor,
                        ctx=ctx,
                        dry=True,
                    )
                except HTTPException as exc:
                    await db.rollback()
                    raise CliError(f"HTTPException: {exc.status_code}", exit_code=2)
                await db.rollback()

            if preview.already_committed:
                print(f"import_id: {preview.import_id}")
                print("status: already_committed")
                return 8

            if preview.is_revision and not REVISION_STAGING_AVAILABLE:
                print(
                    "revision_not_available: una lectura distinta de una válida "
                    "ya commiteada no se stagea todavía (fase de revisiones "
                    "pendiente)."
                )
                return 12

            if args.dry:
                print(f"status: {preview.status}")
                print(f"rows: {preview.n_rows}")
                print(f"categories: {preview.n_categories}")
                if preview.is_revision:
                    print(f"revisión de la importación #{preview.parent_import_id}")
                return 0

            if preview.import_id is not None:
                # Dedupe: ya existe un import pending con este mismo sha256
                # (fila real, no una previsualización) — no hace falta
                # stagear de nuevo (FR-027, idempotencia).
                print(f"import_id: {preview.import_id}")
                print(f"status: {preview.status}")
                if preview.is_revision:
                    print(f"revisión de la importación #{preview.parent_import_id}")
                print(f"rows: {preview.n_rows}")
                print(f"categories: {preview.n_categories}")
                print(f"/competitions/import?import={preview.import_id}")
                return 0

            # Sesión #2, real — carga su propio actor/header frescos.
            async with target.session() as db:
                actor = await _load_actor(db, args.user_id)
                header = await _resolve_header(db, manifest)
                ctx = AuditContext.for_user(actor)
                try:
                    result = await stage_extracted_results(
                        db,
                        document=document,
                        profile=profile_meta,
                        file_bytes=file_bytes,
                        original_filename=file_path.name,
                        results_ext=results_ext,
                        header=header,
                        actor=actor,
                        ctx=ctx,
                        dry=False,
                    )
                except HTTPException as exc:
                    await db.rollback()
                    raise CliError(f"HTTPException: {exc.status_code}", exit_code=2)
                await db.commit()

            print(f"import_id: {result.import_id}")
            print(f"status: {result.status}")
            if result.is_revision:
                print(f"revisión de la importación #{result.parent_import_id}")
            print(f"rows: {result.n_rows}")
            print(f"categories: {result.n_categories}")
            if result.warnings:
                print(f"warnings: {result.warnings}")
            print(f"/competitions/import?import={result.import_id}")
            _write_report(
                run_dir,
                {
                    "subcommand": "stage",
                    "exit_code": 0,
                    "import_id": result.import_id,
                    "status": result.status,
                    "is_revision": result.is_revision,
                    "rows": result.n_rows,
                    "categories": result.n_categories,
                },
            )
            return 0
        except CliError as exc:
            print(scrub(str(exc)), file=sys.stderr)
            return exc.exit_code

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# compare (solo lectura)
# ---------------------------------------------------------------------------


def cmd_compare(args: argparse.Namespace) -> int:
    """Compara ``private/document.json`` con lo commiteado de la misma
    válida en el destino. Solo lectura — la sesión abre en modo
    ``READ ONLY`` sobre MySQL y siempre termina en ``rollback()``.

    Desviación deliberada frente a ``revision-via-skill.md`` §"Identity-aware
    diff": este comparador cuenta por ``(category_code, normalized_name)``
    exacto (``normalizer.normalize_name``), sin resolución de identidad ni
    fallback difuso — es de solo lectura para el operador, no alimenta un
    commit, y la resolución de identidad real vive en ``identity_resolver``
    (fuera de alcance de esta tarea). Documentado para la próxima ola.
    """
    import asyncio

    from app.services.race.results_skill.target import TargetError, resolve_target

    env_dir = Path(__file__).resolve().parents[1]

    async def _run() -> int:
        try:
            target = await resolve_target(args.target, args.confirm, env_dir)
        except TargetError as exc:
            print(str(exc), file=sys.stderr)
            return 11 if exc.code == "schema_head_mismatch" else 9

        scrub = target.scrub
        try:
            run_dir = Path(args.run)
            document, _profile_meta = _load_run_document(run_dir)

            manifest: dict[str, Any] = {}
            if args.manifest:
                manifest = _load_manifest_dict(Path(args.manifest))
            elif args.race_event_id is not None:
                manifest = {"race_event_id": args.race_event_id}
            else:
                raise CliError("--manifest o --race-event-id es requerido.", exit_code=2)

            from sqlalchemy import select

            from app.models.race_category import RaceCategory
            from app.models.race_competitor import RaceCompetitor
            from app.models.race_event import RaceEvent
            from app.models.race_result import RaceResult
            from app.models.race_series import RaceSeries
            from app.services.race.normalizer import normalize_name

            from sqlalchemy import text as sa_text

            async with target.session() as db:
                try:
                    await db.execute(sa_text("SET TRANSACTION READ ONLY"))
                except Exception:  # noqa: BLE001 — no todo dialecto lo soporta (sqlite en pruebas)
                    pass

                try:
                    header = await _resolve_header(db, manifest)
                except CliError:
                    await db.rollback()
                    print("válida no encontrada en el destino.", file=sys.stderr)
                    return 7

                series = (
                    await db.execute(
                        select(RaceSeries).where(
                            RaceSeries.name == header.series_name,
                            RaceSeries.season_year == header.season,
                        )
                    )
                ).scalar_one_or_none()
                event = None
                if series is not None:
                    event = (
                        await db.execute(
                            select(RaceEvent).where(
                                RaceEvent.series_id == series.id,
                                RaceEvent.sequence_number == header.valida_num,
                            )
                        )
                    ).scalar_one_or_none()
                if event is None:
                    await db.rollback()
                    print("válida no encontrada en el destino.", file=sys.stderr)
                    return 7

                committed_rows = (
                    await db.execute(
                        select(RaceResult, RaceCategory.code, RaceCompetitor.normalized_name)
                        .join(RaceCategory, RaceResult.category_id == RaceCategory.id)
                        .join(RaceCompetitor, RaceResult.competitor_id == RaceCompetitor.id)
                        .where(RaceResult.event_id == event.id, RaceResult.deleted_at.is_(None))
                    )
                ).all()
                await db.rollback()

            committed_by_key: dict[tuple[str, str], Any] = {}
            for row, code, norm_name in committed_rows:
                committed_by_key[(code, norm_name)] = row

            per_category: dict[str, dict[str, int]] = {}
            seen_keys: set[tuple[str, str]] = set()
            for category in document.categories:
                code = category.code or "—"
                counts = per_category.setdefault(
                    code, {"matched": 0, "changed": 0, "missing": 0, "extra": 0}
                )
                for row in category.rows:
                    key = (category.code, normalize_name(row.name))
                    seen_keys.add(key)
                    committed = committed_by_key.get(key)
                    if committed is None:
                        counts["extra"] += 1
                        continue
                    same_position = committed.position == row.position
                    if same_position:
                        counts["matched"] += 1
                    else:
                        counts["changed"] += 1

            for (code, _norm_name), _committed in committed_by_key.items():
                if (code, _norm_name) not in seen_keys:
                    per_category.setdefault(
                        code or "—", {"matched": 0, "changed": 0, "missing": 0, "extra": 0}
                    )["missing"] += 1

            for code in sorted(per_category):
                c = per_category[code]
                print(
                    f"{code}: matched={c['matched']} changed={c['changed']} "
                    f"missing={c['missing']} extra={c['extra']}"
                )
            return 0
        except CliError as exc:
            print(scrub(str(exc)), file=sys.stderr)
            return exc.exit_code

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="race_results", description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_mask = sub.add_parser("mask", help="Enmascara un archivo oficial fuera del repositorio.")
    p_mask.add_argument("--file", required=True)
    p_mask.set_defaults(func=cmd_mask)

    p_pc = sub.add_parser("profile-check", help="Valida un perfil de lectura.")
    p_pc.add_argument("--profile", required=True)
    p_pc.set_defaults(func=cmd_profile_check)

    p_apply = sub.add_parser("apply", help="Aplica un perfil sobre el run enmascarado.")
    p_apply.add_argument("--run", required=True)
    p_apply.add_argument("--profile", required=True)
    p_apply.set_defaults(func=cmd_apply)

    p_compare = sub.add_parser("compare", help="Compara (solo lectura) contra el destino.")
    p_compare.add_argument("--run", required=True)
    p_compare.add_argument("--target", default="local")
    p_compare.add_argument("--confirm")
    p_compare.add_argument("--race-event-id", type=int)
    p_compare.add_argument("--manifest")
    p_compare.set_defaults(func=cmd_compare)

    p_stage = sub.add_parser("stage", help="Stagea la importación (nunca commitea).")
    p_stage.add_argument("--run", required=True)
    p_stage.add_argument("--manifest", required=True)
    p_stage.add_argument("--user-id", type=int, required=True)
    p_stage.add_argument("--target", default="local")
    p_stage.add_argument("--confirm")
    p_stage.add_argument("--dry", action="store_true")
    p_stage.set_defaults(func=cmd_stage)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001 — nunca el mensaje crudo, solo clase.
        print(f"{type(exc).__name__}: error inesperado", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
