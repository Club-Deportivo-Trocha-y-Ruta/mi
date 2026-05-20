"""Smoke test end-to-end del módulo race-analyst v2 contra producción (F8A).

Flujo:
1. POST /api/race-analysis/runs con athlete_id real.
2. Polling /status cada 2s hasta done|failed|cancelled o timeout 5min.
3. GET /result — verifica AnalysisOutput parseable.
4. Verifica que en DB se haya insertado fila en athlete_ai_insights con
   cost_usd_total > 0 (vía endpoint admin /ai-usage).
5. Exit 0 si OK, exit 1 si falla.

Requiere:
- Token JWT válido (coach o admin) en --token o env RACE_SMOKE_TOKEN.
- Token admin separado en --admin-token o env RACE_SMOKE_ADMIN_TOKEN
  para chequear /ai-usage (si el primer token NO es admin).
- Base URL en --base-url o env RACE_SMOKE_BASE_URL.
- ``httpx`` y ``typer`` ya están en el venv del proyecto.

Uso:

    # Smoke contra producción (Render):
    export RACE_SMOKE_TOKEN=<jwt-coach>
    export RACE_SMOKE_ADMIN_TOKEN=<jwt-admin>
    python -m scripts.smoke_test_prod \\
        --base-url https://mi-2yzi.onrender.com \\
        --athlete-id 17 \\
        --season 2026

    # Smoke local (docker compose):
    python -m scripts.smoke_test_prod \\
        --base-url http://localhost:8000 \\
        --athlete-id 1 \\
        --season 2026 \\
        --skip-cost-check  # si la DB local no acumula gasto real

Salida (exit codes):
    0  smoke OK (run done + insight con cost > 0)
    1  fallo de red, timeout, validación o cost_usd == 0
    2  argumentos inválidos
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Optional

import httpx
import typer

app = typer.Typer(add_completion=False, help=__doc__)


POLL_INTERVAL_SECS = 2.0
DEFAULT_TIMEOUT_SECS = 300  # 5 min — runs en frío pueden tardar (Gemini + cold start Render).


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit(label: str, msg: str) -> None:
    """Output con prefijo timestamp para tracing en CI."""
    ts = time.strftime("%H:%M:%S")
    typer.echo(f"[{ts}] {label:7} {msg}")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _post_run(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    athlete_id: int,
    season: int,
    valida_nums: Optional[list[int]],
    explain_mode: bool,
) -> str:
    body = {"athlete_id": athlete_id, "season": season, "explain_mode": explain_mode}
    if valida_nums:
        body["valida_nums"] = valida_nums

    resp = await client.post(
        f"{base_url}/api/race-analysis/runs",
        headers=_bearer(token),
        json=body,
        timeout=30.0,
    )
    if resp.status_code != 201:
        raise RuntimeError(
            f"POST /runs falló: HTTP {resp.status_code} — {resp.text[:300]}"
        )
    run_id = resp.json()["run_id"]
    _emit("OK", f"Run creado run_id={run_id}")
    return run_id


async def _poll_status(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    run_id: str,
    timeout_secs: int,
) -> dict:
    deadline = time.time() + timeout_secs
    last_state: Optional[str] = None

    while time.time() < deadline:
        resp = await client.get(
            f"{base_url}/api/race-analysis/runs/{run_id}/status",
            headers=_bearer(token),
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET /status falló: HTTP {resp.status_code} — {resp.text[:300]}"
            )
        data = resp.json()
        state = data.get("state")
        if state != last_state:
            _emit("STATE", f"{run_id} → {state}")
            last_state = state

        if state in {"done", "completed"}:
            return data
        if state in {"failed", "cancelled", "rejected"}:
            raise RuntimeError(f"Run terminó en estado terminal NO-OK: {state}")
        # awaiting_hitl: el smoke automático NO aprueba HITL — falla con mensaje claro
        if state == "awaiting_hitl":
            raise RuntimeError(
                "Run pausado en HITL. Smoke automático no aprueba HITL — usa un atleta "
                "que no requiera review (o aprueba manualmente y reintenta)."
            )

        await asyncio.sleep(POLL_INTERVAL_SECS)

    raise TimeoutError(
        f"Run {run_id} no terminó en {timeout_secs}s (último state={last_state})"
    )


async def _get_result(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    run_id: str,
) -> dict:
    resp = await client.get(
        f"{base_url}/api/race-analysis/runs/{run_id}/result",
        headers=_bearer(token),
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"GET /result falló: HTTP {resp.status_code} — {resp.text[:300]}"
        )
    data = resp.json()
    # Validación mínima del shape AnalysisOutput.
    required = {"pseudonym", "raw_markdown"}
    missing = required - set(data.keys())
    if missing:
        raise RuntimeError(f"AnalysisOutput inválido — faltan keys: {missing}")
    _emit(
        "OK",
        f"AnalysisOutput parseable (pseudonym={data['pseudonym']}, "
        f"words={data.get('word_count')})",
    )
    return data


async def _check_cost_persisted(
    client: httpx.AsyncClient,
    base_url: str,
    admin_token: str,
) -> float:
    """Verifica vía /admin/ai-usage que el cost_usd_total>0 en últimas 24h."""
    resp = await client.get(
        f"{base_url}/api/race-analysis/admin/ai-usage?days=1",
        headers=_bearer(admin_token),
        timeout=15.0,
    )
    if resp.status_code == 403:
        raise RuntimeError(
            "GET /admin/ai-usage devolvió 403 — el token provisto no es admin"
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"GET /admin/ai-usage falló: HTTP {resp.status_code} — {resp.text[:300]}"
        )
    body = resp.json()
    cost = float(body.get("cost_usd_total") or 0.0)
    return cost


# ---------------------------------------------------------------------------
# Comando principal
# ---------------------------------------------------------------------------


@app.command()
def main(
    base_url: str = typer.Option(
        ...,
        envvar="RACE_SMOKE_BASE_URL",
        help="Base URL del backend (sin slash final). Ej: https://mi-2yzi.onrender.com",
    ),
    token: str = typer.Option(
        ...,
        envvar="RACE_SMOKE_TOKEN",
        help="JWT de un usuario coach o admin (para POST /runs).",
    ),
    admin_token: Optional[str] = typer.Option(
        None,
        envvar="RACE_SMOKE_ADMIN_TOKEN",
        help=(
            "JWT admin para chequear /admin/ai-usage. Si --token ya es admin, "
            "puede omitirse — se reutiliza."
        ),
    ),
    athlete_id: int = typer.Option(
        ...,
        help="ID del atleta sobre el que correr el análisis (debe existir en DB).",
    ),
    season: int = typer.Option(2026, help="Temporada a analizar."),
    valida_num: list[int] = typer.Option(
        [],
        help="Válidas a incluir (vacío → todas las disponibles del año).",
    ),
    explain_mode: bool = typer.Option(
        False,
        help="Activa explain_mode (más eventos, útil para debug, mismo cost).",
    ),
    timeout_secs: int = typer.Option(
        DEFAULT_TIMEOUT_SECS,
        help="Timeout total del polling (segundos). Default 5 min.",
    ),
    skip_cost_check: bool = typer.Option(
        False,
        help="Omite el chequeo de cost_usd > 0 (útil en local con AI fake).",
    ),
) -> None:
    """Ejecuta smoke E2E y exit 0 / 1 según resultado."""
    base_url = base_url.rstrip("/")
    admin_token = admin_token or token

    async def _run() -> int:
        async with httpx.AsyncClient() as client:
            try:
                _emit("BEGIN", f"smoke contra {base_url}, athlete={athlete_id}")
                run_id = await _post_run(
                    client,
                    base_url,
                    token,
                    athlete_id,
                    season,
                    list(valida_num) or None,
                    explain_mode,
                )

                status = await _poll_status(
                    client, base_url, token, run_id, timeout_secs
                )
                _emit("OK", f"Run done en {status.get('elapsed_seconds')}s")

                await _get_result(client, base_url, token, run_id)

                if not skip_cost_check:
                    cost = await _check_cost_persisted(client, base_url, admin_token)
                    if cost <= 0.0:
                        _emit("FAIL", f"cost_usd_total esperado >0, obtenido {cost}")
                        return 1
                    _emit("OK", f"cost persistido OK (24h total=${cost:.6f})")

                _emit("DONE", "smoke OK")
                return 0

            except (httpx.HTTPError, RuntimeError, TimeoutError) as exc:
                _emit("FAIL", f"{type(exc).__name__}: {exc}")
                return 1

    code = asyncio.run(_run())
    sys.exit(code)


if __name__ == "__main__":
    app()
