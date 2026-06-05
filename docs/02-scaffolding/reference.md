# Project Scaffolding — Club Deportivo Trocha y Ruta

**Research date:** 2026-04-14
**Depth:** Exhaustive (5 research agents in parallel)

---

## Executive Summary

This document defines the technology stack, stable versions, microservices architecture, and scaffolding for the management platform of Club Deportivo Trocha y Ruta. The system covers: management of youth XCO athletes (10-15 years old), training plans, Copa Valle 2026 races, wellness, and integrations with Intervals.icu, Strava, Spond, and Google Sheets.

---

## 1. General Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│           React 19 + Vite + TypeScript + shadcn/ui          │
│                    (SPA, no SSR)                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/REST
                    ┌──────┴──────┐
                    │   Traefik   │  (reverse proxy, dev)
                    └──────┬──────┘
         ┌─────────────────┼─────────────────────┐
         ▼                 ▼                      ▼
┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Athletes   │  │    Training      │  │   Competitions   │
│  Service    │  │    Service       │  │   Service        │
│  (FastAPI)  │  │    (FastAPI)     │  │   (FastAPI)      │
└──────┬──────┘  └───────┬──────────┘  └───────┬──────────┘
       │                 │                      │
       └────────┬────────┴──────────┬───────────┘
                │                   │
         ┌──────┴──────┐    ┌──────┴──────┐
         │   MySQL 8.4 │    │ Redis/Kafka │
         │    (LTS)    │    │  (events)   │
         └─────────────┘    └─────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
             ┌────────────┐ ┌────────────┐ ┌──────────────┐
             │ Wellness   │ │ Intervals  │ │ Integrations │
             │ Service    │ │ Sync       │ │ Service      │
             │ (FastAPI)  │ │ (Celery)   │ │ (Strava,     │
             └────────────┘ └────────────┘ │  Spond, GS)  │
                                           └──────────────┘
