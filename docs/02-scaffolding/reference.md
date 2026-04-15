# Scaffolding del Proyecto — Club Deportivo Trocha y Ruta

**Fecha de investigacion:** 2026-04-14
**Profundidad:** Exhaustiva (5 agentes de investigacion en paralelo)

---

## Resumen ejecutivo

Este documento define el stack tecnologico, versiones estables, arquitectura de microservicios y scaffolding para la plataforma de gestion del Club Deportivo Trocha y Ruta. El sistema cubre: gestion de atletas juveniles XCO (10-15 anos), planes de entrenamiento, competencias Copa Valle 2026, bienestar, e integraciones con Intervals.icu, Strava, Spond y Google Sheets.

---

## 1. Arquitectura general

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
         │    (LTS)    │    │  (eventos)  │
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

## 2. Stack tecnologico — Versiones estables

### 2.1 Frontend

| Componente | Tecnologia | Version | Justificacion |
|---|---|---|---|
| Framework UI | **React** | 19.2.5 | Estable desde dic 2024; Actions, `use()` nativos |
| Build tool | **Vite** | 8.0.8 | Estandar de la industria para SPAs; CRA deprecado |
| Lenguaje | **TypeScript** | 6.0.2 | Strict mode desde el inicio |
| Estado global | **Zustand** | 5.0.12 | Minimalista, sin boilerplate, TS nativo |
| Server state | **TanStack Query** | 5.99.0 | Cache, retry, sincronizacion de datos del servidor |
| UI Library | **shadcn/ui** | CLI 4.2.0 | Componentes copiados al proyecto, Tailwind nativo, sin vendor-lock |
| Routing | **React Router** | 7.14.0 | Maduro, docs excelentes |
| Formularios | **React Hook Form** | 7.72.1 | Rendimiento superior a Formik |
| Validacion | **Zod** | 4.3.6 | v4 con mejora significativa de performance |
| Graficas | **Recharts** | 3.8.1 | Componentes React nativos, ideal para dashboards de metricas |
| Package manager | **pnpm** | 10.33.0 | 2-3x mas rapido que npm, ahorro de espacio |

**Comando de scaffolding:**

```bash
pnpm create vite@latest trocha-ruta-frontend -- --template react-ts
cd trocha-ruta-frontend
pnpm add @tanstack/react-query zustand react-router react-hook-form zod recharts
pnpm add -D @hookform/resolvers @types/react @types/react-dom
pnpm dlx shadcn@latest init
```

> **Nota:** Next.js descartado — el proyecto es una SPA con API en FastAPI; SSR/SSG no aporta beneficio y agrega complejidad de servidor.

### 2.2 Backend

| Componente | Tecnologia | Version | Justificacion |
|---|---|---|---|
| Lenguaje | **Python** | 3.13.13 | Ultima estable (abr 2026) |
| Framework | **FastAPI** | 0.128.0 | Async nativo, ideal para microservicios + Kafka |
| Servidor ASGI | **uvicorn** | 0.40.0 | Alto rendimiento, hot reload en dev |
| ORM | **SQLAlchemy 2** | 2.0.49 | Async nativo, production-ready, Alembic compatible |
| Migraciones | **Alembic** | 1.17.2 | Del mismo autor de SQLAlchemy, maduro |
| Validacion | **Pydantic v2** | 2.13.0 | Integrado nativamente en FastAPI |
| Background tasks | **Celery** | 5.6.3 | Con Redis como broker; para syncs periodicos |
| JWT | **PyJWT** | 2.12.1 | `python-jose` esta **abandonado** — no usar |
| HTTP client | **httpx** | (ultima) | Async nativo para integraciones externas |

> **FastAPI > Django** para este caso: microservicios + Kafka + integraciones async. Si se necesita panel admin para CRUD directo, considerar un microservicio Django pequeno solo para eso.

> **SQLAlchemy > SQLModel**: SQLModel 0.0.38 sigue en pre-1.0, desarrollo lento. SQLAlchemy 2.0 directo es la opcion production-ready.

### 2.3 Base de datos

| Componente | Tecnologia | Version | Notas |
|---|---|---|---|
| Motor | **MySQL** | 8.4.8 LTS | MySQL 8.0 llega a EOL abr 2026; 9.x es Innovation (no prod) |
| Driver async | **aiomysql** | 0.3.2 | Mantenimiento activo bajo aio-libs |
| Driver sync | **mysqlclient** | 2.2.8 | Para scripts y herramientas CLI |
| Testing | **testcontainers** | 4.14.2 | MySQL real en contenedor por sesion de test |

