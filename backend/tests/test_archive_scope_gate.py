"""La compuerta estática de FR-014 (feature 041, US2, contract
``athlete-archive.md`` §5.4, §12.5).

Recorre ``backend/app/`` en busca de las cuatro firmas textuales que el
contrato marca como de alto riesgo — ``select(Athlete)``,
``Athlete.id.in_(``, ``join(Athlete`` y ``Athlete.club_id`` — y falla si el
cuerpo de la función que contiene ese sitio no aplica
``Athlete.deleted_at.is_(None)`` (directo o vía un helper como
``active_athletes_stmt()``) y el sitio tampoco está en ``ARCHIVE_SCOPE_EXEMPT``
(la lista revisada de §5.3: consultas que deben seguir incluyendo al
atleta archivado — guardrails de redacción de nombres para IA/boletines y la
vista admin de "atletas archivados").

Esta es la "compuerta barata" del contrato — no reemplaza la prueba de
comportamiento real de ``test_archived_athlete_absent.py``, la complementa:
una consulta nueva que se agregue sin el filtro debe fallar aquí incluso si
nadie escribe todavía un test de comportamiento para ella. Es un análisis
estático puro (``ast`` sobre el código fuente en disco) — no importa
``app.main`` ni levanta ninguna base de datos, así que no depende de que la
app termine de arrancar.

Ningún nombre en este archivo corresponde a una persona real (CLAUDE.md,
Ley 1581).
"""
from __future__ import annotations

import ast
import io
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

# Las cuatro firmas textuales de contracts/athlete-archive.md §5.4.
_RISK_PATTERNS = (
    "select(Athlete)",
    "Athlete.id.in_(",
    "join(Athlete",
    "Athlete.club_id",
)

# Cualquiera de estos, presente en el cuerpo fuente de la función que
# contiene el sitio de riesgo, cuenta como "sí filtra". ``verify_athlete_access``
# es la compuerta C3 del contrato (``app/dependencies.py``): cualquier
# endpoint que reciba el atleta a través de esa dependencia ya tiene el
# 404-si-archivado aplicado antes de que el cuerpo de la función se ejecute.
_FILTER_MARKERS = ("deleted_at", "active_athletes_stmt", "verify_athlete_access")

# Directorios que no son código de aplicación con consultas reales, o que
# el contrato no cubre (migraciones, scripts de una sola vez). ``models``
# se excluye porque las coincidencias ahí son declaraciones ORM
# (``relationship(..., foreign_keys="[Athlete.club_id]")``), no sitios de
# consulta.
_EXCLUDED_PARTS = {"__pycache__", "alembic", "migrations", "models"}


