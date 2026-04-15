# Workflow — Fase 1: Auth, Roles, Atletas y Antropometria PHV

**Fecha:** 2026-04-14
**Contexto:** Sistema de trazabilidad entrenador-deportistas para Club Trocha y Ruta
**Alcance:** Autenticacion, roles/permisos, CRUD de atletas, seccion antropometria con calculadora PHV Mirwald

---

## Decision arquitectonica: Monolito para Fase 1

El scaffolding existente define microservicios, pero para Fase 1 (auth + atletas + antropometria) un **monolito modular con FastAPI** es mas eficiente:
- Un solo servicio backend con routers separados por dominio
- Se puede descomponer en microservicios despues sin reescribir logica
- Menos friccion de infra para arrancar (1 Dockerfile, 1 proceso)

La estructura interna sigue la separacion por dominios del scaffolding para facilitar la extraccion futura.

---

## Modelo de datos — Fase 1

```
clubs
├── id (PK)
├── name
├── code (unique, ej: "trocha-y-ruta")
├── location
├── created_at
└── is_active

users  (Fase 1: login activo para admin, coach, parent. Athletes se crean sin credenciales pero con user_id reservado para futuro login)
├── id (PK)
├── email (unique, nullable — atletas no tienen email en Fase 1)
├── hashed_password (nullable — atletas no tienen password en Fase 1)
├── first_name
├── last_name
├── phone
├── role (ENUM: admin, coach, parent, athlete)
├── is_active
├── can_login (BOOLEAN, default true; false para atletas menores en Fase 1)
├── created_at
└── created_by (FK users.id, nullable)

club_members
├── id (PK)
├── club_id (FK clubs.id)
├── user_id (FK users.id)
├── role_in_club (ENUM: admin, coach, parent, athlete)
├── joined_at
└── UNIQUE(club_id, user_id)

parent_athlete  (relacion padre-hijo)
├── id (PK)
├── parent_id (FK users.id WHERE role=parent)
├── athlete_id (FK athletes.id)
└── relationship (ENUM: padre, madre, acudiente)

athletes  (perfil deportivo; user_id conecta con users para futuro login)
├── id (PK)
├── user_id (FK users.id, unique) ← se crea user con can_login=false
├── first_name
├── last_name
├── birth_date
├── sex (ENUM: M, F)
├── years_in_club
├── age_decimal (computed en app: (hoy - birth_date) / 365.25)
├── category (computed en app, basado en tabla FCC 2026)
├── club_id (FK clubs.id)
├── created_by (FK users.id — el entrenador que lo registro)
├── created_at
└── updated_at
NOTA: Al crear un atleta se crea un user con role=athlete y can_login=false.
A futuro, el entrenador podra "activar" el login asignando email/password (can_login=true).

anthropometric_records
├── id (PK)
├── athlete_id (FK athletes.id)
├── evaluation_date
├── mesocycle
├── weight_kg (DECIMAL 5,2)
├── standing_height_cm (DECIMAL 5,1)
├── arm_span_cm (DECIMAL 5,1)
├── sitting_height_cm (DECIMAL 5,1)
├── leg_length_cm (VIRTUAL: standing_height - sitting_height)
├── leg_sitting_ratio (VIRTUAL: leg_length / sitting_height)
├── maturity_offset (computed en app — formula Mirwald)
├── age_at_phv (computed: age_decimal - maturity_offset)
├── maturation_status (ENUM: Pre-PHV, Circa-PHV, Post-PHV)
├── training_implications (TEXT, auto-generado)
├── evaluated_by (FK users.id)
├── created_at
└── notes
```

### Formula PHV Mirwald (2002) — extraida del Excel

```
Datos de entrada: sexo, edad_decimal, peso_kg, talla_pie_cm, talla_sentado_cm
Calculados:
  leg_length = talla_pie - talla_sentado
  ratio = leg_length / talla_sentado

HOMBRES (M):
  MO = -9.236
     + 0.0002708 * (leg_length * sitting_height)
     - 0.001663  * (age * leg_length)
     + 0.007216  * (age * sitting_height)
     + 0.02292   * (weight / standing_height * 100)

MUJERES (F):
  MO = -9.376
     + 0.0001882 * (leg_length * sitting_height)
     + 0.0022    * (age * leg_length)
     + 0.005841  * (age * sitting_height)
     - 0.002658  * (age * weight)
     + 0.07693   * (weight / standing_height * 100)

Edad al PHV = edad_decimal - MO
Estado:
  MO < -1.0  → Pre-PHV
  -1.0 a +1.0 → Circa-PHV
  MO > +1.0  → Post-PHV
```

### Tabla de categorias — Federacion Colombiana de Ciclismo 2026

La categoria se auto-calcula a partir del **ano de nacimiento** del atleta. La tabla incluye sexo implicito (categorias con sufijo "femenino" aplican a sexo F; sin sufijo aplican a M).

**Nota de implementacion:** La logica compara `birth_date.year` contra los rangos. Para categorias "y mas" o "y menos", se usa un limite abierto. Las categorias femeninas son equivalentes en rango de anos pero se asignan por sexo.

| Categoria | Ano nacimiento | Sexo |
|-----------|---------------|------|
| Teteros sin pedales | 2022 y mas | M/F |
| Teteros con pedales | 2022 y mas | M/F |
| Pre-Infantil A | 2021-2020 | M |
| Pre-Infantil A femenino | 2021-2020 | F |
| Pre-Infantil B | 2019-2018 | M |
| Pre-Infantil B femenino | 2019-2018 | F |
| Infantil A | 2017-2016 | M |
| Infantil A femenino | 2017-2016 | F |
| Infantil B | 2015-2014 | M |
| Infantil B femenino | 2015-2014 | F |
| Pre-juvenil A | 2013-2012 | M |
| Pre-juvenil A femenino | 2013-2012 | F |
| Pre-juvenil B | 2011-2010 | M |
| Pre-juvenil B femenino | 2011-2010 | F |
| Junior | 2009-2008 | M |
| Junior femenino | 2009-2008 | F |
| Elite | 2007 y menos | M |
| Elite femenina | 2007 y menos | F |
| Promocional (Novatos) | 2007 y menos | M/F |
| Master Damas | 1991 y menos | F |
| Master A | 1991-1987 | M |
| Master B 1 | 1986-1982 | M |
| Master B 2 | 1977-1981 | M |
| Master C 1 | 1976-1972 | M |
| Master C 2 | 1967-1971 | M |
| Master D | 1966 y menos | M |

