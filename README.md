# Trocha y Ruta — Plataforma de Gestión Deportiva

Sistema de trazabilidad entrenador-deportistas para el **Club Deportivo Trocha y Ruta**, especializado en ciclismo de montaña XCO juvenil (10-15 años) del Valle del Cauca, Colombia.

## Estado del proyecto

| Paso | Descripción | Estado |
|------|-------------|--------|
| 1 | Scaffolding backend (FastAPI monolito) | ✅ Completado |
| 2 | Modelos SQLAlchemy + migración Alembic | ✅ Completado |
| 3 | Autenticación JWT | ⏳ Pendiente |
| 4 | CRUD clubes y usuarios | ⏳ Pendiente |
| 5 | CRUD atletas + calculadora PHV Mirwald | ⏳ Pendiente |
| 6 | Frontend — Auth y layout base | ⏳ Pendiente |
| 7 | Frontend — CRUD atletas | ⏳ Pendiente |
| 8 | Frontend — Antropometría y gráficas PHV | ⏳ Pendiente |
| 9 | Docker Compose + seed data | ✅ Completado (junto con Paso 2) |
| 10 | Tests y validación | ⏳ Pendiente |

## Stack

**Backend:** Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · MySQL 8.4 · PyJWT · passlib  
**Frontend:** React 19 · Vite · TypeScript · shadcn/ui · TanStack Query · Zustand  
**Infra:** Docker Compose · MySQL 8.4 (Hostinger en producción)

## Estructura

```
.
├── backend/            # API FastAPI monolito modular
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/     # users, clubs, athletes, anthropometry
│   │   ├── schemas/
│   │   ├── routers/
│   │   └── services/   # auth, phv (Mirwald), permissions
│   ├── alembic/
│   └── tests/
├── frontend/           # React SPA (Paso 6+)
├── docs/               # Documentación técnica y de entrenamiento
├── docker-compose.yml
└── .env.example
```

## Inicio rápido

### Requisitos
- Python 3.13+
- MySQL 8.4 (local o Hostinger)
- Docker y Docker Compose (opcional)

### Desarrollo local

```bash
# 1. Clonar y configurar variables de entorno
cp .env.example .env
# Editar .env con las credenciales de MySQL

# 2. Crear entorno virtual e instalar dependencias
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Aplicar migraciones (requiere MySQL activo)
alembic upgrade head

# 4. Arrancar la API
uvicorn app.main:app --reload
# API disponible en http://localhost:8000
# Docs en http://localhost:8000/docs
```

### Con Docker Compose (recomendado)

```bash
cp .env.example .env
# Editar .env con credenciales reales

docker compose up
# Aplica migraciones y seed automáticamente
# API en http://localhost:8000
# Docs en http://localhost:8000/docs
```

## Variables de entorno

Ver `.env.example`. Las variables requeridas son:

| Variable | Descripción |
|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` | Servidor MySQL |
| `MYSQL_USER` / `MYSQL_PASS` / `MYSQL_DB` | Credenciales |
| `JWT_SECRET_KEY` | Clave secreta para firmar tokens JWT |

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## Funcionalidades — Fase 1

- **Autenticación JWT** — login, refresh token, roles (admin, coach, parent, athlete)
- **Gestión de atletas** — CRUD con cálculo automático de edad decimal y categoría FCC 2026
- **Calculadora PHV Mirwald** — cálculo de madurez biológica (Pre/Circa/Post-PHV) e implicaciones de entrenamiento
- **RBAC** — permisos por rol en todos los endpoints

## Documentación técnica

- [`docs/workflow-fase1.md`](docs/workflow-fase1.md) — Arquitectura, modelo de datos y pasos de implementación
- [`docs/marco-teorico.md`](docs/marco-teorico.md) — Fundamentación científica LTAD, PHV, fisiología juvenil
- [`docs/scaffolding-proyecto.md`](docs/scaffolding-proyecto.md) — Decisiones de stack y versiones
