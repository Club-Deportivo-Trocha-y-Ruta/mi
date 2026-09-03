import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine
from app.routers import ai, alerts, auth, users, clubs, athletes, anthropometry, athlete_race_analysis, calendar, dashboard, growth, intervals, parent_athletes, profile, race_analysis, race_competitors, race_events, race_imports, race_series, reports, training_sessions
from app.routers.session_assistant import router as session_assistant_router
from app.routers.club_race_insights import router as club_race_insights_router
from app.routers.consent import consent_router, public_router as consent_public_router
from app.routers.monthly_reports import router as monthly_reports_router, parent_router as parent_monthly_router
from app.routers.athlete_monthly_newsletters import router as athlete_newsletters_router, clubs_router as newsletter_clubs_router, training_router as newsletter_training_router
from app.routers.parent_newsletters import router as parent_newsletters_router
from app.routers.webhooks_resend import router as webhooks_resend_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la app.

    Al arrancar, reconciliamos runs huérfanos del pipeline agéntico
    race-analyst (specs/036, US3): el registro de runs activos de
    ``services/race/ai/runner.py`` vive solo en memoria, y Render redeploya
    en cada push a `main`, así que cualquier fila ``agent_runs`` que haya
    quedado en ``running``/``awaiting_hitl`` del proceso anterior queda
    huérfana para siempre si no la cerramos aquí. Ver
    ``services/race/ai/run_reconciliation.py`` para el detalle — esa función
    ya nunca lanza, pero además envolvemos la llamada acá: un fallo al
    reconciliar NUNCA debe bloquear ni tumbar el arranque de la app.

    Al apagar (incluido el spin-down de Render free tier) cerramos el pool de
    conexiones limpiamente con ``engine.dispose()``. Evita el ruido
    ``RuntimeError: Event loop is closed`` de ``__del__`` y libera las
    conexiones contra Hostinger de forma ordenada.
    """
    try:
        from app.services.race.ai.run_reconciliation import reconcile_orphan_runs

        await reconcile_orphan_runs()
    except Exception:  # noqa: BLE001 — el arranque nunca debe caer por esto.
        logger.exception("lifespan: reconcile_orphan_runs falló al arrancar")
    yield
    await engine.dispose()


app = FastAPI(
    title="Trocha y Ruta API",
    description="API del Club Deportivo Trocha y Ruta — Fase 1",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Excepciones no manejadas registradas aquí (en vez de dejarlas escapar
    hasta ServerErrorMiddleware) para que CORSMiddleware sí agregue los
    headers Access-Control-Allow-* a la respuesta 500 — sin esto el frontend
    ve un bloqueo CORS en vez del error real.
    """
    logger.error(
        "Excepción no manejada | method=%s path=%s error_type=%s",
        request.method, request.url.path, type(exc).__name__,
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(clubs.router, prefix="/api/clubs", tags=["clubs"])
app.include_router(alerts.router, prefix="/api/athletes", tags=["alerts"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(athletes.router, prefix="/api/athletes", tags=["athletes"])
app.include_router(anthropometry.router, prefix="/api/athletes", tags=["anthropometry"])
app.include_router(reports.router, prefix="/api/athletes", tags=["reports"])
app.include_router(growth.router, prefix="/api", tags=["growth"])
app.include_router(parent_athletes.router, prefix="/api/parent-athletes", tags=["parent-athletes"])
app.include_router(
    parent_newsletters_router,
    prefix="/api/parents/me/athletes/{athlete_id}/newsletters",
    tags=["parent-newsletters"],
)
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(consent_public_router, prefix="/api/auth", tags=["consent"])
app.include_router(consent_router, prefix="/api/me/consent", tags=["consent"])
app.include_router(calendar.router, prefix="/api/calendar/events", tags=["calendar"])
app.include_router(calendar.race_events_helper_router, prefix="/api/race-events", tags=["race-events"])
app.include_router(training_sessions.router, prefix="/api/training-sessions", tags=["training-sessions"])
app.include_router(monthly_reports_router, prefix="/api/clubs", tags=["monthly-reports"])
app.include_router(parent_monthly_router, prefix="/api/parents", tags=["monthly-reports"])
app.include_router(race_analysis.router, prefix="/api/race-analysis", tags=["race-analysis"])
app.include_router(race_series.router, prefix="/api/race-analysis/race-series", tags=["race-series"])
app.include_router(race_imports.router, prefix="/api/race-analysis/imports", tags=["race-imports"])
app.include_router(race_events.router, prefix="/api/race-analysis/race-events", tags=["race-events"])
app.include_router(race_competitors.router, prefix="/api/race-competitors", tags=["race-competitors"])
app.include_router(athlete_race_analysis.router, prefix="/api/athletes", tags=["athlete-race-analysis"])
app.include_router(athlete_newsletters_router, prefix="/api/athletes", tags=["athlete-newsletters"])
app.include_router(newsletter_clubs_router, prefix="/api/clubs", tags=["athlete-newsletters"])
app.include_router(newsletter_training_router, prefix="/api/training", tags=["athlete-newsletters"])
app.include_router(club_race_insights_router, prefix="/api/races", tags=["club-race-insights"])
app.include_router(session_assistant_router, prefix="/api/clubs", tags=["session-assistant"])
app.include_router(intervals.router, prefix="/api/intervals", tags=["intervals"])
app.include_router(webhooks_resend_router, prefix="/api/webhooks", tags=["webhooks"])

if settings.strava_enabled:
    from app.routers import activities as activities_router_module
    from app.routers import strava_integration as strava_integration_router_module

    app.include_router(
        strava_integration_router_module.router,
        prefix="/api",
        tags=["strava-integration"],
    )
    app.include_router(
        activities_router_module.router,
        prefix="/api",
        tags=["activities"],
    )


# Boot: configurar db_factory del grafo race-AI (F4) para que los nodos
# puedan abrir AsyncSession en runtime fuera del Depends(get_db) de FastAPI.
from app.database import AsyncSessionLocal  # noqa: E402
from app.services.race.ai.db import set_db_factory  # noqa: E402

set_db_factory(AsyncSessionLocal)


_local_media_dir = Path("static/uploads/media")
_local_media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}