**Para el club (10-15 anos), las categorias relevantes son:**
- Pre-Infantil B / B femenino (2019-2018 → 7-8 anos en 2026)
- Infantil A / A femenino (2017-2016 → 9-10 anos)
- Infantil B / B femenino (2015-2014 → 11-12 anos)
- Pre-juvenil A / A femenino (2013-2012 → 13-14 anos)
- Pre-juvenil B / B femenino (2011-2010 → 15-16 anos)

---

## Pasos del Workflow

### Paso 1: Scaffolding del proyecto monolito ✅
**Tipo:** setup
**Agentes:** `backend-architect` (diseño de estructura y dependencias), `devops-architect` (Dockerfile, .env.example, .gitignore)
**Archivos a crear:**
```
trocha-y-ruta/
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml          # con uv o pip
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app, CORS, routers
│   │   ├── config.py           # pydantic-settings (.env)
│   │   ├── database.py         # SQLAlchemy async engine + session
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # DeclarativeBase
│   │   │   ├── user.py
│   │   │   ├── club.py
│   │   │   ├── athlete.py
│   │   │   └── anthropometry.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── club.py
│   │   │   ├── athlete.py
│   │   │   └── anthropometry.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── clubs.py
│   │   │   ├── athletes.py
│   │   │   └── anthropometry.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py         # JWT, hashing
│   │   │   ├── phv.py          # Calculadora PHV Mirwald
│   │   │   └── permissions.py  # RBAC helpers
│   │   └── dependencies.py     # get_db, get_current_user
│   └── tests/
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_athletes.py
│       └── test_phv.py
├── frontend/                   # (Paso 6)
├── docker-compose.yml
├── docker-compose.override.yml
├── .env.example
├── .gitignore
└── README.md
```

**Dependencias backend:**
```
fastapi>=0.115
uvicorn[standard]
sqlalchemy[asyncio]>=2.0
aiomysql
alembic
pydantic>=2.0
pydantic-settings
pyjwt
passlib[bcrypt]
python-multipart
httpx
```

**Criterio de exito:** `uvicorn app.main:app --reload` arranca sin errores, `GET /health` retorna 200.

---

### Paso 2: Modelos SQLAlchemy y migracion inicial ✅
**Tipo:** backend
**Agentes:** `backend-architect` (diseño de modelos, relaciones, constraints), `sql-pro` (optimizacion de esquema, indices, tipos de datos MySQL)
**Archivos:** `app/models/*.py`, `app/database.py`, `alembic/`
**Detalle:**
- Definir todos los modelos del esquema de Fase 1
- `users` con campo `hashed_password`, `role` como Enum
- `athletes` separado de `users` (un atleta tiene un user_id opcional — los ninos pueden no tener login)
- `anthropometric_records` con todos los campos del Excel
- `club_members` como tabla intermedia (many-to-many users-clubs)
- `parent_athlete` relacion padres-hijos
- Generar migracion con Alembic: `alembic revision --autogenerate -m "fase1_initial_schema"`
- Seed: crear club "Trocha y Ruta" y usuario admin por defecto

**Criterio de exito:** `alembic upgrade head` crea las tablas en MySQL sin errores.

**Completado 2026-04-14. Notas de implementacion:**
- Relaciones SQLAlchemy agregadas con `back_populates` y `foreign_keys` en string-form
- `ParentAthlete.relationship` renombrado a `relationship_type` (colision con `sqlalchemy.orm.relationship`); alias de columna preserva el nombre en DB
- `MaturationStatus` usa `values_callable` para almacenar valores `Pre-PHV`/`Circa-PHV`/`Post-PHV`
- Indexes agregados: `ix_users_role`, `ix_athletes_club_id`, `ix_athletes_created_by`, `ix_anthro_athlete_date (compuesto)`, `ix_club_members_user_id`, `ix_parent_athlete_athlete_id`
- `bcrypt` fijado en `<4.0.0` — bcrypt 4.x rompe passlib internamente
- `pymysql[rsa]` + `cryptography` requeridos para Alembic sync con MySQL 8 (`caching_sha2_password`)
- Migración manual: `alembic/versions/072add69b927_fase1_initial_schema.py`
- Seed: `backend/scripts/seed.py` — crea club, admin, coach y 5 atletas de ejemplo

---

### Paso 3: Autenticacion JWT ✅
**Tipo:** backend
**Agentes:** `backend-architect` (diseño de endpoints y flujo auth), `security-engineer` (auditoria JWT, hashing, OWASP auth best practices)
**Archivos:** `app/services/auth.py`, `app/routers/auth.py`, `app/dependencies.py`
**Endpoints:**
- `POST /api/auth/login` — email + password → JWT (access + refresh)
- `POST /api/auth/refresh` — refresh token → nuevo access token
- `GET /api/auth/me` — datos del usuario autenticado

**Detalle:**
- PyJWT para generar/verificar tokens (NO python-jose)
- passlib[bcrypt] para hashing de passwords
- Access token: 30 min. Refresh token: 7 dias.
- JWT payload: `{ sub: user_id, role: role, club_ids: [...] }`
- Dependency `get_current_user` que extrae el user del token
- Dependency `require_role(roles: list[str])` para RBAC