```

---

## 2. Technology Stack — Stable Versions

### 2.1 Frontend

| Component | Technology | Version | Justification |
|---|---|---|---|
| UI Framework | **React** | 19.2.5 | Stable since Dec 2024; Actions, native `use()` |
| Build tool | **Vite** | 8.0.8 | Industry standard for SPAs; CRA deprecated |
| Language | **TypeScript** | 6.0.2 | Strict mode from the start |
| Global state | **Zustand** | 5.0.12 | Minimalist, no boilerplate, native TS |
| Server state | **TanStack Query** | 5.99.0 | Cache, retry, server data synchronization |
| UI Library | **shadcn/ui** | CLI 4.2.0 | Components copied into project, native Tailwind, no vendor-lock |
| Routing | **React Router** | 7.14.0 | Mature, excellent docs |
| Forms | **React Hook Form** | 7.72.1 | Superior performance to Formik |
| Validation | **Zod** | 4.3.6 | v4 with significant performance improvement |
| Charts | **Recharts** | 3.8.1 | Native React components, ideal for metrics dashboards |
| Package manager | **pnpm** | 10.33.0 | 2-3x faster than npm, disk space savings |

**Scaffolding command:**

```bash
pnpm create vite@latest trocha-ruta-frontend -- --template react-ts
cd trocha-ruta-frontend
pnpm add @tanstack/react-query zustand react-router react-hook-form zod recharts
pnpm add -D @hookform/resolvers @types/react @types/react-dom
pnpm dlx shadcn@latest init
```

> **Note:** Next.js discarded — the project is a SPA with API in FastAPI; SSR/SSG provides no benefit and adds server complexity.

### 2.2 Backend

| Component | Technology | Version | Justification |
|---|---|---|---|
| Language | **Python** | 3.13.13 | Latest stable (Apr 2026) |
| Framework | **FastAPI** | 0.128.0 | Native async, ideal for microservices + Kafka |
| ASGI server | **uvicorn** | 0.40.0 | High performance, hot reload in dev |
| ORM | **SQLAlchemy 2** | 2.0.49 | Native async, production-ready, Alembic compatible |
| Migrations | **Alembic** | 1.17.2 | Same author as SQLAlchemy, mature |
| Validation | **Pydantic v2** | 2.13.0 | Natively integrated in FastAPI |
| Background tasks | **Celery** | 5.6.3 | With Redis as broker; for periodic syncs |
| JWT | **PyJWT** | 2.12.1 | `python-jose` is **abandoned** — do not use |
| HTTP client | **httpx** | (latest) | Native async for external integrations |

> **FastAPI > Django** for this case: microservices + Kafka + async integrations. If a direct CRUD admin panel is needed, consider a small Django microservice just for that.

> **SQLAlchemy > SQLModel**: SQLModel 0.0.38 is still pre-1.0, slow development. SQLAlchemy 2.0 directly is the production-ready option.

### 2.3 Database

| Component | Technology | Version | Notes |
|---|---|---|---|
| Engine | **MySQL** | 8.4.8 LTS | MySQL 8.0 reaches EOL Apr 2026; 9.x is Innovation (not prod) |
| Async driver | **aiomysql** | 0.3.2 | Active maintenance under aio-libs |
| Sync driver | **mysqlclient** | 2.2.8 | For scripts and CLI tools |
| Testing | **testcontainers** | 4.14.2 | Real MySQL in container per test session |

**Connection pool configuration for FastAPI:**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    "mysql+aiomysql://user:pass@host/db",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,      # important for Hostinger
    pool_recycle=3600,        # prevents "MySQL server has gone away"
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

**Migration strategy with existing database:**

```bash
alembic init alembic
# Configure alembic.ini and env.py pointing to the existing database
alembic revision --autogenerate -m "reflect_existing_schema"
# MANUALLY REVIEW the generated migration
alembic stamp head  # if models match exactly
```

### 2.4 Messaging / Events

| Component | Technology | Version | Notes |
|---|---|---|---|
| **Recommended initial** | **Redis Streams** | (part of Redis 7.x) | Already in the stack (Celery broker); zero extra infra |
| Robust alternative | **RabbitMQ** | 4.2.5 | If complex routing or dead-letter queues are needed |
| For scaling later | **Apache Kafka** | 4.0.0 | KRaft mode (ZooKeeper removed); only if event replay is needed |
| Kafka Python client | **confluent-kafka** | 2.14.0 | Native async since v2.13; better performance (C-backed) |
| Kafka Monitoring | **AKHQ** | 0.27.0 | Best open-source option |

> **Honest recommendation:** Kafka is overkill for the current volume (~10-20 athletes, moderate events). **Start with Redis Streams** and migrate to Kafka when event replay or Schema Registry is needed. Design events with Kafka compatibility from the start (naming conventions, producer/consumer abstraction).

**Topic naming convention (Kafka-compatible):**

```
trocha.athlete.synced
trocha.wellness.submitted
trocha.training-plan.updated
trocha.competition.result-recorded
trocha.dashboard.refresh-requested
```

### 2.5 Docker Infrastructure

| Component | Image | Version |
|---|---|---|
| Docker Engine | — | v29.x |
| Docker Compose | — | v2.40 |
| Python base | `python:3.13-slim` | Debian Trixie (~41 MB) |
| Node base (dev) | `node:22-bookworm-slim` | Node 22 LTS "Jod" |
| Nginx (prod) | `nginx:1.27-alpine` | Static serving post-build |
| MySQL | `mysql:8.4` | LTS, `lts` tag on Docker Hub |
| Kafka (if used) | `confluentinc/confluent-local:8.2` | Zero-config KRaft, ideal for dev |
| Redis | `redis:7-alpine` | Celery broker + Streams |
| Reverse proxy | `traefik:v3.6` | Auto-discovers containers via labels |

---

## 3. Project Folder Structure

```
trocha-y-ruta/
├── docker-compose.yml              # Base: shared services
├── docker-compose.override.yml     # Dev: hot reload, volumes, debug ports
├── docker-compose.prod.yml         # Prod: builds, no volumes, limits
├── .env                            # Environment variables (NEVER commit)
├── .env.example                    # Variables template
│
├── frontend/                       # React SPA
│   ├── Dockerfile
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/                 # React Router pages
│   │   ├── components/
│   │   │   ├── ui/                 # shadcn/ui components
│   │   │   ├── athletes/
│   │   │   ├── training/
│   │   │   ├── competitions/
│   │   │   ├── wellness/
│   │   │   └── dashboard/
│   │   ├── hooks/                  # Custom hooks (useAthletes, etc.)
│   │   ├── stores/                 # Zustand stores
│   │   ├── lib/                    # API client, utils
│   │   └── types/                  # TypeScript interfaces
│   └── public/
│
├── services/                       # Backend microservices
│   ├── athletes/                   # Athletes service
│   │   ├── Dockerfile
│   │   ├── main.py                 # FastAPI app
│   │   ├── models.py               # SQLAlchemy models
│   │   ├── schemas.py              # Pydantic schemas
│   │   ├── routers/
│   │   │   ├── athletes.py
│   │   │   └── evaluations.py
│   │   ├── tasks.py                # Celery tasks
│   │   └── requirements.txt
│   │
│   ├── training/                   # Plans, sessions, workouts
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── routers/
│   │       ├── plans.py
│   │       ├── sessions.py
│   │       └── workouts.py
│   │
│   ├── competitions/               # Calendar, results
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── routers/
│   │
│   ├── wellness/                   # Daily wellness, Google Sheets sync
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── routers/
│   │
│   └── integrations/               # Intervals.icu, Strava, Spond
│       ├── Dockerfile
│       ├── main.py
│       ├── intervals_sync.py
│       ├── strava_sync.py
│       └── event_publisher.py      # Publishes events to Redis Streams
│
├── shared/                         # Code shared across services
│   ├── db.py                       # SQLAlchemy async engine
│   ├── auth.py                     # PyJWT helpers
│   ├── config.py                   # pydantic-settings
│   ├── events.py                   # pub/sub abstraction (Redis Streams)
│   └── models_base.py              # SQLAlchemy declarative base
│
├── migrations/                     # Alembic (centralized)
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── scripts/                        # Existing utility scripts
│   ├── init_database.sql
│   ├── sync_intervals.py
│   └── import_wellness.py
│
├── data/
│   └── backups/
│
└── docs/
    ├── marco-teorico.md
    ├── plan-entrenamiento-2026.md
    └── scaffolding-proyecto.md     # This document