**Configuracion de connection pool para FastAPI:**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    "mysql+aiomysql://user:pass@host/db",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,      # importante para Hostinger
    pool_recycle=3600,        # previene "MySQL server has gone away"
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

**Estrategia de migracion con BD existente:**

```bash
alembic init alembic
# Configurar alembic.ini y env.py apuntando a la BD existente
alembic revision --autogenerate -m "reflect_existing_schema"
# REVISAR MANUALMENTE la migracion generada
alembic stamp head  # si los modelos coinciden exactamente
```

### 2.4 Mensajeria / Eventos

| Componente | Tecnologia | Version | Notas |
|---|---|---|---|
| **Recomendado inicial** | **Redis Streams** | (parte de Redis 7.x) | Ya esta en el stack (broker de Celery); cero infra extra |
| Alternativa robusta | **RabbitMQ** | 4.2.5 | Si se necesita routing complejo o dead-letter queues |
| Para escalar despues | **Apache Kafka** | 4.0.0 | KRaft mode (ZooKeeper eliminado); solo si se necesita replay de eventos |
| Cliente Kafka Python | **confluent-kafka** | 2.14.0 | Async nativo desde v2.13; mejor rendimiento (C-backed) |
| Monitoring Kafka | **AKHQ** | 0.27.0 | Mejor opcion open-source |

> **Recomendacion honesta:** Kafka es overkill para el volumen actual (~10-20 atletas, eventos moderados). **Empezar con Redis Streams** y migrar a Kafka cuando se necesite replay de eventos o Schema Registry. Disenar los eventos con compatibilidad Kafka desde el inicio (naming conventions, abstraccion de producers/consumers).

**Convencion de nombres de topics (compatible Kafka):**

```
trocha.athlete.synced
trocha.wellness.submitted
trocha.training-plan.updated
trocha.competition.result-recorded
trocha.dashboard.refresh-requested
```

### 2.5 Infraestructura Docker

| Componente | Imagen | Version |
|---|---|---|
| Docker Engine | — | v29.x |
| Docker Compose | — | v2.40 |
| Python base | `python:3.13-slim` | Debian Trixie (~41 MB) |
| Node base (dev) | `node:22-bookworm-slim` | Node 22 LTS "Jod" |
| Nginx (prod) | `nginx:1.27-alpine` | Serving estatico post-build |
| MySQL | `mysql:8.4` | LTS, tag `lts` en Docker Hub |
| Kafka (si se usa) | `confluentinc/confluent-local:8.2` | Zero-config KRaft, ideal para dev |
| Redis | `redis:7-alpine` | Broker Celery + Streams |
| Reverse proxy | `traefik:v3.6` | Auto-descubre containers via labels |

---

## 3. Estructura de carpetas del proyecto

```
trocha-y-ruta/
├── docker-compose.yml              # Base: servicios compartidos
├── docker-compose.override.yml     # Dev: hot reload, volumes, debug ports
├── docker-compose.prod.yml         # Prod: builds, sin volumes, limites
├── .env                            # Variables de entorno (NUNCA commitear)
├── .env.example                    # Template de variables
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
├── services/                       # Backend microservicios
│   ├── athletes/                   # Servicio de atletas
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
│   ├── training/                   # Planes, sesiones, workouts
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── routers/
│   │       ├── plans.py
│   │       ├── sessions.py
│   │       └── workouts.py
│   │
│   ├── competitions/               # Calendario, resultados
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── routers/
│   │
│   ├── wellness/                   # Bienestar diario, Google Sheets sync
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
│       └── event_publisher.py      # Publica eventos a Redis Streams
│
├── shared/                         # Codigo compartido entre servicios
│   ├── db.py                       # SQLAlchemy async engine
│   ├── auth.py                     # PyJWT helpers
│   ├── config.py                   # pydantic-settings
│   ├── events.py                   # Abstraccion de pub/sub (Redis Streams)
│   └── models_base.py              # Base declarativa SQLAlchemy
│
├── migrations/                     # Alembic (centralizado)
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── scripts/                        # Scripts utilitarios existentes
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
    └── scaffolding-proyecto.md     # Este documento
```

---