**Criterio de exito:** Login retorna tokens, endpoints protegidos rechazan sin token (401), role incorrecto (403).

**Completado 2026-04-14. Notas de implementacion:**
- `passlib` eliminado — incompatible con bcrypt ≥4.x y Python 3.14. Se usa `bcrypt` directamente
- JWT `sub` claim es string (RFC 7519), se convierte a/desde int en el flujo
- `get_current_user` valida: token válido, type=access, usuario existe, is_active, can_login
- `require_role(allowed_roles)` es un dependency factory que retorna el usuario si su rol está permitido
- `MeResponse` incluye `club_ids` extraidos de `club_memberships` (eager loaded)
- HTTPBearer scheme usado para extraer token del header Authorization
- Tests unitarios: hashing, JWT roundtrip, token inválido (5/5 passing)

---

### Paso 4: CRUD de clubes y usuarios ✅
**Tipo:** backend
**Agentes:** `backend-architect` (endpoints, validaciones, reglas de negocio RBAC), `security-engineer` (validacion de permisos, proteccion de datos de menores)
**Archivos:** `app/routers/clubs.py`, `app/routers/users.py`, `app/schemas/club.py`, `app/schemas/user.py`
**Endpoints clubes (solo admin):**
- `POST /api/clubs` — crear club
- `GET /api/clubs` — listar clubes
- `PATCH /api/clubs/{id}` — editar club
- `GET /api/clubs/{id}` — detalle club con miembros

**Endpoints usuarios:**
- `POST /api/users` — crear usuario (admin crea coaches, coach crea parents/athletes)
- `GET /api/users` — listar (filtrado por club y rol)
- `PATCH /api/users/{id}` — editar
- `POST /api/clubs/{club_id}/members` — asociar usuario a club

**Reglas de negocio:**
- Admin puede crear coaches y asignarlos a clubes
- Coach puede crear parents y athletes solo en sus clubes
- Un coach puede pertenecer a multiples clubes
- Parents y athletes pertenecen a un solo club
- Relacion parent-athlete via endpoint dedicado

**Criterio de exito:** CRUD completo funcional, permisos validados por rol.

**Completado 2026-04-14. Notas de implementacion:**
- `ClubMemberOut` usa `@model_validator(mode="before")` para aplanar `member.user` en campos planos (first_name, last_name)
- `ClubDetailOut` hereda `ClubOut` + `members: list[ClubMemberOut]` con `selectinload` en 2 niveles
- `await db.refresh(member, attribute_names=["user"])` necesario post-flush para evitar `MissingGreenlet` en async
- Usuarios router: `_ALLOWED_CREATIONS` dict define qué roles puede crear cada actor
- Coach scope: `_coach_club_ids()` extrae club_ids donde el usuario tiene `role_in_club=coach`
- `UserCreate` extendido con `club_id` opcional; si se provee, se crea `ClubMember` en la misma transacción
- `GET /api/users` excluye atletas (se gestionan por `/api/athletes`); coach solo ve usuarios de sus clubes
- `IntegrityError` capturado para duplicados de email (409) y membresías duplicadas (409)
- `asyncio_default_test_loop_scope = "session"` agregado a pyproject.toml para evitar `Future attached to different loop` en tests async
- 28 tests de integración: 12 para clubes, 16 para usuarios (43 total en suite)

---

### Paso 5: CRUD de atletas con auto-calculos ✅
**Tipo:** backend
**Agentes:** `backend-architect` (endpoints, logica de auto-calculo, servicio PHV), `quality-engineer` (validacion de formulas Mirwald contra Excel)
**Archivos:** `app/routers/athletes.py`, `app/schemas/athlete.py`, `app/services/phv.py`
**Endpoints:**
- `POST /api/athletes` — crear atleta (solo coach)
- `GET /api/athletes` — listar atletas del club del coach
- `GET /api/athletes/{id}` — detalle con ultimo registro antropometrico
- `PATCH /api/athletes/{id}` — editar datos basicos
- `POST /api/athletes/{id}/anthropometry` — registrar medicion antropometrica
- `GET /api/athletes/{id}/anthropometry` — historial de mediciones

**Campos auto-calculados al crear atleta:**
- `age_decimal` = (fecha_evaluacion - birth_date) / 365.25
- `category` = segun tabla de categorias por edad

**Campos auto-calculados en antropometria:**
- `leg_length_cm` = standing_height - sitting_height
- `leg_sitting_ratio` = leg_length / sitting_height
- `maturity_offset` = formula Mirwald segun sexo
- `age_at_phv` = age_decimal - maturity_offset
- `maturation_status` = Pre-PHV / Circa-PHV / Post-PHV
- `training_implications` = texto auto-generado segun estado

**Servicio PHV (`app/services/phv.py`):**
```python
def calculate_mirwald_offset(sex: str, age: float, weight: float,
                              standing_height: float, sitting_height: float) -> dict:
    leg_length = standing_height - sitting_height
    ratio = leg_length / sitting_height

    if sex == "M":
        mo = (-9.236
              + 0.0002708 * (leg_length * sitting_height)
              - 0.001663 * (age * leg_length)
              + 0.007216 * (age * sitting_height)
              + 0.02292 * (weight / standing_height * 100))
    else:  # F
        mo = (-9.376
              + 0.0001882 * (leg_length * sitting_height)
              + 0.0022 * (age * leg_length)
              + 0.005841 * (age * sitting_height)
              - 0.002658 * (age * weight)
              + 0.07693 * (weight / standing_height * 100))

    age_at_phv = age - mo

    if mo < -1.0:
        status = "Pre-PHV"
        implications = "Habilidades, juego, coordinacion. Fuerza solo peso corporal. Sin intervalos estructurados."
    elif mo > 1.0:
        status = "Post-PHV"
        implications = "Puede iniciar fuerza progresiva. Entrenamiento mas estructurado permitido."
    else:
        status = "Circa-PHV"
        implications = "EN ESTIRON: reducir volumen repetitivo. Revisar bici cada 4-6 sem. Vigilar Osgood-Schlatter."

    return {
        "leg_length_cm": round(leg_length, 1),
        "leg_sitting_ratio": round(ratio, 4),
        "maturity_offset": round(mo, 2),
        "age_at_phv": round(age_at_phv, 2),
        "maturation_status": status,
        "training_implications": implications,
    }
```

