from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings

# ---------------------------------------------------------------------------
# Rate limiter (A3).
#
# Backend in-memory: válido para Render single-worker (free tier). Cuando se
# escale a multi-worker / multi-instancia hay que migrar a Redis con
# ``storage_uri="redis://..."`` para que los contadores sean compartidos.
# Documentación: https://slowapi.readthedocs.io/en/latest/#storage-backends
#
# En test/development se desactiva por defecto para no ensuciar el estado
# entre tests. Para validar el rate-limit explícitamente, el test fixture
# hace ``limiter.reset()`` y setea ``limiter.enabled = True``.
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)
if settings.app_env != "production":
    limiter.enabled = False

from app.routers import ai, alerts, auth, users, clubs, athletes, anthropometry, athlete_race_analysis, calendar, growth, parent_athletes, race_analysis, race_competitors, race_imports, reports, training_sessions  # noqa: E402
from app.routers.consent import consent_router, public_router as consent_public_router  # noqa: E402
from app.routers.monthly_reports import router as monthly_reports_router, parent_router as parent_monthly_router  # noqa: E402

app = FastAPI(
    title="Trocha y Ruta API",
    description="API del Club Deportivo Trocha y Ruta — Fase 1",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(clubs.router, prefix="/api/clubs", tags=["clubs"])
app.include_router(alerts.router, prefix="/api/athletes", tags=["alerts"])
app.include_router(athletes.router, prefix="/api/athletes", tags=["athletes"])
app.include_router(anthropometry.router, prefix="/api/athletes", tags=["anthropometry"])
app.include_router(reports.router, prefix="/api/athletes", tags=["reports"])
app.include_router(growth.router, prefix="/api", tags=["growth"])
app.include_router(parent_athletes.router, prefix="/api/parent-athletes", tags=["parent-athletes"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(consent_public_router, prefix="/api/auth", tags=["consent"])
app.include_router(consent_router, prefix="/api/me/consent", tags=["consent"])
app.include_router(calendar.router, prefix="/api/calendar/events", tags=["calendar"])
app.include_router(calendar.race_events_helper_router, prefix="/api/race-events", tags=["race-events"])
app.include_router(training_sessions.router, prefix="/api/training-sessions", tags=["training-sessions"])
app.include_router(monthly_reports_router, prefix="/api/clubs", tags=["monthly-reports"])
app.include_router(parent_monthly_router, prefix="/api/parents", tags=["monthly-reports"])
app.include_router(race_analysis.router, prefix="/api/race-analysis", tags=["race-analysis"])
app.include_router(race_imports.router, prefix="/api/race-analysis/imports", tags=["race-imports"])
app.include_router(race_competitors.router, prefix="/api/race-competitors", tags=["race-competitors"])
app.include_router(athlete_race_analysis.router, prefix="/api/athletes", tags=["athlete-race-analysis"])


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
