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

### Paso 5: CRUD de atletas con auto-calculos
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

---

### Paso 6: Frontend — Auth y layout base
**Tipo:** frontend
**Agentes:** `general-purpose` (scaffolding Vite + React, componentes UI, stores Zustand, routing)
**Archivos:** `frontend/src/`
**Scaffolding:**
```bash
pnpm create vite@latest frontend -- --template react-ts
cd frontend
pnpm add @tanstack/react-query zustand react-router react-hook-form zod axios
pnpm dlx shadcn@latest init
```

**Implementar:**
- Login page con formulario (email + password)
- Layout con sidebar (navegacion por rol)
- Auth store (Zustand): token, user, login/logout
- API client (axios) con interceptor JWT
- Protected routes por rol
- Pagina de dashboard vacia (placeholder)

**Criterio de exito:** Login funcional, redireccion por rol, rutas protegidas.

---

### Paso 7: Frontend — CRUD de atletas
**Tipo:** frontend
**Agentes:** `general-purpose` (componentes React, DataTable, formularios, integracion API)
**Archivos:** `frontend/src/components/athletes/`, `frontend/src/routes/athletes/`
**Implementar:**
- Lista de atletas (tabla con shadcn DataTable)
  - Columnas: nombre, edad, sexo, categoria, estado maduracion, acciones
  - Filtros: por categoria, estado PHV
- Formulario crear/editar atleta
  - Datos basicos: nombres, apellidos, fecha nacimiento, sexo, anos en club
  - Edad y categoria se muestran auto-calculados al seleccionar fecha nacimiento
- Detalle de atleta con pestanas:
  - Info general
  - Antropometria (historial + nuevo registro)

**Criterio de exito:** CRUD completo de atletas desde el frontend.

---

### Paso 8: Frontend — Seccion antropometria y PHV
**Tipo:** frontend
**Agentes:** `general-purpose` (formulario antropometria, calculo PHV en tiempo real, graficas Recharts, badges de estado)
**Archivos:** `frontend/src/components/athletes/AnthropometryForm.tsx`, `AnthropometryHistory.tsx`
**Implementar:**
- Formulario de registro antropometrico:
  - Campos de entrada: peso, talla, envergadura, talla sentado
  - Campos auto-calculados (en tiempo real, antes de guardar):
    - Longitud pierna, ratio, maturity offset, edad al PHV, estado, implicaciones
  - Fecha evaluacion y mesociclo
- Historial de mediciones (tabla cronologica)
- Grafica de crecimiento longitudinal (Recharts):
  - Talla vs tiempo
  - Peso vs tiempo
  - Maturity offset vs tiempo
- Indicador visual de estado PHV (badge con color: verde=Pre, amarillo=Circa, azul=Post)
- Notas de implicaciones de entrenamiento visibles

**Criterio de exito:** Formulario calcula PHV en tiempo real, guarda correctamente, historial visible con graficas.

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
                      └→ Paso 6 (frontend auth) ←── puede empezar en paralelo desde Paso 3
                           └→ Paso 7 (frontend atletas)
                                └→ Paso 8 (frontend antropometria)
Paso 9 (docker) ←── puede empezar en paralelo desde Paso 1
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
