from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import alerts, auth, users, clubs, athletes, anthropometry, growth

app = FastAPI(
    title="Trocha y Ruta API",
    description="API del Club Deportivo Trocha y Ruta — Fase 1",
    version="0.1.0",
)

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
app.include_router(growth.router, prefix="/api", tags=["growth"])


@app.get("/health")
async def health():
    return {"status": "ok"}
