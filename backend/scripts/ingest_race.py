"""CLI Typer para ingesta y análisis de resultados Copa Valle XCO.

Herramienta legacy F1.7. Para uso cotidiano del coach existe el wizard
web `/coach/race-analysis` tab "Cargar resultados" (F-UP + F-UP-REV). Este
CLI permanece como utilidad de mantenimiento/backfill o backup si el
wizard falla.

Subcomandos:
- ``ingest``   — parsea PDFs RESULTADOS + GENERAL, captura condiciones del
  evento, confirma matches TyR vía top-3 del matcher y ejecuta
  ``RaceIngestor.ingest_event``. Modo ``--non-interactive`` lee YAML para CI.
- ``analyze evolution|gap|ranking|projection`` — wrappers sobre
  ``app.services.race.analytics`` (Paso 5). Si el módulo no existe, el
  subcomando reporta el estado pendiente y sale con código 2.
- ``riders list|link`` — utilidades de consulta y vinculación manual
  competitor → athlete.

Restricciones inviolables (CLAUDE.md + workflow §6.4):
- Default conservador con nombres: ``riders list`` muestra inicial+apellido
  (``T. Duque``) salvo flag ``--show-names``. ``ingest`` SÍ muestra nombres
  completos al coach durante confirmación de matches — es contexto
  autenticado y necesario para la decisión.
- Logs INFO nunca llevan nombres completos (los warnings del ingestor usan
  bib + cat). El CLI puede imprimir nombres a stdout sólo bajo flag explícito
  o en flujo interactivo del coach.
- El CLI nunca auto-asigna ``athlete_id`` — todas las asignaciones pasan por
  prompt o por el YAML de ``--match-decisions``.
- Para predicciones con ``n < 5``, el subcomando ``projection`` muestra
  ``confidence: low`` con warning explícito.

Uso típico interactivo (Paso 9 backfill):

    cd backend
    python -m scripts.ingest_race ingest \\
        --results /ruta/valida_iv_resultados.pdf \\
        --general /ruta/valida_iv_general.pdf

Modo CI/tests determinístico:

    python -m scripts.ingest_race ingest \\
        --results path.pdf --general path.pdf \\
        --non-interactive \\
        --event-meta /tmp/event.yaml \\
        --match-decisions /tmp/matches.yaml
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.athlete import Athlete
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import SurfaceCondition
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.schemas.race import EventMeta, IngestReport
from app.services.race.ingestor import RaceIngestor
from app.services.race.matcher import MatchCandidate, match_athletes
from app.services.race.normalizer import is_trocha_y_ruta
from app.services.race.csv_parser import (
    parse_event_header_csv,
    parse_results_csv,
)
from app.services.race.pdf_parser import (
    EventHeader,
    ResultsRow,
    parse_event_header,
    parse_general_pdf,
    parse_results_pdf,
)

# ---------------------------------------------------------------------------
# Logging conservador — INFO sin nombres, propagado al ingestor
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ingest_race")

# Console rich global — autodetecta TTY vs pipe (apaga color en CI)
console = Console()


# ---------------------------------------------------------------------------
# App Typer raíz + subapps
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="ingest_race",
    add_completion=False,
    no_args_is_help=True,
    help="Ingesta y análisis de resultados Copa Valle XCO (Trocha y Ruta).",
)
analyze_app = typer.Typer(
    name="analyze", no_args_is_help=True, help="Analíticas sobre datos persistidos."
)
riders_app = typer.Typer(
    name="riders", no_args_is_help=True, help="Listado y vinculación de competidores."
)
app.add_typer(analyze_app, name="analyze")
app.add_typer(riders_app, name="riders")


# ---------------------------------------------------------------------------
# Helpers de I/O — async session, SHA256, YAML, masking
# ---------------------------------------------------------------------------


def _open_session() -> AsyncSession:
    """Devuelve una nueva sesión async. Centraliza para tests (monkeypatch).

    Cada subcomando abre y cierra su propia sesión. No usamos context manager
    aquí porque los helpers async la consumen vía ``async with``.
    """
    return AsyncSessionLocal()


async def _get_or_create_system_user(db: AsyncSession) -> int:
    """Devuelve el ``id`` del user ``system@trochyruta.com`` (crea si no existe).

    Este user es el ``created_by_user_id`` por defecto cuando el CLI no tiene
    autenticación. ``can_login=False`` para evitar que sea una cuenta real.
    """
    result = await db.execute(select(User).where(User.email == "system@trochyruta.com"))
    user = result.scalar_one_or_none()
    if user is not None:
        return user.id

    user = User(
        email="system@trochyruta.com",
        first_name="System",
        last_name="CLI",
        role=UserRole.admin,
        is_active=True,
        can_login=False,
    )
    db.add(user)
    await db.flush()
    await db.commit()
    return user.id


def _sha256_of(path: Path) -> str:
    """SHA256 hex de un archivo (lectura en chunks de 64KB)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_yaml(path: Path) -> Any:
    """Lee YAML con ``safe_load``. Devuelve dict/list/None según contenido."""
    if not path.exists():
        raise typer.BadParameter(f"YAML no encontrado: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _mask_name(full: str) -> str:
    """Devuelve ``"T. Duque"`` para ``"Thiago Duque Cardona"`` — privacy default.

    Estrategia: primera inicial del primer nombre + último apellido. Si el
    nombre tiene un solo token, retorna ``"T."`` (inicial). Si está vacío,
    retorna ``"?"``.
    """
    if not full or not full.strip():
        return "?"
    parts = [p for p in full.strip().split() if p]
    if len(parts) == 1:
        return f"{parts[0][0].upper()}."
    return f"{parts[0][0].upper()}. {parts[-1]}"


def _present_name(full: str, *, show: bool) -> str:
    """Convención CLI: enmascarar por defecto, mostrar completo si ``show=True``."""
    return full if show else _mask_name(full)


# ---------------------------------------------------------------------------
# Helpers rich — tablas estandarizadas
# ---------------------------------------------------------------------------


def _print_table(
    title: str,
    headers: Iterable[str],
    rows: Iterable[Iterable[Any]],
    *,
    caption: Optional[str] = None,
) -> None:
    """Tabla rich con estilo del proyecto. ``rows`` se convierten a ``str``."""
    table = Table(title=title, caption=caption, header_style="bold cyan")
    for h in headers:
        table.add_column(h)
    for r in rows:
        table.add_row(*[str(c) if c is not None else "—" for c in r])
    console.print(table)


def _print_ingest_report(report: IngestReport) -> None:
    """Imprime ``IngestReport`` formateado + warnings (sin nombres)."""
    panel = Panel(
        f"[bold]event_id[/]: {report.event_id}  "
        f"[bold]series_id[/]: {report.series_id}\n"
        f"[bold]competitors_created[/]: {report.competitors_created}  "
        f"[bold]competitors_updated[/]: {report.competitors_updated}\n"
        f"[bold]results_inserted[/]: {report.results_inserted}  "
        f"[bold]results_skipped[/]: {report.results_skipped}\n"
        f"[bold green]tyr_count[/]: {report.tyr_count}\n"
        f"[bold yellow]warnings[/]: {len(report.warnings)}",
        title="IngestReport",
        border_style="green" if not report.warnings else "yellow",
    )
    console.print(panel)
    if report.warnings:
        console.print("[yellow]Warnings:[/]")
        for w in report.warnings:
            console.print(f"  • {w}")


# ---------------------------------------------------------------------------
# Despacho de parser según extensión (.pdf vs .csv)
# ---------------------------------------------------------------------------


def _is_csv_source(path: Path) -> bool:
    """``True`` si la extensión sugiere CSV/XLSX exportado a CSV."""
    return path.suffix.lower() in {".csv", ".tsv", ".txt"}


def _parse_results_auto(path: Path) -> dict[str, list[ResultsRow]]:
    """Despacha al parser correcto según extensión del archivo de RESULTADOS."""
    if _is_csv_source(path):
        return parse_results_csv(path)
    return parse_results_pdf(path)


def _parse_event_header_auto(path: Path) -> Optional[EventHeader]:
    """Despacha al detector de header correcto según extensión."""
    if _is_csv_source(path):
        return parse_event_header_csv(path)
    return parse_event_header(path)


# ---------------------------------------------------------------------------
# ingest — flujo interactivo + non-interactive
# ---------------------------------------------------------------------------


@app.command("ingest")
def ingest_cmd(
    results: Path = typer.Option(
        ...,
        "--results",
        help=(
            "Ruta al archivo RESULTADOS. Extensión define el formato: "
            ".pdf (PDF oficial Federación) o .csv (export tabular oficial)."
        ),
    ),
    general: Optional[Path] = typer.Option(
        None,
        "--general",
        help=(
            "Ruta al PDF GENERAL acumulado (opcional pero recomendado). "
            "Sólo formato PDF — Federación no publica GENERAL en CSV."
        ),
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Lee meta + decisiones desde YAML (CI/tests)."
    ),
    event_meta_path: Optional[Path] = typer.Option(
        None, "--event-meta", help="YAML con campos de EventMeta (--non-interactive)."
    ),
    match_decisions_path: Optional[Path] = typer.Option(
        None,
        "--match-decisions",
        help="YAML con lista [{bib, athlete_id}] (--non-interactive).",
    ),
    user_id: Optional[int] = typer.Option(
        None, "--user-id", help="user.id que firma la ingesta (default: system user)."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Saltar confirmación final (peligroso en interactivo)."
    ),
) -> None:
    """Ingesta una válida desde PDFs oficiales (o CSV/XLSX exportado).

    Flujo interactivo (default):
    1. Parsea RESULTADOS (autodetecta PDF/CSV por extensión) y GENERAL (PDF).
    2. Detecta header del archivo (``valida_num``, ``location``, ``event_date``).
       Si falta algo, pregunta.
    3. Pregunta condiciones: clima, temperatura, superficie, altitud, notas.
    4. Muestra resumen (categorías, corredores, TyR detectados).
    5. Por cada TyR sin match previo, muestra top-3 athletes con nombres
       completos (contexto autenticado del coach) y pide decisión.
    6. Confirma ``[y/N]`` antes de ejecutar (a menos que ``--yes``).
    7. Ejecuta ingest atómico y reporta.

    Modo ``--non-interactive``:
        - Lee ``--event-meta`` (todos los campos de EventMeta).
        - Lee ``--match-decisions`` (lista de ``{bib, athlete_id}``).
        - Salta toda interacción. Determinístico para tests.
    """
    asyncio.run(
        _ingest_impl(
            results=results,
            general=general,
            non_interactive=non_interactive,
            event_meta_path=event_meta_path,
            match_decisions_path=match_decisions_path,
            user_id=user_id,
            confirm_yes=yes,
        )
    )


async def _ingest_impl(
    *,
    results: Path,
    general: Optional[Path],
    non_interactive: bool,
    event_meta_path: Optional[Path],
    match_decisions_path: Optional[Path],
    user_id: Optional[int],
    confirm_yes: bool,
) -> None:
    """Implementación async del subcomando ``ingest`` — separada para test."""
    if not results.exists():
        console.print(f"[red]RESULTADOS no encontrado:[/] {results}")
        raise typer.Exit(code=1)
    if general is not None and not general.exists():
        console.print(f"[red]GENERAL no encontrado:[/] {general}")
        raise typer.Exit(code=1)

    # 1. Parsear RESULTADOS (PDF o CSV según extensión)
    fmt_results = "CSV" if _is_csv_source(results) else "PDF"
    console.print(f"[cyan]Parseando RESULTADOS ({fmt_results})[/]: {results.name}")
    parsed_results = _parse_results_auto(results)
    total_rows = sum(len(rs) for rs in parsed_results.values())
    tyr_in_results = sum(
        1
        for rows in parsed_results.values()
        for r in rows
        if is_trocha_y_ruta(r.club)
    )

    parsed_general: dict[str, list] = {}
    if general is not None:
        console.print(f"[cyan]Parseando GENERAL[/]: {general.name}")
        parsed_general = parse_general_pdf(general)

    console.print(
        f"[green]✓[/] Parseo OK: {len(parsed_results)} categorías | "
        f"{total_rows} corredores | {tyr_in_results} TyR"
    )

    # 2. Resolver EventMeta
    if non_interactive:
        if event_meta_path is None:
            console.print("[red]--non-interactive requiere --event-meta[/]")
            raise typer.Exit(code=2)
        meta = _meta_from_yaml(_load_yaml(event_meta_path), results, general)
    else:
        meta = _meta_from_interactive(results, general)

    # 3. SHA256 (para idempotencia)
    sha_results = _sha256_of(results)
    sha_general = _sha256_of(general) if general is not None else None

    # 4. Cargar match decisions
    if non_interactive:
        decisions = _decisions_from_yaml(
            _load_yaml(match_decisions_path) if match_decisions_path else []
        )
    else:
        # En interactivo, los matches se resuelven dentro de la sesión DB
        # (para poder consultar Athletes existentes y ofrecer top-3).
        decisions = None  # señal de que hay que pedirlos online

    # 5. Open session + ejecutar
    async with _open_session() as db:
        ingester_uid = user_id if user_id is not None else await _get_or_create_system_user(db)

        if decisions is None:
            # Interactivo: pedir decisiones ahora que tenemos DB
            decisions = await _collect_match_decisions_interactive(db, parsed_results)

        # Resumen + confirmación
        _print_table(
            "Resumen previo a ingest",
            ["Métrica", "Valor"],
            [
                ("Válida", meta.valida_num),
                ("Evento", meta.name),
                ("Fecha", meta.event_date.isoformat()),
                ("Ubicación", meta.location),
                ("Categorías", len(parsed_results)),
                ("Corredores total", total_rows),
                ("TyR detectados", tyr_in_results),
                ("Match decisions", len(decisions)),
            ],
        )

        if not confirm_yes and not non_interactive:
            ok = typer.confirm("Ejecutar ingest?", default=False)
            if not ok:
                console.print("[yellow]Abortado por el usuario.[/]")
                raise typer.Exit(code=0)

        ingestor = RaceIngestor(db)
        report = await ingestor.ingest_event(
            meta=meta,
            results_by_category=parsed_results,
            general_by_category=parsed_general or None,
            match_decisions=decisions,
            pdf_results_sha256=sha_results,
            pdf_general_sha256=sha_general,
            ingested_by_user_id=ingester_uid,
        )

    _print_ingest_report(report)

    # 6. Comparativa con válida anterior (best-effort)
    try:
        await _print_previous_valida_comparison(meta=meta, report=report)
    except Exception as exc:  # pragma: no cover — no debe romper ingest exitoso
        logger.warning("Comparativa válida anterior falló: %s", exc)


# ---------------------------------------------------------------------------
# Helpers de EventMeta — YAML vs interactivo
# ---------------------------------------------------------------------------


def _meta_from_yaml(
    data: dict, results_path: Path, general_path: Optional[Path]
) -> EventMeta:
    """Construye ``EventMeta`` desde dict YAML, enriqueciendo con filenames."""
    # Tipos defensivos (YAML retorna strings)
    raw_temp = data.get("temperature_c")
    temp: Optional[Decimal]
    if raw_temp is None or raw_temp == "":
        temp = None
    else:
        try:
            temp = Decimal(str(raw_temp))
        except InvalidOperation as exc:
            raise typer.BadParameter(f"temperature_c inválida: {raw_temp!r}") from exc

    # Parsear surface_condition si es string
    raw_surface = data.get("surface_condition")
    surface: Optional[SurfaceCondition]
    if raw_surface is None or raw_surface == "":
        surface = None
    elif isinstance(raw_surface, SurfaceCondition):
        surface = raw_surface
    else:
        try:
            surface = SurfaceCondition(str(raw_surface))
        except ValueError as exc:
            raise typer.BadParameter(
                f"surface_condition inválida: {raw_surface!r}. "
                f"Permitidas: {[s.value for s in SurfaceCondition]}"
            ) from exc

    # event_date acepta date o str ISO
    raw_date = data.get("event_date")
    if isinstance(raw_date, date):
        evt_date = raw_date
    elif isinstance(raw_date, str):
        evt_date = date.fromisoformat(raw_date)
    else:
        raise typer.BadParameter(f"event_date requerido (ISO YYYY-MM-DD): {raw_date!r}")

    return EventMeta(
        season=int(data.get("season", 2026)),
        copa_code=str(data.get("copa_code", "copa_valle")),
        valida_num=int(data["valida_num"]),
        name=str(data.get("name", f"Valida {data['valida_num']}")),
        event_date=evt_date,
        location=str(data.get("location", "")),
        climate=data.get("climate"),
        temperature_c=temp,
        surface_condition=surface,
        altitude_msnm=(int(data["altitude_msnm"]) if data.get("altitude_msnm") is not None else None),
        weather_notes=data.get("weather_notes"),
        pdf_results_filename=results_path.name,
        pdf_general_filename=(general_path.name if general_path else None),
    )


def _meta_from_interactive(
    results_path: Path, general_path: Optional[Path]
) -> EventMeta:
    """Construye ``EventMeta`` vía prompts, pre-rellenando desde header del archivo."""
    detected = _parse_event_header_auto(results_path)
    if detected is not None:
        console.print(
            f"[green]Header detectado:[/] Válida {detected.valida_num} en "
            f"{detected.location} ({detected.event_date.isoformat()})"
        )
        valida_num = typer.prompt("valida_num", default=str(detected.valida_num), type=int)
        location = typer.prompt("location", default=detected.location)
        event_date_str = typer.prompt("event_date (YYYY-MM-DD)", default=detected.event_date.isoformat())
        default_name = f"VALIDA {valida_num} {location} {detected.raw_text}"
    else:
        console.print("[yellow]Header no detectado — proporciona manualmente.[/]")
        valida_num = typer.prompt("valida_num", type=int)
        location = typer.prompt("location")
        event_date_str = typer.prompt("event_date (YYYY-MM-DD)")
        default_name = f"VALIDA {valida_num} {location}"

    season = typer.prompt("season", default="2026", type=int)
    name = typer.prompt("event name", default=default_name)
    climate = typer.prompt("climate", default="soleado")
    temp_raw = typer.prompt("temperature_c (vacío para omitir)", default="")
    altitude = typer.prompt("altitude_msnm (vacío para omitir)", default="")
    weather_notes = typer.prompt("weather_notes (vacío para omitir)", default="")

    valid_surfaces = [s.value for s in SurfaceCondition]
    surface_str = typer.prompt(
        f"surface_condition {valid_surfaces} (vacío para omitir)", default=""
    )

    temp_val: Optional[Decimal] = None
    if temp_raw.strip():
        try:
            temp_val = Decimal(temp_raw.strip())
        except InvalidOperation:
            console.print("[yellow]temperature_c inválida, se omite.[/]")

    altitude_val: Optional[int] = None
    if altitude.strip():
        try:
            altitude_val = int(altitude.strip())
        except ValueError:
            console.print("[yellow]altitude_msnm inválida, se omite.[/]")

    surface_val: Optional[SurfaceCondition] = None
    if surface_str.strip():
        try:
            surface_val = SurfaceCondition(surface_str.strip())
        except ValueError:
            console.print(
                f"[yellow]surface_condition inválida ({surface_str!r}), se omite.[/]"
            )

    return EventMeta(
        season=int(season),
        copa_code="copa_valle",
        valida_num=int(valida_num),
        name=name,
        event_date=date.fromisoformat(event_date_str),
        location=location,
        climate=climate or None,
        temperature_c=temp_val,
        surface_condition=surface_val,
        altitude_msnm=altitude_val,
        weather_notes=(weather_notes or None),
        pdf_results_filename=results_path.name,
        pdf_general_filename=(general_path.name if general_path else None),
    )


# ---------------------------------------------------------------------------
# Helpers de match decisions
# ---------------------------------------------------------------------------


def _decisions_from_yaml(data: Any) -> dict[str, Optional[int]]:
    """Convierte YAML lista a dict ``{bib_str: athlete_id|None}``.

    Acepta:
    - ``[]`` o ``None`` → ``{}`` (sin decisiones — todos los TyR quedarán
      como pendientes de match).
    - Lista de dicts ``[{bib: "553", athlete_id: 12}, ...]``.
    - Si ``athlete_id`` es ``null`` o falta, se interpreta como "skip"
      (queda en None en el dict — el ingestor lo trata como no-link).
    """
    if not data:
        return {}
    if not isinstance(data, list):
        raise typer.BadParameter(
            f"match-decisions debe ser lista YAML; recibido: {type(data).__name__}"
        )
    out: dict[str, Optional[int]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            raise typer.BadParameter(
                f"Entrada inválida en match-decisions: {entry!r} (debe ser dict)"
            )
        bib = entry.get("bib")
        if bib is None:
            raise typer.BadParameter(f"Entrada sin bib: {entry!r}")
        aid = entry.get("athlete_id")
        out[str(bib)] = int(aid) if aid is not None else None
    return out


async def _collect_match_decisions_interactive(
    db: AsyncSession, parsed_results: dict[str, list[ResultsRow]]
) -> dict[str, Optional[int]]:
    """Para cada competidor TyR, muestra top-3 athletes y pide decisión.

    Carga TODOS los athletes una vez (n es pequeño en el club: ~16). Para
    cada TyR del PDF, invoca ``match_athletes`` y prompt típico:

        [1] Thiago Duque (12.4 años) score=95.0  reason=name+age_compat
        [2] ...
        > 1/2/3/s(kip)/n(ew):

    Retorna ``{bib: athlete_id|None}``. ``None`` significa "skip" o "new"
    — el ingestor no creará link.
    """
    decisions: dict[str, Optional[int]] = {}

    # Cargar athletes activos. No filtramos por club_id porque el CLI no
    # sabe a qué club apunta — asumimos un club único (Trocha y Ruta). Si
    # en el futuro hay multi-club, agregar filtro.
    athletes_result = await db.execute(select(Athlete))
    athletes = list(athletes_result.scalars().all())

    # Iterar TyR del PDF
    for code, rows in parsed_results.items():
        for row in rows:
            if not is_trocha_y_ruta(row.club):
                continue

            candidates = match_athletes(
                competitor_name=row.name,
                competitor_club=row.club,
                competitor_category=None,  # podríamos pasar la cat. real
                athletes=athletes,
            )

            console.print(
                f"\n[bold]TyR bib={row.bib} cat={code}[/] | PDF: [italic]{row.name}[/]"
            )
            if not candidates:
                console.print("  [yellow]Sin candidatos sobre threshold.[/]")
                decisions[str(row.bib)] = None
                continue

            for i, c in enumerate(candidates, start=1):
                age_str = f"{c.age_decimal} años" if c.age_decimal is not None else "edad?"
                console.print(
                    f"  [bold]{i}[/] {c.full_name}  score={c.score:.1f}  "
                    f"{age_str}  reason={c.reason}"
                )

            choice = typer.prompt("Elige 1/2/3/s(kip)/n(ew)", default="s").strip().lower()
            if choice in {"s", "skip"}:
                decisions[str(row.bib)] = None
            elif choice in {"n", "new"}:
                decisions[str(row.bib)] = None
            elif choice in {"1", "2", "3"}:
                idx = int(choice) - 1
                if idx < len(candidates):
                    decisions[str(row.bib)] = candidates[idx].athlete_id
                else:
                    console.print("[yellow]Índice fuera de rango — skip.[/]")
                    decisions[str(row.bib)] = None
            else:
                console.print(f"[yellow]Respuesta no reconocida ({choice!r}) — skip.[/]")
                decisions[str(row.bib)] = None

    return decisions


# ---------------------------------------------------------------------------
# Comparativa con válida anterior (best-effort)
# ---------------------------------------------------------------------------


async def _print_previous_valida_comparison(meta: EventMeta, report: IngestReport) -> None:
    """Imprime mini-tabla de TyR comparando V-N contra V-(N-1) si existe.

    Best-effort: si no hay analytics, no hay athletes vinculados, o no hay
    válida previa en la misma serie, se imprime una nota informativa y se
    sigue. No bloquea el éxito del ingest.
    """
    if meta.valida_num <= 1 or meta.valida_num == 99:
        return  # CD o primera válida — sin previa
    from app.models.race_event import RaceEvent

    async with _open_session() as db:
        prev_q = await db.execute(
            select(RaceEvent).where(
                RaceEvent.series_id == report.series_id,
                RaceEvent.sequence_number == meta.valida_num - 1,
            )
        )
        prev = prev_q.scalar_one_or_none()
        if prev is None:
            console.print(
                f"[dim]Sin válida anterior (V-{meta.valida_num - 1}) — no hay comparativa.[/]"
            )
            return

    console.print(
        f"[dim]Comparativa V-{meta.valida_num} vs V-{meta.valida_num - 1}: "
        "delegado a `analyze evolution` (Paso 5 pendiente).[/]"
    )


# ---------------------------------------------------------------------------
# analyze — wrappers sobre Paso 5 (best-effort: stub si falta)
# ---------------------------------------------------------------------------


def _require_analytics():
    """Importa ``app.services.race.analytics`` o sale con código 2 si falta.

    El Paso 5 (analytics) puede no estar completo al usar este CLI. En vez
    de fallar con ``ImportError``, mostramos un mensaje accionable.
    """
    try:
        from app.services.race import analytics  # type: ignore
    except ImportError as exc:
        console.print(
            "[red]Módulo `app.services.race.analytics` no disponible.[/] "
            "Este subcomando depende del Paso 5 (analytics) del workflow.\n"
            f"  Detalle: {exc}\n"
            "  → Implementar `analytics.py` con `athlete_progression`, "
            "`podium_gap`, `club_ranking`, `projection`."
        )
        raise typer.Exit(code=2)
    return analytics


@analyze_app.command("evolution")
def analyze_evolution(
    competitor_name: Optional[str] = typer.Option(
        None, "--competitor-name", help="Nombre completo del competidor (LIKE normalizado)."
    ),
    competitor_id: Optional[int] = typer.Option(
        None, "--competitor-id", help="ID directo (alternativa a --competitor-name)."
    ),
    show_names: bool = typer.Option(
        False, "--show-names", help="Mostrar nombres completos (default: enmascarados)."
    ),
) -> None:
    """Evolución longitudinal de un competidor a lo largo de las válidas."""
    if competitor_name is None and competitor_id is None:
        console.print("[red]Requiere --competitor-name o --competitor-id[/]")
        raise typer.Exit(code=2)
    analytics = _require_analytics()
    asyncio.run(
        _analyze_evolution_impl(
            analytics=analytics,
            competitor_name=competitor_name,
            competitor_id=competitor_id,
            show_names=show_names,
        )
    )


async def _analyze_evolution_impl(
    *, analytics, competitor_name, competitor_id, show_names
) -> None:
    async with _open_session() as db:
        if competitor_id is None:
            competitor_id = await _resolve_competitor_by_name(db, competitor_name)
            if competitor_id is None:
                console.print(
                    f"[red]Competidor no encontrado:[/] {_present_name(competitor_name, show=show_names)}"
                )
                raise typer.Exit(code=1)
        df = await analytics.athlete_progression(db, competitor_id)

    if df is None or (hasattr(df, "empty") and df.empty):
        console.print("[yellow]Sin resultados para este competidor.[/]")
        return

    headers = list(df.columns)
    rows = [tuple(row) for row in df.itertuples(index=False, name=None)]
    _print_table(
        f"Evolución competitor_id={competitor_id}", headers, rows
    )


@analyze_app.command("gap")
def analyze_gap(
    category_code: str = typer.Option(..., "--category-code"),
    season: int = typer.Option(..., "--season"),
) -> None:
    """Gap al podio (P1/P3) por válida para corredores TyR de la categoría."""
    analytics = _require_analytics()
    asyncio.run(_analyze_gap_impl(analytics, category_code, season))


async def _analyze_gap_impl(analytics, category_code: str, season: int) -> None:
    from app.models.race_category import RaceCategory

    async with _open_session() as db:
        cat_q = await db.execute(
            select(RaceCategory).where(RaceCategory.code == category_code)
        )
        cat = cat_q.scalar_one_or_none()
        if cat is None:
            console.print(f"[red]Categoría no encontrada:[/] {category_code}")
            raise typer.Exit(code=1)
        df = await analytics.podium_gap(db, cat.id, season)

    if df is None or (hasattr(df, "empty") and df.empty):
        console.print(
            f"[yellow]Sin TyR en categoría {category_code} temporada {season}.[/]"
        )
        return

    headers = list(df.columns)
    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
    _print_table(f"Gap podio {category_code} {season}", headers, rows)


@analyze_app.command("ranking")
def analyze_ranking(
    season: int = typer.Option(..., "--season"),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Archivo .md de salida (opcional)."
    ),
) -> None:
    """Ranking del club por categoría + totales temporada."""
    analytics = _require_analytics()
    asyncio.run(_analyze_ranking_impl(analytics, season, output))


async def _analyze_ranking_impl(
    analytics, season: int, output: Optional[Path]
) -> None:
    async with _open_session() as db:
        data = await analytics.club_ranking(db, season)

    if not data:
        console.print(f"[yellow]Sin datos de club temporada {season}.[/]")
        return

    by_cat = data.get("by_category", [])
    if by_cat:
        rows = [
            (
                entry.get("category_code"),
                entry.get("active_riders", 0),
                entry.get("podiums", 0),
                entry.get("wins", 0),
                entry.get("total_points", 0),
            )
            for entry in by_cat
        ]
        _print_table(
            f"Ranking club {season} por categoría",
            ["categoría", "activos", "podios", "wins", "puntos"],
            rows,
        )

    summary = [
        ("total_points", data.get("total_points", 0)),
        ("total_podiums", data.get("total_podiums", 0)),
        ("total_wins", data.get("total_wins", 0)),
        ("active_riders", data.get("active_riders", 0)),
    ]
    _print_table(f"Totales temporada {season}", ["métrica", "valor"], summary)

    if output is not None:
        _write_ranking_markdown(output, season, data)
        console.print(f"[green]Reporte escrito en[/] {output}")


def _write_ranking_markdown(path: Path, season: int, data: dict) -> None:
    """Vuelca el ranking como markdown determinístico (sin emojis)."""
    lines = [
        f"# Ranking Club Trocha y Ruta — Temporada {season}",
        "",
        "## Por categoría",
        "",
        "| Categoría | Activos | Podios | Wins | Puntos |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for entry in data.get("by_category", []):
        lines.append(
            f"| {entry.get('category_code', '?')} "
            f"| {entry.get('active_riders', 0)} "
            f"| {entry.get('podiums', 0)} "
            f"| {entry.get('wins', 0)} "
            f"| {entry.get('total_points', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Totales",
            "",
            f"- Puntos totales: **{data.get('total_points', 0)}**",
            f"- Podios totales: **{data.get('total_podiums', 0)}**",
            f"- Wins totales: **{data.get('total_wins', 0)}**",
            f"- Riders activos: **{data.get('active_riders', 0)}**",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


@analyze_app.command("projection")
def analyze_projection(
    competitor_name: Optional[str] = typer.Option(None, "--competitor-name"),
    competitor_id: Optional[int] = typer.Option(None, "--competitor-id"),
    next_valida: int = typer.Option(..., "--next-valida"),
) -> None:
    """Proyección para la próxima válida (regresión lineal sobre históricos).

    Warning explícito si ``confidence='low'`` (n<5).
    """
    if competitor_name is None and competitor_id is None:
        console.print("[red]Requiere --competitor-name o --competitor-id[/]")
        raise typer.Exit(code=2)
    analytics = _require_analytics()
    asyncio.run(
        _analyze_projection_impl(
            analytics, competitor_name, competitor_id, next_valida
        )
    )


async def _analyze_projection_impl(
    analytics,
    competitor_name: Optional[str],
    competitor_id: Optional[int],
    next_valida: int,
) -> None:
    async with _open_session() as db:
        if competitor_id is None:
            competitor_id = await _resolve_competitor_by_name(db, competitor_name)
            if competitor_id is None:
                console.print("[red]Competidor no encontrado.[/]")
                raise typer.Exit(code=1)

        # Resolver next_event_id desde serie activa + next_valida
        next_event_id = await _resolve_next_event_id(db, next_valida)
        if next_event_id is None:
            console.print(
                f"[red]No hay evento V-{next_valida} en la serie activa.[/]"
            )
            raise typer.Exit(code=1)

        result = await analytics.projection(db, competitor_id, next_event_id)

    panel = Panel(
        f"competitor_id: {result.get('competitor_id', competitor_id)}\n"
        f"expected_position: {result.get('expected_position', '?')}\n"
        f"expected_position_range: {result.get('expected_position_range', '?')}\n"
        f"expected_time_seconds: {result.get('expected_time_seconds', '—')}\n"
        f"n_samples: {result.get('n_samples', '?')}\n"
        f"[bold]confidence: {result.get('confidence', '?')}[/]",
        title=f"Proyección V-{next_valida}",
        border_style="green"
        if result.get("confidence") in {"medium", "high"}
        else "yellow",
    )
    console.print(panel)
    if result.get("confidence") == "low":
        console.print(
            "[yellow]Warning:[/] proyección con n<5 — interpretarla como "
            "tendencia tentativa, no como pronóstico cerrado."
        )


async def _resolve_competitor_by_name(
    db: AsyncSession, competitor_name: Optional[str]
) -> Optional[int]:
    """Resuelve ``competitor_id`` desde un fragmento de nombre.

    Usa LIKE sobre ``normalized_name`` con el nombre normalizado. Si hay
    múltiples matches, retorna ``None`` y avisa por consola (el coach debe
    desambiguar con ``--competitor-id``).
    """
    if not competitor_name:
        return None
    from app.services.race.normalizer import normalize_name

    needle = normalize_name(competitor_name)
    q = await db.execute(
        select(RaceCompetitor).where(
            RaceCompetitor.normalized_name.like(f"%{needle}%")
        )
    )
    rows = list(q.scalars().all())
    if not rows:
        return None
    if len(rows) > 1:
        console.print(
            f"[yellow]Múltiples competidores matchean[/] {needle!r}:"
        )
        for r in rows:
            console.print(f"  • id={r.id}  {_mask_name(r.display_name)}")
        return None
    return rows[0].id


async def _resolve_next_event_id(db: AsyncSession, next_valida: int) -> Optional[int]:
    """Busca el evento con ``sequence_number=next_valida`` en la serie activa.

    Heurística simple: serie con mayor ``season_year`` y nombre Copa Valle.
    """
    from app.models.race_event import RaceEvent

    series_q = await db.execute(
        select(RaceSeries).order_by(RaceSeries.season_year.desc()).limit(1)
    )
    series = series_q.scalar_one_or_none()
    if series is None:
        return None
    evt_q = await db.execute(
        select(RaceEvent).where(
            RaceEvent.series_id == series.id,
            RaceEvent.sequence_number == next_valida,
        )
    )
    evt = evt_q.scalar_one_or_none()
    return evt.id if evt else None


# ---------------------------------------------------------------------------
# riders — listado y vinculación manual
# ---------------------------------------------------------------------------


@riders_app.command("list")
def riders_list(
    tyr_only: bool = typer.Option(
        False, "--tyr-only", help="Sólo competidores cuyo club fuzzy es TyR."
    ),
    unmatched: bool = typer.Option(
        False, "--unmatched", help="Sólo competidores TyR sin athlete_id."
    ),
    show_names: bool = typer.Option(
        False,
        "--show-names",
        help="Mostrar nombre completo (default: enmascarado T. Apellido).",
    ),
    limit: int = typer.Option(50, "--limit", help="Tope de filas a mostrar."),
) -> None:
    """Lista competidores. Default conservador con nombres (privacy)."""
    asyncio.run(_riders_list_impl(tyr_only, unmatched, show_names, limit))


async def _riders_list_impl(
    tyr_only: bool, unmatched: bool, show_names: bool, limit: int
) -> None:
    async with _open_session() as db:
        # Cargamos todos y filtramos en Python (n manageable en V-IV ≈ 200).
        # Esto evita persistir el flag is_trocha_y_ruta como columna (decisión
        # design.md §3.3 + edge-cases §1: derivar on-demand).
        q = await db.execute(select(RaceCompetitor).order_by(RaceCompetitor.id))
        comps = list(q.scalars().all())

    # Filtros
    if tyr_only or unmatched:
        comps = [c for c in comps if is_trocha_y_ruta(c.club_text or "")]
    if unmatched:
        comps = [c for c in comps if c.athlete_id is None]

    comps = comps[:limit]

    if not comps:
        console.print("[yellow]Sin competidores que coincidan con el filtro.[/]")
        return

    # Última válida en la que participó (para contexto)
    rows = []
    for c in comps:
        rows.append(
            (
                c.id,
                _present_name(c.display_name, show=show_names),
                (c.club_text or "—")[:30],
                c.athlete_id if c.athlete_id is not None else "—",
                c.sex.value if c.sex else "—",
            )
        )

    title = "Competidores"
    if tyr_only:
        title += " · TyR only"
    if unmatched:
        title += " · unmatched"

    _print_table(
        title,
        ["id", "nombre", "club", "athlete_id", "sex"],
        rows,
        caption=f"Total: {len(comps)} (límite {limit}) — "
        f"{'nombres completos' if show_names else 'nombres enmascarados'}",
    )


@riders_app.command("link")
def riders_link(
    competitor_id: int = typer.Option(..., "--competitor-id"),
    athlete_id: int = typer.Option(..., "--athlete-id"),
    force: bool = typer.Option(False, "--force", help="Saltar confirmación."),
) -> None:
    """Vincula manualmente ``competitor.athlete_id``. Requiere confirmación."""
    asyncio.run(_riders_link_impl(competitor_id, athlete_id, force))


async def _riders_link_impl(competitor_id: int, athlete_id: int, force: bool) -> None:
    from datetime import datetime, timezone

    async with _open_session() as db:
        comp_q = await db.execute(
            select(RaceCompetitor).where(RaceCompetitor.id == competitor_id)
        )
        comp = comp_q.scalar_one_or_none()
        if comp is None:
            console.print(f"[red]Competidor id={competitor_id} no encontrado.[/]")
            raise typer.Exit(code=1)

        ath_q = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
        ath = ath_q.scalar_one_or_none()
        if ath is None:
            console.print(f"[red]Athlete id={athlete_id} no encontrado.[/]")
            raise typer.Exit(code=1)

        console.print(
            f"[bold]Vincular:[/] competitor #{comp.id} "
            f"({_mask_name(comp.display_name)}) → athlete #{ath.id} "
            f"({_mask_name(f'{ath.first_name} {ath.last_name}')})"
        )
        if comp.athlete_id is not None and comp.athlete_id != athlete_id:
            console.print(
                f"[yellow]Aviso:[/] competitor ya estaba linkeado a athlete_id={comp.athlete_id}"
            )

        if not force:
            ok = typer.confirm("Confirmar?", default=False)
            if not ok:
                console.print("[yellow]Cancelado.[/]")
                raise typer.Exit(code=0)

        comp.athlete_id = athlete_id
        comp.linked_at = datetime.now(timezone.utc)
        # Hubiera sido ideal capturar quién hace el link, pero el CLI no
        # tiene auth — usamos el system user.
        sys_uid = await _get_or_create_system_user(db)
        comp.linked_by_user_id = sys_uid

        # Backfill: actualizar race_results del competitor con athlete_id
        await db.execute(
            __import__(
                "sqlalchemy", fromlist=["update"]
            ).update(RaceResult)
            .where(RaceResult.competitor_id == competitor_id)
            .values(athlete_id=athlete_id)
        )
        await db.commit()

    console.print("[green]Link aplicado y race_results actualizados.[/]")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    sys.exit(app() or 0)