# ---------------------------------------------------------------------------
# §5.3 — la lista revisada de exenciones. Cada entrada es una consulta que
# DEBE seguir incluyendo al atleta archivado: filtrarla reduciría la
# privacidad (rompe la redacción de nombres de un compañero archivado) o
# borraría evidencia histórica (la vista admin del archivo).
# ---------------------------------------------------------------------------
ARCHIVE_SCOPE_EXEMPT: dict[tuple[str, str], str] = {
    (
        "routers/athlete_monthly_newsletters.py",
        "_build_forbidden_names",
    ): "guardrail de redacción de nombres del boletín mensual — un "
    "compañero archivado puede seguir siendo nombrado en una nota libre "
    "del coach; quitar su nombre de forbidden_names rompe la redacción",
    (
        "services/training/reports.py",
        "generate_monthly_report",
    ): "mismo guardrail de redacción, para el reporte mensual",
    (
        "services/training/reports.py",
        "update_report_blocks",
    ): "mismo guardrail de redacción, para el reporte mensual (segundo sitio)",
    (
        "services/training/session_assistant_context.py",
        "load_club_athlete_name_tokens",
    ): "mismo guardrail de redacción, para el asistente de sesión",
    (
        "services/race/ai/athlete_context.py",
        "load_club_forbidden_names",
    ): "mismo guardrail de redacción, para el scrubbing de análisis de "
    "carreras — 'NUNCA se pasa al LLM, solo alimenta scrubbing/guardrails'",
    (
        "services/training/reports.py",
        "regenerate_block",
    ): "mismo guardrail de redacción, para el reporte mensual (tercer sitio "
    "— ``real_names`` alimenta ``build_context_from_metrics``, igual que en "
    "``generate_monthly_report``)",
    (
        "routers/athletes.py",
        "list_athletes",
    ): "GET /api/athletes?include_archived=true — la vista admin del "
    "archivo (US2 AS2) necesita ver al atleta archivado a propósito",
    (
        "routers/race_analysis.py",
        "_resolve_athlete_club",
    ): "resolutor de ``club_id`` exclusivo del rastro de auditoría "
    "(``record_audit(club_id=...)``, escalera §1.6 de audit-recording.md). "
    "Filtrarlo dejaría sin club las filas de auditoría de un atleta "
    "archivado — borra evidencia, no la protege (§5.3). La compuerta real "
    "de 'no lanzar un run para un atleta archivado' vive en el endpoint de "
    "arranque, no aquí",
    (
        "routers/strava_integration.py",
        "_athlete_club_ids",
    ): "mismo caso: mapa ``athlete_id -> club_id`` que solo alimenta "
    "``record_audit(club_id=...)`` del cron de reconcile. El filtro real "
    "del feed de terceros está en ``services/strava/reconcile.py``, que ya "
    "aplica ``Athlete.deleted_at.is_(None)``",
    (
        "routers/webhooks_resend.py",
        "resend_webhook",
    ): "webhook de Resend sobre un correo YA enviado: solo registra el "
    "evento de entrega (delivered/bounced/opened) de una bitácora del "
    "pasado. §5.3 'cualquier consulta que reconstruye un período cerrado' "
    "— filtrar aquí descartaría silenciosamente la evidencia de entrega de "
    "un atleta archivado después del envío. No dispara ningún correo nuevo",
    (
        "services/coach_activity.py",
        "compute_coach_activity",
    ): "informe de actividad por entrenador (US7, T081): reconstruye un "
    "período cerrado. ``contracts/coach-activity-report.md`` §1.4 lo dice "
    "literalmente — 'those sessions and attendance rows still count — a "
    "report reconstructing a past period must not filter "
    "athletes.deleted_at' — remitiendo a ``data-model.md`` §8.1 'Sites "
    "that must not filter'. Archivar a un menor no puede reescribir el "
    "trabajo que un adulto hizo en ese mes. El único uso del atleta aquí "
    "es el alcance por club de ``agent_runs`` (``athlete_id`` → "
    "``club_id``): ni su id ni su nombre salen jamás en el payload, que "
    "son nombres de personal adulto y enteros",
}


@dataclass(frozen=True)
class RiskSite:
    relative_path: str
    function_name: str
    lineno: int
    pattern: str


def _iter_app_files() -> list[Path]:
    files = []
    for path in APP_ROOT.rglob("*.py"):
        if any(part in _EXCLUDED_PARTS for part in path.parts):
            continue
        files.append(path)
    return files


def _enclosing_function(tree: ast.Module, lineno: int) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """La función (sync o async) más interna cuyo cuerpo contiene ``lineno``."""
    best: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = max(
                (getattr(n, "lineno", start) for n in ast.walk(node)),
                default=start,
            )
            if start <= lineno <= end:
                if best is None or node.lineno > best.lineno:
                    best = node
    return best


def _string_and_comment_lines(source: str) -> set[int]:
    """Líneas que son texto (comentario, docstring, string multi-línea).

    Filtra falsos positivos como una firma citada dentro de un docstring de
    diseño (``services/race/matcher.py``: "el caller hace el
    select(Athlete).where(club_id=...)"). Una línea cuenta como "texto" si
    es enteramente parte de un token COMMENT o de un token STRING que
    empieza antes de esa línea (docstring/string multi-línea) — una string
    de una sola línea con código real al lado en la misma línea no cuenta,
    para no ocultar un ``select(Athlete)`` real que comparte línea con un
    string corto.
    """
    text_lines: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                text_lines.add(tok.start[0])
            elif tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                # String multi-línea: todas sus líneas son texto, incluida
                # la primera (nunca hay código real antes de una comilla
                # triple de apertura en este código base).
                text_lines.update(range(tok.start[0], tok.end[0] + 1))
    except tokenize.TokenizeError:  # pragma: no cover - archivo binario/roto
        pass
    return text_lines


def _find_risk_sites() -> tuple[list[RiskSite], list[str]]:
    """Retorna (sitios sin resolver, archivos con error de parseo)."""
    unresolved: list[RiskSite] = []
    parse_errors: list[str] = []

    for path in _iter_app_files():
        relative_path = str(path.relative_to(APP_ROOT))
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        text_lines = _string_and_comment_lines(source)

        matched_linenos = [
            (i + 1, pattern)
            for i, line in enumerate(lines)
            for pattern in _RISK_PATTERNS
            if pattern in line and (i + 1) not in text_lines
        ]
        if not matched_linenos:
            continue

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - señal de un archivo roto
            parse_errors.append(f"{relative_path}: {exc}")
            continue

        for lineno, pattern in matched_linenos:
            func = _enclosing_function(tree, lineno)
            func_name = func.name if func is not None else "<module>"

            if func is not None:
                func_source = ast.get_source_segment(source, func) or ""
            else:
                func_source = source

            filters_ok = any(marker in func_source for marker in _FILTER_MARKERS)
            exempted = (relative_path, func_name) in ARCHIVE_SCOPE_EXEMPT

            if not filters_ok and not exempted:
                unresolved.append(
                    RiskSite(
                        relative_path=relative_path,
                        function_name=func_name,
                        lineno=lineno,
                        pattern=pattern,
                    )
                )

    return unresolved, parse_errors