**Criterio de exito:** Crear atleta + registrar antropometria retorna todos los campos calculados correctamente. Valores coinciden con el Excel.

**Completado 2026-04-14. Notas de implementacion:**
- `services/category.py` nuevo: `compute_age_decimal()` y `get_category()` con tabla FCC 2026 completa
- `age_decimal` y `category` se calculan en app (no almacenados en DB), enriquecidos al construir respuesta
- `AthleteDetailOut` extiende `AthleteOut` con `latest_anthropometry` (registro más reciente)
- `AthleteListOut` wrapper con `items` + `total` para paginación futura
- Al crear atleta: se crea `User(role=athlete, can_login=false)` + `Athlete` + `ClubMember` en una transacción
- Al actualizar atleta: sincroniza `first_name`/`last_name` con el `User` vinculado
- Antropometría: `age_decimal` se calcula a la `evaluation_date` (no a hoy), lo que permite registros retroactivos correctos
- PHV Mirwald validado: masculino Pre-PHV, femenino Circa-PHV, Post-PHV — fórmulas coinciden con el Excel
- 49 tests nuevos: 17 integración (CRUD + permisos), 32 unitarios (PHV, categorías FCC, edad decimal)
- Suite total: 92 tests passing

---

### Paso 6: Frontend — Scaffolding, API client y Auth store

> Antes era un solo paso. Se divide en 5 sub-pasos secuenciales para reducir el alcance de cada PR y facilitar la revisión.

---

#### Paso 6.1: Scaffolding base y configuracion del proyecto
**Tipo:** setup
**Agentes:** `devops-architect` (Dockerfile dev, configuracion Vite, estructura de carpetas)
**Archivos:** `frontend/`

**Scaffolding:**
```bash
pnpm create vite@latest frontend -- --template react-ts
cd frontend
pnpm add @tanstack/react-query @tanstack/react-query-devtools
pnpm add zustand
pnpm add react-router-dom
pnpm add react-hook-form @hookform/resolvers zod
pnpm add axios
pnpm add recharts
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button input label card badge table form select tabs dialog alert separator skeleton
```

**Estructura de carpetas a crear:**
```
frontend/src/
├── api/              # axios instance + funciones de llamada por dominio
├── components/
│   ├── ui/           # shadcn (auto-generado)
│   ├── layout/       # Sidebar, TopBar, AppShell
│   └── shared/       # LoadingSpinner, ErrorBoundary, ConfirmDialog
├── hooks/            # hooks reutilizables (useDebounce, etc.)
├── lib/              # utils.ts (cn), constants.ts, phv.ts (calculo cliente)
├── routes/           # paginas por dominio: auth/, athletes/, dashboard/
├── store/            # auth.store.ts
└── types/            # tipos TypeScript por dominio
```

**Configuracion Vite:**
- `vite.config.ts`: alias `@/` → `src/`, proxy `/api` → `http://localhost:8000` en dev
- `tsconfig.json`: `paths` con `@/*`
- `.env.example`: `VITE_API_BASE_URL=http://localhost:8000`

**Criterio de exito:** `pnpm dev` arranca sin errores. Pagina en blanco visible en `http://localhost:5173`. Alias `@/` funciona.

---

#### Paso 6.2: API client y tipos TypeScript compartidos
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/api/`, `src/types/`

**`src/api/client.ts`** — axios instance central:
```ts
// interceptor request: agrega Authorization: Bearer <token>
// interceptor response: si 401 → limpia store y redirige a /login
// baseURL desde import.meta.env.VITE_API_BASE_URL
```

**`src/api/auth.ts`** — funciones de auth:
```ts
export const login(email, password) → Promise<{ access_token, refresh_token, token_type }>
export const refreshToken(refresh_token) → Promise<{ access_token, ... }>
export const getMe() → Promise<MeResponse>
```

**`src/api/athletes.ts`** — funciones de atletas:
```ts
export const getAthletes(params?) → Promise<AthleteListOut>
export const getAthlete(id) → Promise<AthleteDetailOut>
export const createAthlete(data) → Promise<AthleteOut>
export const updateAthlete(id, data) → Promise<AthleteOut>
export const getAnthropometry(athleteId) → Promise<AnthropometricRecord[]>
export const createAnthropometry(athleteId, data) → Promise<AnthropometricRecord>
```

**`src/types/`** — interfaces TypeScript que reflejan los schemas del backend:
- `auth.types.ts`: `LoginRequest`, `TokenResponse`, `MeResponse`
- `athlete.types.ts`: `AthleteOut`, `AthleteDetailOut`, `AthleteCreate`, `AthleteUpdate`, `AthleteListOut`
- `anthropometry.types.ts`: `AnthropometricRecord`, `AnthropometryCreate`
- `enums.ts`: `Sex`, `MaturationStatus`, `UserRole`

**Criterio de exito:** `tsc --noEmit` pasa. El cliente hace un `GET /health` al backend y recibe 200 (verificable en devtools).

---

#### Paso 6.3: Auth store con Zustand y persistencia
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/store/auth.store.ts`

**Estado del store:**
```ts
interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: MeResponse | null
  isAuthenticated: boolean
  isLoading: boolean

  login(email: string, password: string): Promise<void>
  logout(): void
  refreshSession(): Promise<void>   // llamado por interceptor 401
  fetchMe(): Promise<void>
}
```