```

---

## 4. Docker Compose — Base Skeleton

```yaml
# docker-compose.yml
services:
  traefik:
    image: traefik:v3.6
    command:
      - --api.insecure=true
      - --providers.docker
      - --providers.docker.exposedbydefault=false
    ports:
      - "80:80"
      - "8080:8080"    # Traefik Dashboard
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks: [frontend, backend]

  frontend:
    build: ./frontend
    labels:
      - traefik.enable=true
      - traefik.http.routers.frontend.rule=PathPrefix(`/`)
    networks: [frontend]

  athletes-api:
    build: ./services/athletes
    labels:
      - traefik.enable=true
      - traefik.http.routers.athletes.rule=PathPrefix(`/api/athletes`)
    depends_on:
      mysql: { condition: service_healthy }
      redis: { condition: service_healthy }
    environment:
      - DATABASE_URL=mysql+aiomysql://${MYSQL_USER}:${MYSQL_PASS}@mysql/${MYSQL_DB}
      - REDIS_URL=redis://redis:6379
    networks: [frontend, backend]

  training-api:
    build: ./services/training
    labels:
      - traefik.enable=true
      - traefik.http.routers.training.rule=PathPrefix(`/api/training`)
    depends_on:
      mysql: { condition: service_healthy }
    networks: [frontend, backend]

  competitions-api:
    build: ./services/competitions
    labels:
      - traefik.enable=true
      - traefik.http.routers.competitions.rule=PathPrefix(`/api/competitions`)
    depends_on:
      mysql: { condition: service_healthy }
    networks: [frontend, backend]

  wellness-api:
    build: ./services/wellness
    labels:
      - traefik.enable=true
      - traefik.http.routers.wellness.rule=PathPrefix(`/api/wellness`)
    depends_on:
      mysql: { condition: service_healthy }
    networks: [frontend, backend]

  integrations:
    build: ./services/integrations
    depends_on:
      mysql: { condition: service_healthy }
      redis: { condition: service_healthy }
    networks: [backend]

  celery-worker:
    build: ./services/integrations
    command: celery -A tasks worker --loglevel=info
    depends_on:
      redis: { condition: service_healthy }
    networks: [backend]

  celery-beat:
    build: ./services/integrations
    command: celery -A tasks beat --loglevel=info
    depends_on:
      redis: { condition: service_healthy }
    networks: [backend]

  mysql:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASS}
      MYSQL_DATABASE: ${MYSQL_DB}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASS}
    volumes:
      - mysql_data:/var/lib/mysql
      - ./scripts/init_database.sql:/docker-entrypoint-initdb.d/01-schema.sql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks: [backend]

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks: [backend]