def test_no_unparsed_app_files():
    """Un archivo con SyntaxError deja huecos ciegos en la compuerta —
    tratar eso como un fallo explícito, no un ``continue`` silencioso.
    """
    _, parse_errors = _find_risk_sites()
    assert not parse_errors, f"Archivos que no se pudieron parsear: {parse_errors}"


def test_every_athlete_query_filters_or_is_exempt():
    unresolved, _ = _find_risk_sites()
    if unresolved:
        detail = "\n".join(
            f"  {s.relative_path}:{s.lineno} en {s.function_name}() — patrón "
            f"'{s.pattern}' sin Athlete.deleted_at.is_(None) ni exención"
            for s in unresolved
        )
        pytest.fail(
            "Sitios que consultan Athlete sin filtrar archivados y sin "
            "exención registrada en ARCHIVE_SCOPE_EXEMPT:\n" + detail
        )


def test_archive_scope_exempt_entries_are_real():
    """Cada exención debe apuntar a una función que de verdad exista hoy —
    si el código se reorganiza y la función desaparece o se renombra, la
    exención queda huérfana (protege contra podredumbre silenciosa).
    """
    orphaned = []
    for (relative_path, function_name), _reason in ARCHIVE_SCOPE_EXEMPT.items():
        path = APP_ROOT / relative_path
        if not path.is_file():
            orphaned.append(f"{relative_path} no existe")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if function_name not in names:
            orphaned.append(f"{relative_path}::{function_name} ya no existe")

    assert not orphaned, f"Exenciones huérfanas en ARCHIVE_SCOPE_EXEMPT: {orphaned}"


def test_archive_scope_exempt_matches_contract_section_5_3():
    """Ancla el tamaño y la forma del set exento a lo revisado en el
    contrato — agregar una exención nueva debe ser un diff explícito en
    este test, no un cambio silencioso.
    """
    expected_files = {
        "routers/athlete_monthly_newsletters.py",
        "services/training/reports.py",
        "services/training/session_assistant_context.py",
        "services/race/ai/athlete_context.py",
        "routers/athletes.py",
        # Añadidos en G15 (feature 041): resolutores de ``club_id`` que solo
        # alimentan el rastro de auditoría, y el webhook de entrega de un
        # correo ya enviado. Ver la razón de cada uno arriba.
        "routers/race_analysis.py",
        "routers/strava_integration.py",
        "routers/webhooks_resend.py",
        # Añadido en T081 (feature 041, US7): una sola entrada,
        # ``services/coach_activity.py::compute_coach_activity``, el informe
        # de actividad por entrenador. Es un reconstructor de período
        # cerrado — §1.4 del contrato lo lista entre los sitios que NO deben
        # filtrar ``deleted_at``. Sus dos sitios de riesgo
        # (``Athlete.club_id`` y ``join(Athlete``) viven en la misma
        # función, así que suman una única entrada al conteo.
        "services/coach_activity.py",
    }
    actual_files = {relative_path for relative_path, _ in ARCHIVE_SCOPE_EXEMPT}
    assert actual_files == expected_files
    # 10 exenciones revisadas hasta G15 + 1 de T081 (ver comentario arriba).
    assert len(ARCHIVE_SCOPE_EXEMPT) == 11


def test_gate_actually_detects_an_unfiltered_query(tmp_path, monkeypatch):
    """Prueba negativa: sin esto, la compuerta podría estar pasando porque
    nunca encuentra nada que reportar, no porque el código esté limpio.
    """
    bad_file = tmp_path / "unfiltered_example.py"
    bad_file.write_text(
        "from app.models.athlete import Athlete\n"
        "from sqlalchemy import select\n\n"
        "async def list_everyone(db):\n"
        "    result = await db.execute(select(Athlete))\n"
        "    return result.scalars().all()\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys.modules[__name__], "APP_ROOT", tmp_path)
    unresolved, _ = _find_risk_sites()
    assert len(unresolved) == 1
    assert unresolved[0].function_name == "list_everyone"