**Detalles de implementacion:**
- `persist` middleware de Zustand con `sessionStorage` (no localStorage — dato sensible de menores)
- `accessToken` guardado en memoria del store (no en cookie ni localStorage)
- `refreshToken` guardado en `sessionStorage` via persist
- `login()`: llama `api/auth.login()` → guarda tokens → llama `fetchMe()`
- `logout()`: limpia store + `sessionStorage` + redirige a `/login`
- `refreshSession()`: llama `api/auth.refreshToken()` → actualiza `accessToken`; si falla → `logout()`

**Criterio de exito:** Login guarda tokens. Recarga de pagina restaura sesion desde sessionStorage. Logout limpia completamente.

---

#### Paso 6.4: Login page con formulario validado
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/routes/auth/LoginPage.tsx`

**Implementar:**
- Formulario con `react-hook-form` + schema `zod`:
  ```ts
  z.object({ email: z.string().email(), password: z.string().min(6) })
  ```
- Estado de carga: boton deshabilitado con spinner durante el login
- Manejo de error: mensaje claro si credenciales incorrectas (401) o servidor caido (500+)
- Redireccion post-login: a `/dashboard` si rol=coach o admin; a `/` si otro
- Responsive: centrado en pantalla, logo del club arriba

**NO implementar en este paso:** registro de usuario (flujo de admin, Fase 2).

**Criterio de exito:** Login funcional contra el backend real. Errores muestran mensaje legible. Token visible en store.

---

#### Paso 6.5: Layout, sidebar y rutas protegidas
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/components/layout/`, `src/routes/`, `src/App.tsx`

**Estructura de rutas (`react-router-dom` v6):**
```
/login                  → LoginPage (publica)
/                       → redirect a /dashboard (protegida)
/dashboard              → DashboardPage (coach, admin)
/athletes               → AthletesListPage (coach)
/athletes/:id           → AthleteDetailPage (coach)
/athletes/new           → AthleteFormPage (coach)
/athletes/:id/edit      → AthleteFormPage (coach)
*                       → NotFoundPage
```

**`ProtectedRoute` component:**
```tsx
// Si no autenticado → redirect /login
// Si rol no permitido → redirect /dashboard con toast de error
// Acepta prop allowedRoles: UserRole[]
```

**`AppShell` component:**
- Sidebar colapsable con navegacion: Dashboard, Atletas, (Perfil)
- Links activos resaltados (`NavLink`)
- TopBar: nombre del usuario, boton logout
- Sidebar muestra items segun rol del usuario en store

**DashboardPage:** placeholder con cards de metricas vacias (total atletas, ultima evaluacion, etc.)

**Criterio de exito:** Navegar a `/athletes` sin token redirige a `/login`. Con token de coach, sidebar visible y navegacion funcional. URL directa a ruta inexistente muestra 404.

---

### Paso 7: Frontend — CRUD de atletas

> Dividido en 4 sub-pasos. Los pasos 7.3 y 7.4 pueden ejecutarse en paralelo.

---

#### Paso 7.1: Hooks TanStack Query para atletas
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/hooks/athletes/`

**Hooks a crear:**
```ts
// src/hooks/athletes/useAthletes.ts
export function useAthletes(filters?: AthleteFilters)
// → useQuery(['athletes', filters], () => api.getAthletes(filters))

// src/hooks/athletes/useAthlete.ts
export function useAthlete(id: number)
// → useQuery(['athlete', id], () => api.getAthlete(id))

// src/hooks/athletes/useCreateAthlete.ts
export function useCreateAthlete()
// → useMutation(api.createAthlete, { onSuccess: invalidate ['athletes'] })

// src/hooks/athletes/useUpdateAthlete.ts
export function useUpdateAthlete(id: number)
// → useMutation(api.updateAthlete, { onSuccess: invalidate ['athlete', id] + ['athletes'] })
```

**Configuracion QueryClient** en `src/main.tsx`:
- `staleTime: 30_000` (30s) — datos de atletas no cambian frecuentemente
- `retry: 1` — un solo reintento en error de red
- `QueryClientProvider` wrapping toda la app

**Criterio de exito:** `useAthletes()` retorna la lista del backend. `tsc --noEmit` pasa.

---

#### Paso 7.2: Lista de atletas con DataTable y filtros
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/routes/athletes/AthletesListPage.tsx`, `src/components/athletes/AthletesTable.tsx`

**Columnas de la tabla (TanStack Table v8 via shadcn DataTable):**
| Columna | Campo | Formato |
|---------|-------|---------|
| Nombre | first_name + last_name | link a detalle |
| Edad | age_decimal | `X.X anos` |
| Sexo | sex | `M` / `F` |
| Categoria | category | badge |
| Estado PHV | maturation_status del ultimo registro | badge coloreado (ver Paso 8.4) |
| Acciones | — | boton editar, boton ver detalle |

**Filtros (toolbar sobre la tabla):**
- Input de busqueda por nombre (debounced 300ms)
- Select de categoria (opciones de la tabla FCC)
- Select de estado PHV (Pre-PHV / Circa-PHV / Post-PHV / Todos)

**Estados de la UI:**
- Skeleton de 5 filas mientras carga
- Mensaje "No hay atletas registrados" con boton "+ Agregar atleta" si lista vacia
- Toast de error si falla la peticion

**Boton "Nuevo atleta":** visible solo para coach, navega a `/athletes/new`.

**Criterio de exito:** Lista muestra atletas del seed. Filtros reducen la tabla en tiempo real. Esqueleto visible durante carga.

---

