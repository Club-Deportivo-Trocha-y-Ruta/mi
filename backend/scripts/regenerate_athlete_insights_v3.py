"""Regenera los insights v3 de un atleta contra la API local y reporta calidad.

Verificación SC-1 de la feature 037 (specs/037-ai-insights-v3-causal/spec.md):
lanza un run por cada carrera de la temporada del atleta (o las que se pasen
con ``--event-id``), espera el resultado y reporta métricas agregadas de
calidad **sin nombres ni datos identificables**: hallazgo, tendencia,
confianza, observaciones con evidencia, acciones con catálogo, pregunta al
coach, vacíos de datos, veredicto del crítico y costo.

Uso (con el backend local corriendo en :8000 y la clave RACE_AI configurada
en su .env — este script NO lee ni imprime secretos)::

    source .venv/bin/activate
    python scripts/regenerate_athlete_insights_v3.py --athlete-id 2 --season 2026
    python scripts/regenerate_athlete_insights_v3.py --athlete-id 2 --season 2026 --season-summary
    python scripts/regenerate_athlete_insights_v3.py --athlete-id 2 --season 2026 --event-id 26

El token se firma localmente con ``create_access_token`` (mismo secreto JWT
del backend) para el usuario coach indicado. Los runs bloqueados por el
crítico (``hitl_waiting``) NO se aprueban automáticamente: quedan pendientes
para que el coach los revise en la pestaña Insights IA.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

import httpx

from app.services.auth import create_access_token

POLL_SECONDS = 3.0
TERMINAL_STATES = {"done", "failed", "cancelled"}


def _token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id)})


async def _list_races(client: httpx.AsyncClient, athlete_id: int, season: int) -> list[dict]:
    r = await client.get(
        f"/api/athletes/{athlete_id}/race-analysis/races", params={"season": season}
    )
    r.raise_for_status()
    return r.json().get("items", [])


async def _start_run(
    client: httpx.AsyncClient, athlete_id: int, season: int, race: dict
) -> str:
    body = {
        "season": season,
        "event_id": race["event_id"],
        "valida_nums": [race["sequence_number"]],
        "explain_mode": False,
    }
    r = await client.post(f"/api/athletes/{athlete_id}/race-analysis/runs", json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"start_run {r.status_code}: {r.text[:200]}")
    return r.json()["run_id"]


async def _start_season(client: httpx.AsyncClient, athlete_id: int, season: int) -> str:
    r = await client.post(
        f"/api/athletes/{athlete_id}/race-analysis/season-summary",
        json={"season": season, "explain_mode": False},
    )
    if r.status_code >= 400:
        raise RuntimeError(f"season_summary {r.status_code}: {r.text[:200]}")
    return r.json()["run_id"]


async def _wait(client: httpx.AsyncClient, run_id: str, timeout_s: float) -> dict:
    """Pollea el estado hasta terminal o hitl_waiting. Devuelve el último status."""
    started = time.monotonic()
    last_seq = 0
    events: list[dict] = []
    while True:
        r = await client.get(
            f"/api/race-analysis/runs/{run_id}/status", params={"since": last_seq}
        )
        if r.status_code == 404 and time.monotonic() - started < 30:
            # La fila agent_runs puede tardar en ser visible tras el 202.
            await asyncio.sleep(POLL_SECONDS)
            continue
        r.raise_for_status()
        st = r.json()
        events.extend(st.get("new_events") or [])
        last_seq = st.get("last_seq", last_seq)
        if st["state"] in TERMINAL_STATES or st["state"] == "hitl_waiting":
            st["_events"] = events
            st["_elapsed_s"] = round(time.monotonic() - started, 1)
            return st
        if time.monotonic() - started > timeout_s:
            st["_events"] = events
            st["_elapsed_s"] = round(time.monotonic() - started, 1)
            st["state"] = "timeout"
            return st
        await asyncio.sleep(POLL_SECONDS)


async def _latest_insight_detail(
    client: httpx.AsyncClient, athlete_id: int, season: int, valida_num: int | None,
    event_id: int | None,
) -> dict | None:
    r = await client.get(
        f"/api/athletes/{athlete_id}/race-analysis/insights",
        params={"season": season, "limit": 50},
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    cands = [
        i for i in items
        if (event_id is not None and i.get("event_id") == event_id)
        or (event_id is None and i.get("valida_num") == valida_num)
    ]
    if not cands:
        return None
    cands.sort(key=lambda i: i.get("generated_at") or "", reverse=True)
    d = await client.get(
        f"/api/athletes/{athlete_id}/race-analysis/insights/{cands[0]['id']}"
    )
    d.raise_for_status()
    return d.json()


def _quality_row(label: str, status: dict, detail: dict | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "race": label,
        "run_state": status.get("state"),
        "elapsed_s": status.get("_elapsed_s"),
    }
    if detail is None:
        row["insight"] = None
        return row
    s = detail.get("structured") or {}
    snap = detail.get("metrics_snapshot") or {}
    verdict = snap.get("critic_verdict") or {}
    agg = snap.get("aggregate") or {}
    actions = s.get("actions") or []
    obs = s.get("observations") or []
    row.update(
        {
            "confidence": detail.get("confidence"),
            "is_fallback": detail.get("is_fallback"),
            "headline": s.get("headline"),
            "trend": s.get("trend"),
            "field_reading": (s.get("field_reading") or {}).get("summary"),
            "n_observations": len(obs),
            "evidence_items": sum(len(o.get("evidence") or []) for o in obs),
            "domains": sorted({o.get("domain") for o in obs if o.get("domain")}),
            "n_actions": len(actions),
            "actions_with_catalog": sum(1 for a in actions if a.get("catalog_ref")),
            "coach_question": s.get("coach_question"),
            "data_gaps": s.get("data_gaps") or [],
            "critic_must_block": verdict.get("must_block"),
            "critic_issues": len(verdict.get("issues") or []),
            "tokens_in": agg.get("tokens_in_total"),
            "tokens_out": agg.get("tokens_out_total"),
            "cost_usd": agg.get("cost_usd_total"),
        }
    )
    return row


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--athlete-id", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--coach-user-id", type=int, default=2)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--event-id", type=int, action="append", default=None)
    ap.add_argument("--season-summary", action="store_true")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--json", action="store_true", help="salida JSON en vez de tabla")
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {_token(args.coach_user_id)}"}
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=args.base_url, headers=headers, timeout=60) as client:
        races = await _list_races(client, args.athlete_id, args.season)
        if args.event_id:
            races = [r for r in races if r["event_id"] in set(args.event_id)]
        print(f"carreras a analizar: {len(races)}", file=sys.stderr)
        for race in races:
            label = race.get("label") or f"event {race['event_id']}"
            print(f"→ {label} …", file=sys.stderr)
            try:
                run_id = await _start_run(client, args.athlete_id, args.season, race)
            except RuntimeError as exc:
                rows.append({"race": label, "run_state": "not_started", "error": str(exc)})
                continue
            try:
                status = await _wait(client, run_id, args.timeout)
                detail = None
                if status["state"] == "done":
                    detail = await _latest_insight_detail(
                        client, args.athlete_id, args.season, race["sequence_number"],
                        race["event_id"],
                    )
                row = _quality_row(label, status, detail)
            except Exception as exc:  # noqa: BLE001 - seguir con las demás carreras
                row = {"race": label, "run_state": "error", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            row["run_id"] = run_id
            rows.append(row)
        if args.season_summary:
            print("→ resumen de temporada …", file=sys.stderr)
            try:
                run_id = await _start_season(client, args.athlete_id, args.season)
                status = await _wait(client, run_id, args.timeout)
                detail = None
                if status["state"] == "done":
                    detail = await _latest_insight_detail(
                        client, args.athlete_id, args.season, 0, None
                    )
                row = _quality_row("Resumen de temporada", status, detail)
                row["run_id"] = run_id
                rows.append(row)
            except RuntimeError as exc:
                rows.append({"race": "Resumen de temporada", "run_state": "not_started", "error": str(exc)})

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    for r in rows:
        print("=" * 78)
        print(f"{r['race']}  ·  run={r.get('run_state')}  ·  {r.get('elapsed_s')} s")
        if r.get("error"):
            print(f"  error: {r['error']}")
            continue
        if r.get("insight") is None and "headline" not in r:
            print("  (sin insight persistido)")
            continue
        print(f"  confianza={r['confidence']}  fallback={r['is_fallback']}  tendencia={r['trend']}")
        print(f"  HALLAZGO: {r['headline']}")
        if r.get("field_reading"):
            print(f"  pelotón: {r['field_reading']}")
        print(
            f"  observaciones={r['n_observations']} (evidencias={r['evidence_items']}, dominios={','.join(r['domains'])})"
            f"  acciones={r['n_actions']} (con catálogo={r['actions_with_catalog']})"
        )
        print(f"  pregunta: {r['coach_question']}")
        if r["data_gaps"]:
            print(f"  vacíos: {r['data_gaps']}")
        print(
            f"  crítico: must_block={r['critic_must_block']} issues={r['critic_issues']}"
            f"  ·  tokens={r['tokens_in']}/{r['tokens_out']}  costo=${r['cost_usd']}"
        )
    distinct = len({r.get("headline") for r in rows if r.get("headline")})
    print("=" * 78)
    print(f"hallazgos distintos: {distinct}/{sum(1 for r in rows if r.get('headline'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