## 4. Docker Compose — Esqueleto base

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
      - "8080:8080"    # Dashboard Traefik
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
# docker-compose.override.yml (dev — cargado automaticamente)
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
      - "3306:3306"    # Acceso directo para GUI (DBeaver, etc.)

  redis:
    ports:
      - "6379:6379"
```

---

## 5. Health checks

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
│  network    │ ← APIs (exposicion publica)
└──────┬──────┘
       │
┌──────┴──────┐
│  backend    │ ← APIs, MySQL, Redis, Celery
│  network    │ ← Integraciones
└─────────────┘
```

- Servicios se comunican por **nombre de servicio** como hostname (`http://athletes-api:8000`)
- Solo exponer puertos al host para acceso directo en desarrollo (MySQL GUI, Redis CLI)
- Nunca usar `network_mode: host`

---

## 7. Estrategia de eventos — Fase inicial vs Escalada

### Fase 1: Redis Streams (ahora)

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

- **Sin infraestructura adicional** — Redis ya esta como broker de Celery
- Consumer groups para procesamiento distribuido
- Persistencia y replayabilidad basica

### Fase 2: Kafka (cuando escalar)

**Migrar a Kafka cuando se necesite:**
- Replay de semanas de historial de bienestar en un nuevo servicio de analytics
- Schema Registry para contratos multi-servicio
- Exactamente-una-vez (exactly-once) semantics
- Mas de ~10k eventos/dia consistentemente

**Stack Kafka:**
- Apache Kafka 4.0.0 (KRaft, sin ZooKeeper)
- confluent-kafka 2.14.0 (async nativo)
- JSON Schema (simple, legible, suficiente para equipo Python)
- AKHQ 0.27.0 (monitoring UI)

---

## 8. Testing

| Nivel | Herramienta | Estrategia |
|---|---|---|
| Unit (frontend) | Vitest + Testing Library | Componentes, hooks, stores |
| Unit (backend) | pytest + pytest-asyncio | Schemas, logica de negocio |
| Integracion (DB) | testcontainers 4.14.2 | MySQL real en contenedor por sesion |
| E2E | Playwright | Flujos criticos (CRUD atletas, registro bienestar) |
| API | httpx + pytest | Endpoints FastAPI con TestClient |

> **No usar SQLite como fallback** para tests — los dialectos difieren (JSON, ENUM, TINYINT) y generan falsa confianza.

---

## 9. Resumen de versiones — Referencia rapida

### Frontend
| Paquete | Version |
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
| Paquete | Version |
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

### Infraestructura
| Componente | Version/Imagen |
|---|---|
| Docker Engine | v29.x |
| Docker Compose | v2.40 |
| MySQL | 8.4.8 LTS (`mysql:8.4`) |
| Redis | 7.x (`redis:7-alpine`) |
| Python base | `python:3.13-slim` |
| Node base | `node:22-bookworm-slim` |
| Nginx (prod) | `nginx:1.27-alpine` |
| Traefik | `traefik:v3.6` |

### Mensajeria (si se escala a Kafka)
| Componente | Version |
|---|---|
| Apache Kafka | 4.0.0 (KRaft) |
| confluent-kafka | 2.14.0 |
| RabbitMQ (alternativa) | 4.2.5 |
| AKHQ (monitoring) | 0.27.0 |

---

## 10. Decisiones clave y justificaciones

| Decision | Elegido | Descartado | Por que |
|---|---|---|---|
| Frontend build | Vite | CRA, Next.js | CRA deprecado; Next.js agrega SSR innecesario para SPA |
| Backend framework | FastAPI | Django + DRF | Async nativo, ideal para microservicios + integraciones |
| ORM | SQLAlchemy 2.0 | SQLModel, Django ORM | SQLModel pre-1.0; Django ORM requiere Django completo |
| Mensajeria inicial | Redis Streams | Kafka, RabbitMQ | Ya en el stack (Celery broker); Kafka overkill para ~20 atletas |
| MySQL version | 8.4 LTS | 9.x Innovation | Estabilidad en produccion; 8.0 llega a EOL |
| JWT | PyJWT | python-jose | python-jose esta abandonado con vulnerabilidades |
| Driver MySQL async | aiomysql | asyncmy | Mantenimiento activo bajo aio-libs; asyncmy menos activo |
| Python base image | slim (Debian) | alpine | Alpine incompatible con wheels glibc, builds 50x mas lentos |
| Kafka mode | KRaft | ZooKeeper | ZooKeeper eliminado en Kafka 4.0 |

---

## 11. Fuentes

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