networks:
  frontend:
  backend:

volumes:
  mysql_data:
```

```yaml
# docker-compose.override.yml (dev — loaded automatically)
services:
  frontend:
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - VITE_HOST=0.0.0.0
    command: pnpm dev --host 0.0.0.0

  athletes-api:
    volumes:
      - ./services/athletes:/app
      - ./shared:/app/shared
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  training-api:
    volumes:
      - ./services/training:/app
      - ./shared:/app/shared
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  mysql:
    ports:
      - "3306:3306"    # Direct access for GUI (DBeaver, etc.)

  redis:
    ports:
      - "6379:6379"
```

---

## 5. Health Checks

```yaml
# MySQL
healthcheck:
  test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s

# Redis
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 5s
  retries: 3

# FastAPI services
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 10s
  timeout: 5s
  retries: 3
```

---

## 6. Networking

```
┌─────────────┐
│  frontend   │ ← React, Traefik
│  network    │ ← APIs (public exposure)
└──────┬──────┘
       │
┌──────┴──────┐
│  backend    │ ← APIs, MySQL, Redis, Celery
│  network    │ ← Integrations
└─────────────┘
```

- Services communicate by **service name** as hostname (`http://athletes-api:8000`)
- Only expose ports to the host for direct access in development (MySQL GUI, Redis CLI)
- Never use `network_mode: host`

---

## 7. Events Strategy — Initial Phase vs Scaling

### Phase 1: Redis Streams (now)

```
                    Redis Streams
                    ┌──────────┐
 Intervals.icu ──→  │ trocha.  │ ──→ Athletes Service
 sync               │ athlete. │
                    │ synced   │
                    └──────────┘
 Google Sheets ──→  ┌──────────┐ ──→ Wellness Service
 import             │ trocha.  │ ──→ Dashboard (WebSocket)
                    │ wellness.│
                    │ submitted│
                    └──────────┘
```

- **No additional infrastructure** — Redis is already in the stack as Celery broker
- Consumer groups for distributed processing
- Basic persistence and replayability

### Phase 2: Kafka (when scaling)

**Migrate to Kafka when needed:**
- Replay weeks of wellness history in a new analytics service
- Schema Registry for multi-service contracts
- Exactly-once semantics
- More than ~10k events/day consistently

**Kafka Stack:**
- Apache Kafka 4.0.0 (KRaft, no ZooKeeper)
- confluent-kafka 2.14.0 (native async)
- JSON Schema (simple, readable, sufficient for Python team)
- AKHQ 0.27.0 (monitoring UI)

---

## 8. Testing

| Level | Tool | Strategy |
|---|---|---|
| Unit (frontend) | Vitest + Testing Library | Components, hooks, stores |
| Unit (backend) | pytest + pytest-asyncio | Schemas, business logic |
| Integration (DB) | testcontainers 4.14.2 | Real MySQL in container per session |
| E2E | Playwright | Critical flows (CRUD athletes, wellness logging) |
| API | httpx + pytest | FastAPI endpoints with TestClient |

> **Do not use SQLite as fallback** for tests — dialects differ (JSON, ENUM, TINYINT) and generate false confidence.

---

## 9. Version Summary — Quick Reference