#### Paso 7.3: Formulario crear / editar atleta
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/routes/athletes/AthleteFormPage.tsx`, `src/components/athletes/AthleteForm.tsx`

**Campos del formulario:**
| Campo | Tipo input | Validacion |
|-------|-----------|-----------|
| Nombres | text | requerido, min 2 |
| Apellidos | text | requerido, min 2 |
| Fecha de nacimiento | date | requerido, max hoy, min 1990-01-01 |
| Sexo | select (M / F) | requerido |
| Anos en el club | number | requerido, min 0, max 20 |

**Auto-calculos en tiempo real** (usando `watch` de RHF):
- Al cambiar `birth_date`: calcular y mostrar `age_decimal` y `category` debajo del campo, en texto informativo gris. Logica replicada del backend en `src/lib/category.ts`.
- Estos campos son solo de visualizacion, no se envian en el body (el backend los calcula).

**`src/lib/category.ts`** — replica de la logica Python del backend:
```ts
export function computeAgeDecimal(birthDate: Date, referenceDate = new Date()): number
export function getCategory(birthYear: number, sex: Sex): string
```

**Modo edicion:** el componente detecta si tiene `id` en la ruta → carga datos con `useAthlete(id)` → pre-rellena el formulario.

**Submit:**
- Crear: `useCreateAthlete()` → navega a `/athletes/:id` con toast de exito
- Editar: `useUpdateAthlete(id)` → invalida cache → toast de exito

**Criterio de exito:** Crear atleta desde el formulario y verlo en la lista. Editar actualiza los datos. Edad y categoria se muestran correctamente al seleccionar fecha.

---

#### Paso 7.4: Vista detalle de atleta
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/routes/athletes/AthleteDetailPage.tsx`, `src/components/athletes/AthleteInfoCard.tsx`

**Layout de la pagina:**
```
[← Volver a lista]    [boton Editar atleta]

┌─────────────────────────────────────────────┐
│  Nombre Apellido          Categoria: [badge]│
│  Edad: X.X anos  |  Sexo: M/F  |  En club: X anos  │
└─────────────────────────────────────────────┘

[Tabs]
├── Info general         → AthleteInfoCard (datos basicos)
└── Antropometria        → placeholder "Proximamente" (se completa en Paso 8)
```

**`AthleteInfoCard`:** muestra todos los campos del atleta en formato legible. Si tiene `latest_anthropometry`, muestra el estado PHV con badge coloreado y la fecha de la ultima evaluacion.

**Skeleton:** mientras carga `useAthlete(id)`, mostrar skeleton del layout.

**Error 404:** si el atleta no existe (404 del backend), mostrar mensaje con boton volver.

**Criterio de exito:** Navegar a `/athletes/:id` muestra los datos correctos. Tab de Antropometria visible (aunque muestre placeholder). Boton editar lleva al formulario pre-rellenado.

---

### Paso 8: Frontend — Seccion antropometria y PHV

> Dividido en 4 sub-pasos. 8.2 y 8.3 pueden ejecutarse en paralelo despues de 8.1.

---

#### Paso 8.1: Formulario antropometrico con calculo PHV en tiempo real
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/components/athletes/AnthropometryForm.tsx`, `src/lib/phv.ts`, `src/hooks/athletes/useAnthropometry.ts`

**`src/lib/phv.ts`** — replica exacta de la formula Mirwald del backend:
```ts
interface PHVInput {
  sex: Sex
  ageDecimal: number
  weightKg: number
  standingHeightCm: number
  sittingHeightCm: number
}

interface PHVResult {
  legLengthCm: number
  legSittingRatio: number
  maturityOffset: number
  ageAtPhv: number
  maturationStatus: MaturationStatus
  trainingImplications: string
}

export function calculatePHV(input: PHVInput): PHVResult | null
// Retorna null si algun campo es 0 o invalido (formulario incompleto)
```

**Hooks:**
```ts
// src/hooks/athletes/useAnthropometry.ts
export function useAnthropometry(athleteId: number)
// → useQuery(['anthropometry', athleteId], ...)

export function useCreateAnthropometry(athleteId: number)
// → useMutation → invalidate ['anthropometry', athleteId] + ['athlete', athleteId]
```

**Campos del formulario:**
| Campo | Tipo | Validacion |
|-------|------|-----------|
| Fecha de evaluacion | date | requerido, max hoy |
| Mesociclo | text | requerido (ej: "Prep Gral 1") |
| Peso (kg) | number | requerido, 20-150 |
| Talla de pie (cm) | number | requerido, 100-220 |
| Envergadura (cm) | number | requerido, 100-220 |
| Talla sentado (cm) | number | requerido, 50-120 |
| Notas | textarea | opcional, max 500 chars |

**Panel de resultados PHV en tiempo real** (se actualiza con cada cambio via `watch`):
```
┌──────────────────────────────────────────┐
│  CALCULO PHV (en tiempo real)            │
│  Longitud pierna: XX.X cm               │
│  Ratio pierna/sentado: X.XXXX           │
│  Maturity Offset: +X.XX / -X.XX         │
│  Edad al PHV: XX.XX anos                │
│  Estado: [badge coloreado]              │
│  Implicaciones: [texto]                 │
└──────────────────────────────────────────┘
```
- Si algun campo esta vacio → panel muestra "Completa los campos para ver el calculo"
- La edad decimal se calcula a la `evaluation_date` (no a hoy) — importante para registros retroactivos

**Submit:** `useCreateAnthropometry()` → toast de exito → invalida cache → panel se oculta/resetea.

**Criterio de exito:** Ingresar los datos del Excel y verificar que los valores calculados en frontend coincidan exactamente con los del backend. El formulario guarda y la tabla se actualiza.

---

#### Paso 8.2: Historial de mediciones antropometricas
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/components/athletes/AnthropometryHistory.tsx`

**Tabla de historial (orden cronologico descendente):**
| Columna | Campo | Formato |
|---------|-------|---------|
| Fecha | evaluation_date | DD/MM/YYYY |
| Mesociclo | mesocycle | texto |
| Peso | weight_kg | X.X kg |
| Talla | standing_height_cm | XXX.X cm |
| Talla sentado | sitting_height_cm | XX.X cm |
| Offset | maturity_offset | +X.XX / -X.XX |
| Estado PHV | maturation_status | badge coloreado |
| Edad al PHV | age_at_phv | XX.XX anos |

