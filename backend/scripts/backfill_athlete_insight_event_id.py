"""Backfill manual de ``athlete_ai_insights.event_id`` para filas legacy.

Contexto
========
La migración ``7a8b9c0d1e2f`` agregó ``athlete_ai_insights.event_id`` (NULL)
para anclar cada insight a la válida (``race_events.id``) concreta que
analiza. Es necesario desde feature 014 (cup vs championship): un mismo
``sequence_number`` (ej. válida 1) puede mapear a >1 evento en la misma
temporada cuando hay copa y campeonato corriendo en paralelo, y
``POST /athletes/{id}/race-analysis/runs`` responde 409 "Válida ambigua"
si no se puede resolver un único evento.

Las filas creadas antes de que el flujo anclara ``event_id`` (o sembradas
directamente en dev) quedaron con ``event_id IS NULL``. Cuando su
``valida_num`` es ambiguo en la temporada, el botón "Regenerar" del coach
falla con 409 porque el frontend ya no tiene forma de saber a qué evento
apunta el insight histórico.

Este script propone matches usando la única señal disponible para estas
filas legacy: el ``summary_text`` generado, que en el shape "Qué pasó en
esta válida" incluye posición y tiempo de carrera explícitos
(``"tiempo de 0:36:19"``, ``"posición 4"``). Comparamos esos valores contra
``race_results`` del mismo atleta en cada evento candidato (mismo season +
sequence_number ambiguo). Si exactamente un candidato coincide en posición
Y tiempo → confianza alta. Si solo coincide en posición (tiempo no
parseable) → confianza media. Filas sin match unívoco (shape "Evolución",
sin cifras concretas para ESA válida, o candidatos empatados) quedan sin
resolver y se reportan explícitamente — nunca se adivina.

NO modifica la DB salvo que se pase ``--apply``, y aún así pide
confirmación interactiva por cada match (salvo ``--auto-high``).

Uso
===

    # Dry-run (default): imprime tabla con propuestas + nivel de confianza.
    python -m backend.scripts.backfill_athlete_insight_event_id

    # Aplicar (interactivo, pide y/n por cada match).
    python -m backend.scripts.backfill_athlete_insight_event_id --apply

    # Aplicar solo matches de alta confianza, sin prompts.
    python -m backend.scripts.backfill_athlete_insight_event_id --apply --auto-high

Salida
======
Tabla CSV-friendly con:
``insight_id, athlete_id, season, valida_num, candidate_event_ids,
matched_event_id, confidence, would_apply``

Y al final la lista de insights que quedaron sin resolver (con el motivo).
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass, field
from typing import Literal

Confidence = Literal["high", "medium"]

# Solo se extrae de la sección "Qué pasó en esta válida" — el único shape de
# summary_text que reporta el resultado de ESA válida puntual. El shape
# "Evolución" menciona posiciones/tiempos de otras válidas o promedios en el
# cuerpo del texto; extraer de ahí produciría falsos matches.
_SECTION_RE = re.compile(
    r"qu[eé] pas[oó] en esta v[aá]lida\s*\n+(.*?)(?:\n##|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_TIME_COLON_RE = re.compile(r"tiempo de(?: carrera)? (\d{1,2}):(\d{2}):(\d{2})")
_TIME_MS_RE = re.compile(r"tiempo de(?: carrera)? de (\d+) ms")
_POSITION_RE = re.compile(r"posici[oó]n (\d{1,2})\b")

# El prompt v2 redacta la posición en palabras ("La deportista finalizó cuarta
# en la primera válida"). El ancla es el VERBO: sin ella, "la primera válida"
# de esa misma frase se leería como posición 1.
_ORDINAL_WORDS: dict[str, int] = {
    "primer": 1, "primero": 1, "primera": 1,
    "segundo": 2, "segunda": 2,
    "tercer": 3, "tercero": 3, "tercera": 3,
    "cuarto": 4, "cuarta": 4,
    "quinto": 5, "quinta": 5,
    "sexto": 6, "sexta": 6,
    "séptimo": 7, "séptima": 7, "septimo": 7, "septima": 7,
    "octavo": 8, "octava": 8,
    "noveno": 9, "novena": 9,
    "décimo": 10, "décima": 10, "decimo": 10, "decima": 10,
}
_POSITION_WORD_RE = re.compile(
    r"finaliz(?:ó|o|ando)?\s+(?:en\s+(?:el|la)\s+)?(" + "|".join(_ORDINAL_WORDS) + r")\b",
    re.IGNORECASE,
)

# Tolerancia por redondeo detectado en los datos seed (ej. summary dice
# "0:50:05" pero race_time_ms real es 3004000 = 0:50:04).
_TIME_TOLERANCE_MS = 1000


def _valida_section(text: str) -> str | None:
    m = _SECTION_RE.search(text)
    return m.group(1) if m else None


def _parse_time_ms(section: str) -> int | None:
    m = _TIME_COLON_RE.search(section)
    if m:
        h, mm, ss = (int(x) for x in m.groups())
        return ((h * 60 + mm) * 60 + ss) * 1000
    m = _TIME_MS_RE.search(section)
    if m:
        return int(m.group(1))
    return None


def _parse_position_word(section: str) -> int | None:
    m = _POSITION_WORD_RE.search(section)
    return _ORDINAL_WORDS.get(m.group(1).lower()) if m else None


def _parse_position(section: str) -> int | None:
    m = _POSITION_RE.search(section)
    return int(m.group(1)) if m else None


@dataclass(frozen=True)
class MatchProposal:
    insight_id: int
    athlete_id: int
    season: int
    valida_num: int
    candidate_event_ids: list[int]
    matched_event_id: int
    confidence: Confidence


@dataclass(frozen=True)
class Unresolved:
    insight_id: int
    athlete_id: int
    season: int
    valida_num: int
    candidate_event_ids: list[int]
    reason: str


@dataclass
class Result:
    proposals: list[MatchProposal] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)


async def _propose_matches() -> Result:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.athlete_ai_insight import AthleteAiInsight
    from app.models.race_event import RaceEvent
    from app.models.race_result import RaceResult
    from app.models.race_series import RaceSeries

    result = Result()
    async with AsyncSessionLocal() as session:
        # Se seleccionan COLUMNAS, no la entidad completa: cargar el modelo
        # obliga a un SELECT de todas sus columnas, y este script tiene que
        # poder correr contra un entorno con migraciones pendientes (en
        # producción faltaba `is_fallback` y el script reventaba con un 1054
        # aunque no usa ese campo para nada). Pedir lo mínimo lo vuelve
        # inmune a esa deriva de esquema.
        insights_q = await session.execute(
            select(
                AthleteAiInsight.id,
                AthleteAiInsight.athlete_id,
                AthleteAiInsight.season,
                AthleteAiInsight.valida_num,
                AthleteAiInsight.summary_text,
            ).where(
                AthleteAiInsight.event_id.is_(None),
                AthleteAiInsight.valida_num.is_not(None),
                AthleteAiInsight.valida_num > 0,
            )
        )
        insights = list(insights_q.all())
        if not insights:
            return result

        # (season, sequence_number) -> [event_id, ...] ambiguos (>1 evento).
        events_q = await session.execute(
            select(RaceEvent.id, RaceEvent.sequence_number, RaceSeries.season_year).join(
                RaceSeries, RaceSeries.id == RaceEvent.series_id
            )
        )
        by_season_seq: dict[tuple[int, int], list[int]] = {}
        for event_id, seq, season_year in events_q.all():
            by_season_seq.setdefault((int(season_year), int(seq)), []).append(int(event_id))
        ambiguous = {k: v for k, v in by_season_seq.items() if len(v) > 1}

        for insight in insights:
            key = (insight.season, insight.valida_num)
            candidates = ambiguous.get(key)
            if not candidates:
                continue  # no ambiguo -> el flujo normal ya lo resuelve solo.

            section = _valida_section(insight.summary_text or "")
            if section is None:
                result.unresolved.append(
                    Unresolved(
                        insight.id,
                        insight.athlete_id,
                        insight.season,
                        insight.valida_num,
                        candidates,
                        "summary_text sin sección 'Qué pasó en esta válida' (shape 'Evolución')",
                    )
                )
                continue

            parsed_time_ms = _parse_time_ms(section)
            parsed_position = _parse_position(section) or _parse_position_word(section)
            if parsed_position is None:
                result.unresolved.append(
                    Unresolved(
                        insight.id,
                        insight.athlete_id,
                        insight.season,
                        insight.valida_num,
                        candidates,
                        "sección encontrada pero sin posición parseable",
                    )
                )
                continue

            # Igual que arriba: sólo las tres columnas que se comparan.
            rr_q = await session.execute(
                select(
                    RaceResult.event_id,
                    RaceResult.position,
                    RaceResult.race_time_ms,
                ).where(
                    RaceResult.athlete_id == insight.athlete_id,
                    RaceResult.event_id.in_(candidates),
                    RaceResult.deleted_at.is_(None),
                )
            )
            candidate_results = list(rr_q.all())

            both_match = [
                rr.event_id
                for rr in candidate_results
                if rr.position == parsed_position
                and parsed_time_ms is not None
                and rr.race_time_ms is not None
                and abs(rr.race_time_ms - parsed_time_ms) <= _TIME_TOLERANCE_MS
            ]
            pos_only_match = [
                rr.event_id for rr in candidate_results if rr.position == parsed_position
            ]

            if len(both_match) == 1:
                result.proposals.append(
                    MatchProposal(
                        insight.id,
                        insight.athlete_id,
                        insight.season,
                        insight.valida_num,
                        candidates,
                        both_match[0],
                        "high",
                    )
                )
            elif len(pos_only_match) == 1:
                result.proposals.append(
                    MatchProposal(
                        insight.id,
                        insight.athlete_id,
                        insight.season,
                        insight.valida_num,
                        candidates,
                        pos_only_match[0],
                        "medium",
                    )
                )
            else:
                reason = (
                    "0 candidatos coinciden en posición+tiempo"
                    if not both_match and not pos_only_match
                    else "match ambiguo entre varios candidatos"
                )
                result.unresolved.append(
                    Unresolved(
                        insight.id,
                        insight.athlete_id,
                        insight.season,
                        insight.valida_num,
                        candidates,
                        reason,
                    )
                )

    return result


def _print_report(result: Result, *, apply: bool) -> None:
    print(
        "insight_id,athlete_id,season,valida_num,candidate_event_ids,"
        "matched_event_id,confidence,would_apply"
    )
    for p in result.proposals:
        print(
            f"{p.insight_id},{p.athlete_id},{p.season},{p.valida_num},"
            f"{p.candidate_event_ids},{p.matched_event_id},{p.confidence},{apply}"
        )

    if result.unresolved:
        print("\n# Sin resolver (requieren revisión manual):")
        print("insight_id,athlete_id,season,valida_num,candidate_event_ids,reason")
        for u in result.unresolved:
            print(
                f"{u.insight_id},{u.athlete_id},{u.season},{u.valida_num},"
                f"{u.candidate_event_ids},{u.reason!r}"
            )


async def _apply(proposals: list[MatchProposal], *, auto_high: bool) -> int:
    from sqlalchemy import update

    from app.database import AsyncSessionLocal
    from app.models.athlete_ai_insight import AthleteAiInsight

    applied = 0
    async with AsyncSessionLocal() as session:
        for p in proposals:
            ok = True
            if not (auto_high and p.confidence == "high"):
                ans = (
                    input(
                        f"Apply insight {p.insight_id} (atleta {p.athlete_id}, "
                        f"válida {p.valida_num}) -> event_id {p.matched_event_id} "
                        f"({p.confidence})? [y/N] "
                    )
                    .strip()
                    .lower()
                )
                ok = ans == "y"
            if not ok:
                continue
            # UPDATE dirigido en vez de cargar la entidad: el SELECT del ORM
            # traería todas las columnas del modelo y rompe contra un
            # esquema con migraciones pendientes (ver comentario en
            # `_propose_matches`). El WHERE conserva `event_id IS NULL` para
            # que la escritura sea idempotente y no pise un anclaje que otro
            # proceso haya resuelto entre el dry-run y el apply.
            res = await session.execute(
                update(AthleteAiInsight)
                .where(
                    AthleteAiInsight.id == p.insight_id,
                    AthleteAiInsight.event_id.is_(None),
                )
                .values(event_id=p.matched_event_id)
            )
            applied += int(res.rowcount or 0)
        await session.commit()
    return applied


async def _run(*, apply: bool, auto_high: bool) -> int:
    result = await _propose_matches()
    if not result.proposals and not result.unresolved:
        print("# No hay insights con valida_num ambiguo y event_id NULL.")
        return 0

    _print_report(result, apply=apply)

    if apply:
        applied = await _apply(result.proposals, auto_high=auto_high)
        print(f"\n# applied={applied}/{len(result.proposals)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Si se pasa, ejecuta los UPDATEs (interactivo).",
    )
    parser.add_argument(
        "--auto-high",
        action="store_true",
        help="Junto con --apply, aplica matches de confianza alta sin preguntar.",
    )
    args = parser.parse_args()

    return asyncio.run(_run(apply=args.apply, auto_high=args.auto_high))


if __name__ == "__main__":
    sys.exit(main())