### Frontend
| Package | Version |
|---|---|
| React | 19.2.5 |
| Vite | 8.0.8 |
| TypeScript | 6.0.2 |
| Zustand | 5.0.12 |
| TanStack Query | 5.99.0 |
| shadcn/ui CLI | 4.2.0 |
| React Router | 7.14.0 |
| React Hook Form | 7.72.1 |
| Zod | 4.3.6 |
| Recharts | 3.8.1 |
| pnpm | 10.33.0 |

### Backend
| Package | Version |
|---|---|
| Python | 3.13.13 |
| FastAPI | 0.128.0 |
| uvicorn | 0.40.0 |
| SQLAlchemy | 2.0.49 |
| Alembic | 1.17.2 |
| Pydantic | 2.13.0 |
| Celery | 5.6.3 |
| PyJWT | 2.12.1 |
| aiomysql | 0.3.2 |
| mysqlclient | 2.2.8 |
| testcontainers | 4.14.2 |

### Infrastructure
| Component | Version/Image |
|---|---|
| Docker Engine | v29.x |
| Docker Compose | v2.40 |
| MySQL | 8.4.8 LTS (`mysql:8.4`) |
| Redis | 7.x (`redis:7-alpine`) |
| Python base | `python:3.13-slim` |
| Node base | `node:22-bookworm-slim` |
| Nginx (prod) | `nginx:1.27-alpine` |
| Traefik | `traefik:v3.6` |

### Messaging (if scaling to Kafka)
| Component | Version |
|---|---|
| Apache Kafka | 4.0.0 (KRaft) |
| confluent-kafka | 2.14.0 |
| RabbitMQ (alternative) | 4.2.5 |
| AKHQ (monitoring) | 0.27.0 |

---

## 10. Key Decisions and Justifications

| Decision | Chosen | Discarded | Why |
|---|---|---|---|
| Frontend build | Vite | CRA, Next.js | CRA deprecated; Next.js adds unnecessary SSR for a SPA |
| Backend framework | FastAPI | Django + DRF | Native async, ideal for microservices + integrations |
| ORM | SQLAlchemy 2.0 | SQLModel, Django ORM | SQLModel pre-1.0; Django ORM requires full Django |
| Initial messaging | Redis Streams | Kafka, RabbitMQ | Already in the stack (Celery broker); Kafka overkill for ~20 athletes |
| MySQL version | 8.4 LTS | 9.x Innovation | Production stability; 8.0 reaches EOL |
| JWT | PyJWT | python-jose | python-jose is abandoned with vulnerabilities |
| MySQL async driver | aiomysql | asyncmy | Active maintenance under aio-libs; asyncmy less active |
| Python base image | slim (Debian) | alpine | Alpine incompatible with glibc wheels, builds 50x slower |
| Kafka mode | KRaft | ZooKeeper | ZooKeeper removed in Kafka 4.0 |

---

## 11. Sources

- React 19.2.5 — [GitHub Releases](https://github.com/facebook/react/releases)
- Vite 8.0.8 — [npm](https://www.npmjs.com/package/vite)
- FastAPI 0.128.0 — [PyPI](https://pypi.org/project/fastapi/)
- SQLAlchemy 2.0.49 — [PyPI](https://pypi.org/project/SQLAlchemy/)
- Kafka 4.0.0 — [Apache Blog](https://kafka.apache.org/blog/2025/03/18/apache-kafka-4.0.0-release-announcement/)
- MySQL 8.4.8 — [Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.4/en/)
- Docker Engine v29 — [Docker Docs](https://docs.docker.com/engine/release-notes/29/)
- Traefik v3.6 — [GitHub Releases](https://github.com/traefik/traefik/releases)
- confluent-kafka 2.14.0 — [PyPI](https://pypi.org/project/confluent-kafka/)
- Python 3.13.13 — [python.org](https://www.python.org/downloads/)
- Pydantic 2.13.0 — [PyPI](https://pypi.org/project/pydantic/)
- Celery 5.6.3 — [PyPI](https://pypi.org/project/celery/)
- PyJWT 2.12.1 — [PyPI](https://pypi.org/project/PyJWT/)
- testcontainers 4.14.2 — [PyPI](https://pypi.org/project/testcontainers/)