**Interacciones:**
- Click en una fila → abre modal con todos los campos incluyendo `training_implications` y `notes`
- Boton "+ Nueva medicion" sobre la tabla → muestra el `AnthropometryForm` (8.1) en un `Dialog` o seccion expandible

**Estados:**
- Skeleton de 3 filas durante carga
- Mensaje "No hay mediciones registradas aun" si historial vacio

**Criterio de exito:** Historial muestra los registros del seed. Click en fila abre modal con detalles completos.

---

#### Paso 8.3: Graficas de crecimiento (Recharts)
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/components/athletes/GrowthCharts.tsx`

**Tres graficas (LineChart de Recharts):**

1. **Talla vs Tiempo**
   - X: `evaluation_date` (formato mes/año)
   - Y: `standing_height_cm`
   - Tooltip: fecha exacta + valor
   - Color: azul

2. **Peso vs Tiempo**
   - X: `evaluation_date`
   - Y: `weight_kg`
   - Tooltip: fecha exacta + valor
   - Color: verde

3. **Maturity Offset vs Tiempo**
   - X: `evaluation_date`
   - Y: `maturity_offset`
   - Linea horizontal de referencia en Y=0, Y=-1 y Y=+1 (limites Pre/Circa/Post PHV)
   - Puntos coloreados segun `maturation_status` (verde/amarillo/azul)
   - Color de linea: purpura

**Layout:** 3 graficas apiladas verticalmente o en grid 2+1. Responsive (100% de ancho del contenedor).

**Si menos de 2 mediciones:** mostrar mensaje "Se necesitan al menos 2 mediciones para generar la grafica" en lugar del chart.

**Criterio de exito:** Con ≥2 registros del seed, las 3 graficas se renderizan. Tooltip muestra datos correctos al hover.

---

#### Paso 8.4: Integracion completa en vista de detalle
**Tipo:** frontend
**Agentes:** `general-purpose`
**Archivos:** `src/routes/athletes/AthleteDetailPage.tsx`, `src/components/shared/PHVBadge.tsx`

**`PHVBadge` component reutilizable:**
```tsx
// Props: status: MaturationStatus | null
// Pre-PHV  → badge verde    (#22c55e) + texto "Pre-PHV"
// Circa-PHV → badge amarillo (#eab308) + texto "Circa-PHV"  
// Post-PHV → badge azul     (#3b82f6) + texto "Post-PHV"
// null      → badge gris "Sin evaluar"
```

**Tab "Antropometria" (completo):**
```
[+ Nueva medicion]    (boton — abre Dialog con AnthropometryForm)

GrowthCharts          (3 graficas de evolucion)

AnthropometryHistory  (tabla de historial)
```

**Tab "Info general" (actualizar):**
- Si `latest_anthropometry` existe → mostrar `PHVBadge` + fecha ultima evaluacion + `training_implications` en un card resaltado
- Implicaciones de entrenamiento: destacado con icono de advertencia para Circa-PHV (estiron activo)

**Criterio de exito:**
- Tab Antropometria muestra formulario en dialog, graficas e historial integrados
- `PHVBadge` aparece en Info general y en la lista de atletas
- Flujo completo: login → lista atletas → detalle → nueva medicion → grafica actualizada

---

### Paso 9: Docker Compose y seed data ✅ (completado junto con Paso 2)
**Tipo:** devops
**Agentes:** `devops-architect` (docker-compose, Dockerfiles, networking, health checks), `backend-architect` (script de seed data)
**Archivos:** `docker-compose.yml`, `docker-compose.override.yml`, `scripts/seed.py`
**Implementar:**
- docker-compose con: MySQL 8.4, backend (FastAPI), frontend (Vite dev)
- Script de seed que crea:
  - Club "Trocha y Ruta" (Cali, Valle del Cauca)
  - Usuario admin
  - Usuario entrenador de prueba
  - 3-5 atletas de ejemplo con datos antropometricos

**Criterio de exito:** `docker compose up` levanta todo el stack. Login con usuario seed funciona.

**Completado 2026-04-14. Stack verificado:**
- MySQL 8.4 + backend FastAPI levantados y saludables
- `entrypoint.sh` ejecuta migraciones + seed antes de uvicorn
- `GET /health` retorna `{"status": "ok"}`
- Swagger UI disponible en `http://localhost:8000/docs`

---

### Paso 10: Tests y validacion
**Tipo:** testing
**Agentes:** `quality-engineer` (estrategia de testing, cobertura, edge cases), `security-engineer` (validacion final de auth, permisos, datos sensibles de menores)
**Implementar:**
- Tests unitarios del servicio PHV (comparar con resultados del Excel)
- Tests de integracion de auth (login, refresh, permisos)
- Tests de endpoints de atletas y antropometria
- Test E2E basico: login → crear atleta → registrar antropometria

**Criterio de exito:** Suite de tests pasa. Valores PHV coinciden con la hoja de calculo Excel.

---

## Resumen de endpoints Fase 1

| Metodo | Ruta | Rol minimo | Descripcion |
|--------|------|-----------|-------------|
| POST | /api/auth/login | publico | Login |
| POST | /api/auth/refresh | autenticado | Refresh token |
| GET | /api/auth/me | autenticado | Perfil actual |
| POST | /api/clubs | admin | Crear club |
| GET | /api/clubs | autenticado | Listar clubes |
| PATCH | /api/clubs/{id} | admin | Editar club |
| POST | /api/users | admin/coach | Crear usuario |
| GET | /api/users | autenticado | Listar usuarios (filtrado) |
| PATCH | /api/users/{id} | admin/coach | Editar usuario |
| POST | /api/athletes | coach | Crear atleta |
| GET | /api/athletes | coach | Listar atletas |
| GET | /api/athletes/{id} | coach | Detalle atleta |
| PATCH | /api/athletes/{id} | coach | Editar atleta |
| POST | /api/athletes/{id}/anthropometry | coach | Nueva medicion |
| GET | /api/athletes/{id}/anthropometry | coach | Historial mediciones |

