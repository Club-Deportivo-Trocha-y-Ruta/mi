# Trocha y Ruta — Plataforma de Gestión Deportiva

Plataforma entrenador–deportistas–familias del **Club Deportivo Trocha y Ruta**, club de ciclismo de montaña XCO juvenil (10–15 años) del Valle del Cauca, Colombia.

- **App:** <https://mi.clubdeportivotrochayruta.org> (frontend en Cloudflare Pages)
- **API:** <https://mi-2yzi.onrender.com> (Render, plan gratuito — el primer arranque tarda ~50 s)

## Qué hace

| Módulo | Resumen |
|---|---|
| **Atletas y crecimiento** | Ficha del deportista, antropometría, madurez biológica (PHV Mirwald), curvas de crecimiento OMS 2007 y explicaciones con IA revisadas por un crítico. |
| **Entrenamiento** | Asistente de sesiones paso a paso, calendario (salidas y actividades conjuntas), asistencia con RPE y rúbrica (esfuerzo, actitud, técnica), evidencias multimedia y biblioteca de técnica/gymkana. |
| **Competencias** | Copa Valle XCO: importación de resultados oficiales en PDF, identidad de competidores revisada por el entrenador, perfil de circuito (GPX), histórico de temporadas y análisis por válida con IA. |
| **Informes** | Informe técnico mensual del club (PDF/DOCX) y bitácora mensual para cada familia. |
| **Familias** | Portal de padres/acudientes con acceso solo a sus deportistas, consentimientos y notificaciones por correo. |
| **Integraciones** | Sincronización de actividades con Strava (nunca se guarda ni se muestra GPS/ruta), correo con Resend, medios en SFTP Hostinger. |
| **Gobierno** | Roles (admin, coach, parent, athlete), varios entrenadores por club, trazabilidad de cada cambio y auditoría con purga a 24 meses. |

El estado detallado por módulo está en [`docs/implementation-status.md`](docs/implementation-status.md).

## Privacidad (Ley 1581)

La plataforma trata datos de menores de edad. Ningún nombre, fecha de nacimiento, dato médico o identificador de un menor puede aparecer en logs, mensajes de error, commits, fixtures versionados ni prompts de IA. Las salidas de IA sobre deportistas pasan por guardarraíles (lista de nombres prohibidos, límites de palabras, consentimientos). Los archivos `.env*` nunca se versionan ni se comparten.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.13 · FastAPI · SQLAlchemy 2 (async, aiomysql) · Pydantic v2 · Alembic · MySQL 8.4 |
| IA | Capa compartida LangChain (`app/services/llm/`) · LangGraph para el analista de competencias · proveedor por defecto Google Gemini |
| Documentos | Jinja2 (correos) · WeasyPrint (PDF) · docxtpl (DOCX) · pdfplumber + rapidfuzz + pandas (resultados) |
| Frontend | React 19 · Vite · TypeScript · Tailwind v4 · shadcn/ui · TanStack Query · Zustand · React Hook Form + Zod |
| Pruebas | pytest (aiosqlite en memoria) · Vitest + Testing Library + MSW + jest-axe · Playwright · Stryker / mutmut |
| Infra | Docker Compose (backend + MySQL + MailHog) · Render · Cloudflare Pages · MySQL en Hostinger |

## Estructura

```
.
├── backend/              # FastAPI — monolito modular
│   ├── app/
│   │   ├── routers/      # un router por dominio, montados en /api/*
│   │   ├── services/     # lógica de dominio (permisos, IA, competencias, informes…)
│   │   ├── models/       # SQLAlchemy
│   │   └── schemas/      # Pydantic
│   ├── alembic/          # migraciones
│   ├── templates/        # correos y documentos
│   └── tests/
├── frontend/             # React SPA
│   └── src/{routes,components,api,hooks,store,schemas}
├── docs/                 # documentación por módulo (numerada) — ver docs/README.md
├── specs/                # features de Spec Kit (spec → plan → tasks)
└── docker-compose.yml
```

## Inicio rápido

### Con Docker Compose (recomendado)

```bash
cp .env.example .env      # completar credenciales locales
docker compose up
```

El `entrypoint.sh` del backend aplica migraciones, carga los datos de referencia y, con `APP_ENV=development`, datos de demostración.

- API: <http://localhost:8000> · documentación OpenAPI en `/docs`
- MailHog (correos de desarrollo): <http://localhost:8025>

### Backend sin Docker

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # requiere MySQL activo
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxy de /api hacia :8000)
```

## Variables de entorno

La lista completa y comentada está en [`.env.example`](.env.example). Las mínimas para arrancar:

| Variable | Descripción |
|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASS` / `MYSQL_DB` | Conexión a MySQL |
| `JWT_SECRET_KEY` | Clave para firmar los tokens |
| `APP_ENV` | `development` o `production` |
| `AI_ENABLED` / `AI_PROVIDER` / `AI_API_KEY` | IA de la app (con `AI_ENABLED=false` se usa un proveedor falso) |
| `RACE_AI_PROVIDER` | IA de competencias; vacío hereda `AI_PROVIDER` |
| `EMAIL_PROVIDER` | `smtp` (MailHog en desarrollo) o Resend en producción |
| `STRAVA_ENABLED` | Activa la sincronización con Strava |

## Pruebas y verificación

```bash
# Backend
cd backend && source .venv/bin/activate
pytest                        # suite por defecto, sin red ni MySQL
pytest -m mysql               # opcional: MySQL real (TEST_DATABASE_URL, BD terminada en _test)
pytest -m golden              # opcional: evaluación dorada del analista de competencias
ruff check

# Frontend
cd frontend
npm run typecheck             # tsc es la verificación estática (no hay ESLint)
npm test                      # Vitest
npm run test:e2e              # Playwright
npm run build
```

## Despliegue

- **Backend:** despliegue automático en Render desde `main`; las migraciones corren al iniciar.
- **Frontend:** Cloudflare Pages.
- **Después de cada despliegue:** revisar `/health` y un endpoint autenticado.
- **Tareas programadas (GitHub Actions):** conciliación diaria de Strava, retención de auditoría y evaluaciones de IA (`.github/workflows/`).

## Cómo contribuir

- Ramas `<tipo>/<slug>` (p. ej. `feat/season-panorama`); commits en Conventional Commits con descripción en español.
- Las features nuevas se trabajan con Spec Kit en `specs/NNN-slug/`, siguiendo la constitución del proyecto (`.specify/memory/constitution.md`).
- Al cerrar un trabajo, actualizar `docs/implementation-status.md` y `docs/technical-notes.md`.
- Textos para usuarios en español neutro (Colombia) con tildes completas.

## Documentación

- [`docs/README.md`](docs/README.md) — índice de la documentación por módulo
- [`docs/01-marco-teorico.md`](docs/01-marco-teorico.md) — fundamentos científicos (LTAD, PHV, fisiología juvenil)
- [`docs/implementation-status.md`](docs/implementation-status.md) — estado por módulo
- [`docs/technical-notes.md`](docs/technical-notes.md) — bitácora técnica fechada
- [`CLAUDE.md`](CLAUDE.md) — guía de arquitectura para agentes de IA