---

## Dependencias entre pasos

```
Paso 1 (scaffolding)
  └→ Paso 2 (modelos + migracion)
       └→ Paso 3 (auth JWT)
            └→ Paso 4 (CRUD clubes/usuarios)
                 └→ Paso 5 (CRUD atletas + PHV)
                      └→ 6.1 (scaffolding Vite + estructura)
                           └→ 6.2 (API client + tipos TS)
                                └→ 6.3 (auth store Zustand)
                                     └→ 6.4 (login page)
                                          └→ 6.5 (layout + rutas protegidas)
                                               └→ 7.1 (hooks TanStack Query)
                                                    ├→ 7.2 (lista atletas + DataTable)
                                                    └→ 7.3 (formulario crear/editar)
                                                         └→ 7.4 (vista detalle atleta)
                                                              └→ 8.1 (form antropometria + lib/phv.ts)
                                                                   ├→ 8.2 (historial mediciones)  ─┐
                                                                   └→ 8.3 (graficas Recharts)     ─┤
                                                                                                   └→ 8.4 (integracion completa)
Paso 9 (docker) ←── completado junto con Paso 2
Paso 10 (tests) ←── incremental, se agrega en cada paso
```

---

## Deuda de seguridad pre-produccion

Hallazgos de auditoría OWASP (2026-04-14) que **deben resolverse antes del deploy a producción**. Los que aplican a datos de menores tienen prioridad máxima.

### CRIT-02: Refresh token sin revocación
**CWE:** CWE-613 / CWE-384
**Riesgo:** Un refresh token robado es válido 7 días completos. No hay forma de invalidarlo server-side. Datos biométricos de menores quedan expuestos sin posibilidad de corte inmediato.
**Solución:** Agregar claim `jti` (UUID) a cada refresh token + tabla `refresh_tokens(jti, user_id, expires_at, revoked_at)`. En `/refresh`: verificar que `jti` no esté revocado, luego revocar el anterior.
**Esfuerzo estimado:** 4-6h
**Bloquea:** LOW-02 (logout)

### HIGH-01: Sin rate limiting en /login
**CWE:** CWE-307
**Riesgo:** Brute force ilimitado sobre cuentas de coaches y admin con acceso a datos de menores.
**Solución A (app):** `pip install slowapi` + `@limiter.limit("5/minute")` en el endpoint.
**Solución B (infra, preferida en prod):** Rate limiting en nginx/Traefik/proxy inverso.
**Esfuerzo estimado:** 1h

### HIGH-03: `club_ids` embebidos en JWT payload
**CWE:** CWE-602
**Riesgo:** Si un usuario es removido de un club, el token sigue presentando los `club_ids` antiguos hasta 30 min (tiempo de expiración del access token). Cualquier router que confíe en el payload del token en lugar de la DB tendrá autorización incorrecta.
**Nota:** `get_current_user` ya consulta la DB en cada request — el riesgo aplica solo si futuros routers leen `club_ids` del token directamente.
**Solución:** Eliminar `club_ids` del payload. Usar `current_user.club_memberships` (ya cargado vía `selectinload`).
```python
# routers/auth.py — en login y refresh
token_data = {"sub": str(user.id), "role": user.role.value}  # sin club_ids
```
**Esfuerzo estimado:** 20 min

### MED-02: `MeResponse` expone campos internos
**CWE:** CWE-359
**Riesgo:** `can_login` (flag de control interno), `phone` y `created_at` expuestos innecesariamente. Principio de minimización de datos — relevante para GDPR/privacidad de datos de menores.
**Solución:** Quitar `can_login`, `phone` y `created_at` de `MeResponse`.
**Esfuerzo estimado:** 15 min

### MED-04: Misma clave para access y refresh tokens
**CWE:** CWE-330
**Riesgo:** Si la clave se compromete, ambos tipos de tokens quedan expuestos simultáneamente.
**Solución:** Configurar `JWT_ACCESS_SECRET` y `JWT_REFRESH_SECRET` como variables de entorno separadas.
**Esfuerzo estimado:** 30 min

### LOW-02: Sin endpoint `/logout`
**CWE:** CWE-613
**Riesgo:** Cerrar sesión es solo una acción cliente (borrar token local). Sin invalidación server-side.
**Nota:** Depende de CRIT-02 para ser efectivo — sin blocklist, el logout es simbólico.
**Solución:** `POST /api/auth/logout` que inserta el `jti` del refresh token en la tabla de revocados.
**Esfuerzo estimado:** 2h (depende de CRIT-02)

---

## Preguntas pendientes para el entrenador

1. ~~**Tabla de categorias oficial:**~~ Resuelto — tabla FCC 2026 integrada.
2. ~~**Atletas sin login:**~~ Resuelto — los atletas se crean con `user_id` (role=athlete, can_login=false). A futuro se activan asignando email/password.
3. ~~**Padres sin login en Fase 1:**~~ Resuelto — los padres SI tienen login (email + contrasena). Rol `parent` en tabla `users`.
4. ~~**Hosting:**~~ Resuelto — MySQL se queda en Hostinger. Se necesita proveedor separado para:
   - **Frontend React** (hosting estatico: Vercel, Netlify, Cloudflare Pages)
   - **Backend FastAPI** (contenedores: Railway, Render, Fly.io, DigitalOcean App Platform)
   - Evaluar en Paso 9 la mejor combinacion costo/simplicidad.
