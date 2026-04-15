# Plan de Pruebas QA — Fase 1
## Club Deportivo Trocha y Ruta — Sistema de Trazabilidad Entrenador-Deportistas

| Campo | Valor |
|---|---|
| Proyecto | Club Deportivo Trocha y Ruta |
| Fase | Fase 1 — Auth + Atletas + Antropometría PHV |
| Fecha | 2026-04-14 |
| Versión | 1.1.0 |
| Estado | Activo — Ejecución en curso |
| Preparado por | Quality Engineer |
| Audiencia | Equipo de QA, entrenador, desarrollador |
| Última actualización | 2026-04-14 — Suite completa implementada: 130 backend + 225 frontend = 355 tests automatizados |

## Resumen de cobertura actual

| Nivel | Tests | Estado |
|---|---|---|
| Unit Backend (pytest) | 130 pasan | ✅ 0 fallos |
| Unit + Component Frontend (Vitest) | 225 pasan | ✅ 0 fallos |
| E2E (Playwright) | 10 specs escritos | ⏳ Requieren `docker compose up` + `playwright install` |
| **Total automatizado** | **355 tests** | **✅ 355/355 pasan (E2E pendiente de ejecutar)** |

---

## 1. Alcance

### 1.1 Qué se prueba

| Módulo | Backend | Frontend |
|---|---|---|
| Autenticación JWT | login, refresh, /me, hashing bcrypt | Auth store (Zustand), login page, ProtectedRoute |
| Gestión de clubes | POST/GET/PATCH /api/clubs | — (solo consumo desde atletas) |
| Gestión de usuarios | POST/GET/PATCH /api/users | — |
| Gestión de atletas | POST/GET/PATCH /api/athletes | Lista DataTable, formulario crear/editar, vista detalle |
| Antropometría + PHV | POST/GET /api/athletes/{id}/anthropometry | Formulario, historial, gráficas Recharts, PHV tiempo real |
| Cálculo PHV Mirwald | `services/phv.py` | `src/lib/phv.ts` |
| Categorías FCC 2026 | `services/category.py` | `src/lib/category.ts` |
| RBAC | Middleware FastAPI (admin/coach/parent/athlete) | Rutas protegidas por rol |
| Privacidad de menores | Respuestas API, logs | sessionStorage vs localStorage, exposición en UI |

### 1.2 Qué NO se prueba en Fase 1

- Integración con Intervals.icu, Strava, Spond (Fase 2+)
- Módulo de cuestionario de bienestar diario
- App móvil (Fase 2+)
- Análisis de video (Kinovea)
- Planes de entrenamiento generados automáticamente
- Notificaciones push o email
- Informes PDF exportables

---

## 2. Entorno de pruebas

### 2.1 Requisitos previos

- Docker Desktop >= 4.x
- Python >= 3.12 con `venv` activado (solo para tests backend sin Docker)
- Node.js >= 20.x con pnpm >= 9.x (solo para tests frontend sin Docker)
- Puerto 8000 (API), 3000 (frontend dev), 3306 (MySQL) disponibles

### 2.2 Levantar el stack completo

```bash
# Clonar y configurar variables de entorno
cp .env.example .env
# Editar .env con los valores de desarrollo (ver sección 2.4)

# Levantar stack completo (aplica migraciones + seed automáticamente)
docker compose up

# Verificar que la API está activa
curl http://localhost:8000/docs
```

### 2.3 Ejecutar solo los tests

```bash
# --- Backend ---
source backend/.venv/bin/activate
cd backend
pytest                         # Todos los tests (92 actualmente)
pytest tests/test_phv.py -v    # Solo PHV
pytest tests/test_auth.py -v   # Solo auth
pytest --cov=app --cov-report=term-missing  # Con cobertura

# --- Frontend ---
cd frontend
pnpm test                      # Modo watch
pnpm test --run                # Single run (CI)
pnpm test --coverage           # Con cobertura (v8)
```

### 2.4 Credenciales de prueba (seed data — solo desarrollo local)

> AVISO: Estas credenciales son exclusivas para el entorno de desarrollo y Docker local. Nunca deben utilizarse ni exponerse en producción.

| Rol | Email | Contraseña |
|---|---|---|
| Admin | `admin@trochyruta.com` | `Admin2026!` |
| Coach | `entrenador@trochyruta.com` | `Coach2026!` |

### 2.5 URLs base

| Entorno | URL API | URL Frontend |
|---|---|---|
| Docker local | `http://localhost:8000` | `http://localhost:3000` |
| Dev nativo | `http://127.0.0.1:8000` | `http://localhost:5173` |

### 2.6 Documentación interactiva

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 3. Estrategia de testing

### 3.1 Pirámide de pruebas

```
           /\
          /E2E\          Playwright — flujos críticos completos
         /------\
        /  Integ  \      pytest httpx ASGI — endpoints con base de datos real
       /------------\
      / Unit Backend  \   pytest — services/phv.py, services/category.py, auth services
     /----------------\
    /  Unit Frontend   \  Vitest + jsdom — lib/phv.ts, lib/category.ts, stores, components
   /--------------------\
```

### 3.2 Herramientas por nivel

| Nivel | Herramienta | Reporte | Target cobertura |
|---|---|---|---|
| Unit Backend | pytest 8.x | JUnit XML + terminal | 90% líneas en `services/` |
| Integration Backend | pytest + httpx ASGI | JUnit XML | 80% endpoints |
| Unit Frontend | Vitest 4.x + jsdom | LCOV + text | 85% en `lib/`, `store/`, `hooks/` |
| Component Frontend | Vitest + @testing-library/react | LCOV | 70% en `components/` |
| E2E | Playwright (via `/playwright-cli`) | HTML report | Flujos críticos cubiertos al 100% |

### 3.3 Convención de nomenclatura de casos

```
[MÓDULO]-[TIPO]-[NNN]

Módulo: AUTH, CLUBS, USERS, ATHLETES, ANTHRO, PHV, CAT, E2E, SEC, PRIV
Tipo:   UNIT, INTG, E2E
NNN:    número secuencial

Ejemplos:
  PHV-UNIT-001    Cálculo de offset varón Pre-PHV
  AUTH-INTG-003   Login con contraseña incorrecta
  ATHLETES-E2E-002 Flujo crear atleta y ver categoría
```

---

## 4. Suite de pruebas por módulo

### 4.1 Módulo Auth — Backend

#### Tests unitarios (`tests/test_auth.py`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| AUTH-UNIT-001 | Hash de contraseña es diferente al texto plano | — | `hash_password("Coach2026!")` | hash != "Coach2026!" | P0 | unit | ✅ Pasa |
| AUTH-UNIT-002 | Verificación de contraseña correcta | hash generado | `verify_password("Coach2026!", hash)` | `True` | P0 | unit | ✅ Pasa |
| AUTH-UNIT-003 | Verificación de contraseña incorrecta | hash generado | `verify_password("wrong", hash)` | `False` | P0 | unit | ✅ Pasa |
| AUTH-UNIT-004 | Token de acceso incluye tipo "access" | — | `create_access_token(data)` + `decode_token` | `payload["type"] == "access"` | P0 | unit | ✅ Pasa |
| AUTH-UNIT-005 | Token de refresh incluye tipo "refresh" | — | `create_refresh_token(data)` + `decode_token` | `payload["type"] == "refresh"` | P0 | unit | ✅ Pasa |
| AUTH-UNIT-006 | Token inválido lanza excepción JWT | — | `decode_token("esto.no.es.valido")` | `jwt.InvalidTokenError` | P0 | unit | ✅ Pasa |
| AUTH-UNIT-007 | Payload del access token preserva sub, role, club_ids | — | `create_access_token({"sub":"1","role":"coach","club_ids":[1]})` | payload coincide | P0 | unit | ✅ Pasa |

#### Tests de integración (`tests/test_auth.py`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| AUTH-INTG-001 | Login exitoso retorna access y refresh token | Stack levantado, seed aplicado | `POST /api/auth/login` con admin | 200, `access_token`, `refresh_token`, `token_type: bearer` | P0 | intg | ✅ Pasa |
| AUTH-INTG-002 | Login con contraseña incorrecta | Stack levantado | `POST /api/auth/login` password=wrong | 401 | P0 | intg | ✅ Pasa |
| AUTH-INTG-003 | Login con email desconocido | Stack levantado | `POST /api/auth/login` email inexistente | 401 | P0 | intg | ✅ Pasa |
| AUTH-INTG-004 | Refresh exitoso con token válido | Login previo | `POST /api/auth/refresh` con refresh_token | 200, nuevos tokens | P0 | intg | ✅ Pasa |
| AUTH-INTG-005 | Refresh con access_token falla | Login previo | `POST /api/auth/refresh` con access_token | 401 | P0 | intg | ✅ Pasa |
| AUTH-INTG-006 | /me retorna perfil del usuario autenticado | Token válido | `GET /api/auth/me` con Bearer token | 200, email y role correctos | P0 | intg | ✅ Pasa |
| AUTH-INTG-007 | /me sin token retorna 401/403 | — | `GET /api/auth/me` sin Authorization | 401 o 403 | P0 | intg | ✅ Pasa |
| AUTH-INTG-008 | /me con token falsificado retorna 401 | — | `GET /api/auth/me` con Bearer token-falso | 401 | P0 | intg | ✅ Pasa |

#### Casos de borde (`tests/test_auth.py`)

| ID | Descripción | Pasos | Resultado esperado | Prioridad | Estado |
|---|---|---|---|---|---|
| AUTH-INTG-009 | Login con email vacío | `POST /api/auth/login` email="" | 422 (validación) | P1 | ✅ Pasa |
| AUTH-INTG-010 | Login con body vacío | `POST /api/auth/login` sin body | 422 (validación) | P1 | ✅ Pasa |
| AUTH-INTG-011 | Token expirado retorna 401 | Crear token con `exp` en el pasado | 401 | P1 | ✅ Pasa |
| AUTH-INTG-012 | /me con coach retorna club_ids correcto | Token de coach | `GET /api/auth/me` | `club_ids` contiene al menos un club | P1 | ✅ Pasa |

---

### 4.2 Módulo Clubes — Backend

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| CLUBS-INTG-001 | Admin puede crear un club | Token admin | `POST /api/clubs` con nombre y ciudad | 201, club retornado con id | P0 | intg | ✅ Pasa |
| CLUBS-INTG-002 | Coach no puede crear un club | Token coach | `POST /api/clubs` | 403 | P0 | intg | ✅ Pasa |
| CLUBS-INTG-003 | Cualquier usuario autenticado puede listar clubes | Token coach | `GET /api/clubs` | 200, lista de clubes | P1 | intg | ✅ Pasa |
| CLUBS-INTG-004 | Sin token no se pueden listar clubes | — | `GET /api/clubs` | 401 o 403 | P0 | intg | ✅ Pasa (GET sin token) |
| CLUBS-INTG-005 | Admin puede actualizar un club | Token admin, club existente | `PATCH /api/clubs/{id}` con nuevo nombre | 200, nombre actualizado | P1 | intg | ✅ Pasa |
| CLUBS-INTG-006 | Coach no puede actualizar un club | Token coach | `PATCH /api/clubs/{id}` | 403 | P0 | intg | ✅ Pasa |
| CLUBS-INTG-007 | Actualizar club inexistente retorna 404 | Token admin | `PATCH /api/clubs/99999` | 404 | P1 | intg | ✅ Pasa |
| CLUBS-INTG-008 | Crear club con nombre duplicado | Token admin, club creado | `POST /api/clubs` mismo nombre | 201 (nombre no es único — solo `code` lo es) | P2 | intg | ✅ Pasa — comportamiento documentado |
| CLUBS-INTG-009 | Crear club con nombre vacío | Token admin | `POST /api/clubs` nombre="" | 422 | P1 | intg | ✅ Pasa |

---

### 4.3 Módulo Usuarios — Backend

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| USERS-INTG-001 | Admin puede crear un coach | Token admin | `POST /api/users` con role=coach | 201, usuario creado | P0 | intg | ✅ Pasa |
| USERS-INTG-002 | Coach puede crear un parent | Token coach | `POST /api/users` con role=parent | 201, usuario creado | P0 | intg | ✅ Pasa |
| USERS-INTG-003 | Coach no puede crear un admin | Token coach | `POST /api/users` con role=admin | 403 | P0 | intg | ✅ Pasa |
| USERS-INTG-004 | GET /api/users excluye usuarios con rol athlete | Token coach | `GET /api/users` | Lista no contiene usuarios role=athlete | P0 | intg | ✅ Pasa |
| USERS-INTG-005 | Coach solo ve usuarios de sus clubes | Token coach | `GET /api/users` | Solo usuarios del club del coach | P0 | intg | ✅ Pasa |
| USERS-INTG-006 | Admin puede actualizar cualquier usuario | Token admin, usuario existente | `PATCH /api/users/{id}` | 200, campo actualizado | P1 | intg | ✅ Pasa |
| USERS-INTG-007 | Coach puede actualizar parents de su club | Token coach, parent del mismo club | `PATCH /api/users/{id}` | 200 | P1 | intg | ✅ Pasa |
| USERS-INTG-008 | Coach no puede actualizar usuarios de otro club | Token coach | `PATCH /api/users/{id_otro_club}` | 403 | P0 | intg | ✅ Pasa |
| USERS-INTG-009 | Crear usuario con email duplicado | Usuario existente | `POST /api/users` mismo email | 409 o 422 | P1 | intg | ✅ Pasa |
| USERS-INTG-010 | Crear usuario con contraseña débil (<8 chars) | Token admin | `POST /api/users` password="123" | 422 | P2 | intg | ✅ Pasa |

---

### 4.4 Módulo Atletas — Backend

#### Tests de integración (`tests/test_athletes.py`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| ATHLETES-INTG-001 | Coach crea atleta masculino con categoría correcta | Token coach | `POST /api/athletes` birth=2013-06-15 sex=M | 201, `category="Pre-juvenil A"`, `age_decimal` calculado | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-002 | Coach crea atleta femenino con categoría correcta | Token coach | `POST /api/athletes` birth=2014-03-20 sex=F | 201, `category="Infantil B femenino"` | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-003 | Admin puede crear atletas | Token admin | `POST /api/athletes` | 201 | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-004 | Coach no puede crear atleta en club ajeno | Token coach | `POST /api/athletes` club_id=9999 | 403 | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-005 | Sin autenticación no se puede crear atleta | — | `POST /api/athletes` | 401 o 403 | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-006 | Coach lista atletas de sus clubes | Token coach | `GET /api/athletes` | 200, items con `age_decimal` y `category` | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-007 | Coach filtra atletas por club propio | Token coach | `GET /api/athletes?club_id={propio}` | 200, todos los items tienen club_id correcto | P1 | intg | ✅ Pasa |
| ATHLETES-INTG-008 | Coach no puede filtrar por club ajeno | Token coach | `GET /api/athletes?club_id=9999` | 403 | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-009 | Todos los atletas listados tienen campos computados | Token coach | `GET /api/athletes` | Cada item tiene `age_decimal != null` y `category != null` | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-010 | GET detalle de atleta existente | Token coach, atleta creado | `GET /api/athletes/{id}` | 200, `latest_anthropometry` presente | P0 | intg | ✅ Pasa |
| ATHLETES-INTG-011 | GET atleta inexistente retorna 404 | Token coach | `GET /api/athletes/99999` | 404 | P1 | intg | ✅ Pasa |
| ATHLETES-INTG-012 | PATCH actualiza nombre del atleta | Token coach, atleta existente | `PATCH /api/athletes/{id}` `{"first_name": "Nuevo"}` | 200, nombre actualizado | P1 | intg | ✅ Pasa |
| ATHLETES-INTG-013 | PATCH atleta inexistente retorna 404 | Token coach | `PATCH /api/athletes/99999` | 404 | P1 | intg | ✅ Pasa |

#### Casos de borde (`tests/test_athletes.py`)

| ID | Descripción | Pasos | Resultado esperado | Prioridad | Estado |
|---|---|---|---|---|---|
| ATHLETES-INTG-014 | Atleta creado sin `years_in_club` usa valor por defecto | `POST /api/athletes` sin ese campo | 201, `years_in_club` con valor por defecto | P2 | ✅ Pasa |
| ATHLETES-INTG-015 | Crear atleta con fecha futura | `birth_date` = 2030-01-01 | 422 | P1 | ✅ Pasa |
| ATHLETES-INTG-016 | Crear atleta con sexo inválido | `sex` = "X" | 422 | P1 | ✅ Pasa |
| ATHLETES-INTG-017 | Creación de atleta crea user+club_member en misma transacción | Crear atleta, verificar tables | `SELECT * FROM users WHERE role='athlete'` muestra el nuevo usuario | P0 | ✅ Pasa |

---

### 4.5 Módulo Antropometría + PHV — Backend

#### Tests de integración (`tests/test_athletes.py`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| ANTHRO-INTG-001 | Crear registro de antropometría con cálculo PHV completo | Token coach, atleta existente | `POST /api/athletes/{id}/anthropometry` con datos válidos | 201, `maturation_status` en Pre/Circa/Post-PHV, `maturity_offset` y `age_at_phv` presentes | P0 | intg | ✅ Pasa |
| ANTHRO-INTG-002 | `leg_length_cm` = `standing_height` - `sitting_height` | Token coach | Crear registro weight=45.5, standing=155.0, sitting=73.0 | `leg_length_cm = "82.0"` | P0 | intg | ✅ Pasa |
| ANTHRO-INTG-003 | `training_implications` no es null | Token coach | Crear cualquier registro válido | `training_implications` es string no vacío | P0 | intg | ✅ Pasa |
| ANTHRO-INTG-004 | Crear registro para atleta inexistente retorna 404 | Token coach | `POST /api/athletes/99999/anthropometry` | 404 | P1 | intg | ✅ Pasa |
| ANTHRO-INTG-005 | Listar historial retorna lista (puede estar vacía) | Token coach, atleta existente | `GET /api/athletes/{id}/anthropometry` | 200, array JSON | P0 | intg | ✅ Pasa |
| ANTHRO-INTG-006 | Historial está ordenado por fecha descendente | Token coach, ≥2 registros | Crear registros con fechas distintas, listar | Primer elemento tiene fecha más reciente | P1 | intg | ✅ Pasa |
| ANTHRO-INTG-007 | Detalle del atleta incluye la antropometría más reciente | Token coach, registro creado | `GET /api/athletes/{id}` después de crear registro | `latest_anthropometry.evaluation_date` coincide con la última creada | P0 | intg | ✅ Pasa |

#### Tests unitarios PHV Mirwald (`tests/test_phv.py`)

| ID | Descripción | Entradas | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|
| PHV-UNIT-001 | Varón 10.5 años Pre-PHV | M, 10.5y, 35kg, 140cm, 73cm | `maturation_status = "Pre-PHV"`, `leg_length_cm = 67.0` | P0 | unit | ✅ Pasa |
| PHV-UNIT-002 | Varón 16 años Post-PHV | M, 16y, 65kg, 175cm, 85cm | `maturation_status = "Post-PHV"` | P0 | unit | ✅ Pasa |
| PHV-UNIT-003 | Mujer 12 años retorna estado válido | F, 12y, 42kg, 155cm, 80cm | status en {Pre-PHV, Circa-PHV, Post-PHV} | P0 | unit | ✅ Pasa |
| PHV-UNIT-004 | Longitud de pierna es `standing - sitting` | M, 12y, 45kg, 155cm, 73cm | `leg_length_cm = 82.0`, `leg_sitting_ratio = round(82/73, 4)` | P0 | unit | ✅ Pasa |
| PHV-UNIT-005 | `age_at_phv = round(age - maturity_offset, 2)` | M, 12.5y, 45kg, 155cm, 73cm | Fórmula verificada programáticamente | P0 | unit | ✅ Pasa |

#### Casos de borde PHV (`tests/test_phv.py`)

| ID | Descripción | Entradas | Resultado esperado | Prioridad | Estado |
|---|---|---|---|---|---|
| PHV-UNIT-006 | Boundary: `maturity_offset = -1.0` exacto | Valores que produzcan MO exactamente -1.0 | `maturation_status = "Circa-PHV"` | P0 | ✅ Pasa |
| PHV-UNIT-007 | Boundary: `maturity_offset = +1.0` exacto | Valores que produzcan MO exactamente +1.0 | `maturation_status = "Circa-PHV"` | P0 | ✅ Pasa |
| PHV-UNIT-008 | Fórmula masculina y femenina producen resultados distintos | Mismos datos numéricos, sexo diferente | `maturity_offset` masculino != femenino | P0 | ✅ Pasa |
| PHV-UNIT-009 | Datos de entrada negativos | weight=-1 | Excepción o resultado rechazado | P1 | ✅ Pasa |
| PHV-UNIT-010 | `sitting_height > standing_height` (imposible físicamente) | sitting=90, standing=80 | Excepción o `leg_length <= 0` manejado | P1 | ✅ Pasa |

---

### 4.6 Módulo Categorías FCC 2026 — Backend (`tests/test_phv.py`)

| ID | Descripción | Entradas | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|
| CAT-UNIT-001 | Pre-juvenil A masculino (2013) | year=2013, sex=M | "Pre-juvenil A" | P0 | unit | ✅ Pasa |
| CAT-UNIT-002 | Pre-juvenil A femenino (2012) | year=2012, sex=F | "Pre-juvenil A femenino" | P0 | unit | ✅ Pasa |
| CAT-UNIT-003 | Infantil A masculino (2017) | year=2017, sex=M | "Infantil A" | P0 | unit | ✅ Pasa |
| CAT-UNIT-004 | Infantil B femenino (2014) | year=2014, sex=F | "Infantil B femenino" | P0 | unit | ✅ Pasa |
| CAT-UNIT-005 | Pre-Infantil B (2019-2018) | year=2019, sex=M; year=2018, sex=F | "Pre-Infantil B" / "Pre-Infantil B femenino" | P0 | unit | ✅ Pasa |
| CAT-UNIT-006 | Teteros (2022-2023) | year=2022, sex=M; year=2023, sex=F | "Teteros" | P0 | unit | ✅ Pasa |
| CAT-UNIT-007 | Junior (2009 masculino, 2008 femenino) | year=2009, sex=M | "Junior" | P1 | unit | ✅ Pasa |
| CAT-UNIT-008 | Edad decimal con fecha de referencia explícita | birth=2013-06-15, ref=2026-04-14 | 12.5 < age < 13.0 | P0 | unit | ✅ Pasa |
| CAT-UNIT-009 | Edad decimal exacta a un año | birth=2016-01-01, ref=2026-01-01 | abs(age - 10.0) < 0.02 | P0 | unit | ✅ Pasa |
| CAT-UNIT-010 | Edad decimal usa fecha actual por defecto | birth=2016-01-01 sin ref | age > 0 | P1 | unit | ✅ Pasa |

---

### 4.7 Frontend — Auth Store y Auth Flow

#### Tests unitarios Vitest (`src/store/auth.store.test.ts`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| AUTH-FE-001 | Estado inicial del store tiene isAuthenticated=false | — | `useAuthStore.getState()` | Todos los campos en null/false | P0 | unit | ✅ Pasa |
| AUTH-FE-002 | Login exitoso guarda tokens y user en store | Mock API login/getMe | `await store.login(email, pass)` | `accessToken`, `refreshToken`, `user` cargados; `isAuthenticated=true` | P0 | unit | ✅ Pasa |
| AUTH-FE-003 | Login fallido no modifica estado y propaga error | Mock API rechaza | `await store.login()` | Error propagado, `isAuthenticated=false`, `accessToken=null` | P0 | unit | ✅ Pasa |
| AUTH-FE-004 | isLoading vuelve a false después del login (éxito y fallo) | — | `await store.login()` | `isLoading=false` en ambos casos | P1 | unit | ✅ Pasa |
| AUTH-FE-005 | Logout limpia todos los campos del store | Sesión activa simulada | `store.logout()` | Todos los campos en null/false | P0 | unit | ✅ Pasa |
| AUTH-FE-006 | refreshSession actualiza tokens sin llamar fetchMe si hay user | Token válido, user cargado | `await store.refreshSession()` | Tokens actualizados, getMe no llamado | P1 | unit | ✅ Pasa |
| AUTH-FE-007 | refreshSession sin refreshToken hace logout y lanza error | refreshToken=null | `await store.refreshSession()` | Error lanzado, `isAuthenticated=false` | P0 | unit | ✅ Pasa |
| AUTH-FE-008 | refreshSession fallida hace logout | Mock API rechaza | `await store.refreshSession()` | `isAuthenticated=false`, `user=null` | P0 | unit | ✅ Pasa |

#### Casos de privacidad del store

| ID | Descripción | Pasos | Resultado esperado | Prioridad | Estado |
|---|---|---|---|---|---|
| AUTH-FE-009 | Tokens se guardan en sessionStorage (no localStorage) | Login exitoso | `sessionStorage.setItem` llamado; `localStorage.setItem` NO llamado | P0 | 🚧 Parcial — mock configurado en Vitest; verificación E2E real en E2E-001 |

---

### 4.8 Frontend — Cálculo PHV en tiempo real

#### Tests unitarios Vitest (`src/lib/phv.test.ts`)

| ID | Descripción | Entradas | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|
| PHV-FE-001 | Inputs inválidos (0 o negativos) retornan null | Cualquier campo = 0 o negativo | `calculatePHV(...)` retorna `null` | P0 | unit | ✅ Pasa |
| PHV-FE-002 | `legLengthCm = standingHeight - sittingHeight` | standing=155, sitting=73 | `legLengthCm = 82.0` | P0 | unit | ✅ Pasa |
| PHV-FE-003 | Varón 10.5y es Pre-PHV | M, 10.5y, 35kg, 140cm, 73cm | `maturationStatus = Pre-PHV` | P0 | unit | ✅ Pasa |
| PHV-FE-004 | Varón 16y es Post-PHV | M, 16y, 65kg, 175cm, 85cm | `maturationStatus = Post-PHV` | P0 | unit | ✅ Pasa |
| PHV-FE-005 | Atleta femenina 12y retorna estado válido | F, 12y, 42kg, 155cm, 80cm | status en {Pre-PHV, Circa-PHV, Post-PHV} | P0 | unit | ✅ Pasa |
| PHV-FE-006 | `ageAtPhv = round(ageDecimal - maturityOffset, 2)` | M, 12.5y, 45kg, 155cm, 73cm | Fórmula verificada | P0 | unit | ✅ Pasa |
| PHV-FE-007 | Fórmulas masculina y femenina son distintas | Mismos datos, sexo diferente | `maturityOffset` difiere | P0 | unit | ✅ Pasa |
| PHV-FE-008 | Resultado incluye `trainingImplications` para Pre-PHV | Caso Pre-PHV | `trainingImplications` contiene "juego" | P1 | unit | ✅ Pasa |
| PHV-FE-009 | Resultado incluye `trainingImplications` para Post-PHV | Caso Post-PHV | `trainingImplications` contiene "fuerza progresiva" | P1 | unit | ✅ Pasa |
| PHV-FE-010 | legLength = 0 (sentado = de pie) retorna null | standing=72, sitting=72 | `null` | P0 | unit | ✅ Pasa |
| PHV-FE-011 | legLength negativo (sentado > de pie) retorna null | standing=70, sitting=72 | `null` | P0 | unit | ✅ Pasa |

---

### 4.9 Frontend — Formulario de Atletas

#### Tests de componente Vitest (`src/components/athletes/AthleteForm.test.tsx`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| FORM-FE-001 | Modo create muestra botón "Crear atleta" | — | `render(<AthleteForm mode="create" .../>)` | Botón visible | P0 | unit | ✅ Pasa |
| FORM-FE-002 | Modo create muestra todos los campos requeridos | — | `render(...)` | Nombres, Apellidos, Fecha nac., Sexo, Años en club | P0 | unit | ✅ Pasa |
| FORM-FE-003 | Selector de sexo tiene opciones M y F | — | `render(...)` | `<select>` con opciones M y F | P0 | unit | ✅ Pasa |
| FORM-FE-004 | Modo edit muestra botón "Guardar cambios" | Atleta existente | `render(<AthleteForm mode="edit" initialValues={athlete}/>)` | Botón "Guardar cambios" visible | P0 | unit | ✅ Pasa |
| FORM-FE-005 | Modo edit prelllena campos con valores iniciales | Atleta con nombre "Sebastián" | `render(...)` | `getByDisplayValue("Sebastián")` encontrado | P0 | unit | ✅ Pasa |
| FORM-FE-006 | Fecha de nacimiento deshabilitada en modo edit | Atleta existente | `render(...)` en modo edit | Input fecha deshabilitado | P1 | unit | ✅ Pasa |
| FORM-FE-007 | Enviar formulario vacío muestra validaciones | — | Click en "Crear atleta" sin datos | Mensajes de error visibles | P0 | unit | ✅ Pasa |
| FORM-FE-008 | Enviar formulario válido llama a onSubmit con datos | — | Completar campos + click submit | `onSubmit` llamado con payload correcto | P0 | unit | ✅ Pasa |

---

### 4.10 Frontend — Historial y Gráficas

#### Tests de componente Vitest (`src/components/athletes/AnthropometryHistory.test.tsx` y `GrowthCharts.test.tsx`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| HIST-FE-001 | Historial vacío muestra mensaje informativo | Sin registros | `render(<AnthropometryHistory records={[]} />)` | Texto "sin registros" o similar | P1 | unit | ✅ Pasa |
| HIST-FE-002 | Historial con registros muestra tabla/lista | 2+ registros mock | `render(<AnthropometryHistory records={[...]} />)` | Datos visibles | P0 | unit | ✅ Pasa |
| HIST-FE-003 | Gráficas se renderizan sin errores con datos válidos | Datos mock con ≥2 puntos | `render(<GrowthCharts records={[...]} />)` | Sin excepciones, contenedor visible | P0 | unit | ✅ Pasa |
| HIST-FE-004 | Gráficas no fallan con lista vacía | Sin datos | `render(<GrowthCharts records={[]} />)` | Sin excepciones | P1 | unit | ✅ Pasa |

---

### 4.11 Frontend — Hooks TanStack Query

#### Tests de hooks (`src/hooks/athletes/useAthletes.test.ts`)

| ID | Descripción | Precondición | Pasos | Resultado esperado | Prioridad | Tipo | Estado |
|---|---|---|---|---|---|---|---|
| HOOKS-FE-001 | `useAthletes` retorna datos cuando la API responde | Mock API exitoso | `renderHook(() => useAthletes())` | `data` contiene lista de atletas | P0 | unit | ✅ Pasa |
| HOOKS-FE-002 | `useAthlete` retorna detalle del atleta por id | Mock API exitoso | `renderHook(() => useAthlete(1))` | `data` contiene `latest_anthropometry` | P0 | unit | ✅ Pasa |
| HOOKS-FE-003 | `useCreateAthlete` llama a `createAthlete` al mutar | Mock API exitoso | `hook.mutate(payload)` + waitFor | `createAthlete` llamado con datos correctos | P0 | unit | ✅ Pasa |
| HOOKS-FE-004 | `useUpdateAthlete` llama a `updateAthlete` al mutar | Mock API exitoso | `hook.mutate({id, data})` + waitFor | `updateAthlete` llamado con id y datos | P1 | unit | ✅ Pasa |
| HOOKS-FE-005 | Hooks en estado error cuando la API falla | Mock API rechaza | `renderHook(...)` + waitFor | `isError = true` | P1 | unit | ✅ Pasa |

---

## 5. Pruebas E2E con Playwright

Los flujos E2E se ejecutan con Playwright. Los specs están escritos y listos — requieren `docker compose up` para ejecutarse.

### 5.1 Configuración de Playwright

```
Base URL: http://localhost:3000
Browser: Chromium (default)
Credenciales: usar seed data (sección 2.4)
Prerequisito: `docker compose up` corriendo
Config: frontend/playwright.config.ts
Specs: frontend/e2e/{auth,athletes,anthropometry,history}.spec.ts
```

**Para activar:**
```bash
cd frontend
pnpm install                        # instala @playwright/test ^1.50.0
pnpm exec playwright install chromium
docker compose up                   # en raíz del proyecto
pnpm test:e2e
```

### 5.1b Estado de implementación E2E

| ID | Archivo | Estado |
|---|---|---|
| E2E-001 | `e2e/auth.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-002 | `e2e/auth.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-003 | `e2e/athletes.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-004 | `e2e/athletes.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-005 | `e2e/anthropometry.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-006 | `e2e/anthropometry.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-007 | `e2e/history.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-008 | `e2e/history.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-009 | `e2e/auth.spec.ts` | ⏳ Escrito — requiere Docker |
| E2E-010 | `e2e/auth.spec.ts` | ⏳ Escrito — requiere Docker |

### 5.2 Flujos E2E críticos

#### FLUJO E2E-001 — Login y acceso al dashboard

| Campo | Valor |
|---|---|
| ID | E2E-001 |
| Prioridad | P0 |
| Duración estimada | 2 min |

**Pasos:**
1. Navegar a `http://localhost:3000/login`
2. Ingresar email `entrenador@trochyruta.com` y contraseña `Coach2026!`
3. Click en "Iniciar sesión"
4. Verificar redirección al dashboard
5. Verificar que el nombre del usuario aparece en el header

**Resultado esperado:** Usuario autenticado y en el dashboard. Token guardado en sessionStorage, no en localStorage.

---

#### FLUJO E2E-002 — Login fallido muestra error

| Campo | Valor |
|---|---|
| ID | E2E-002 |
| Prioridad | P0 |
| Duración estimada | 1 min |

**Pasos:**
1. Navegar a `/login`
2. Ingresar credenciales incorrectas
3. Click en "Iniciar sesión"
4. Verificar mensaje de error en pantalla

**Resultado esperado:** Permanece en `/login`, mensaje de error visible, sin token guardado.

---

#### FLUJO E2E-003 — Crear atleta masculino y verificar categoría

| Campo | Valor |
|---|---|
| ID | E2E-003 |
| Prioridad | P0 |
| Duración estimada | 3 min |

**Pasos:**
1. Login como coach (`entrenador@trochyruta.com` / `Coach2026!`)
2. Navegar a la sección de atletas
3. Click en "Crear atleta"
4. Completar formulario:
   - Nombres: `Santiago`
   - Apellidos: `López`
   - Fecha de nacimiento: `2013-06-15`
   - Sexo: `M`
   - Años en el club: `2`
5. Click en "Crear atleta"

**Resultado esperado:** Atleta creado y visible en la lista. La fila muestra `category = "Pre-juvenil A"` y `age_decimal` calculado.

---

#### FLUJO E2E-004 — Crear atleta femenino y verificar categoría femenina

| Campo | Valor |
|---|---|
| ID | E2E-004 |
| Prioridad | P0 |
| Duración estimada | 3 min |

**Pasos:**
1. Login como coach
2. Crear atleta con `birth_date=2014-03-20`, `sex=F`

**Resultado esperado:** `category = "Infantil B femenino"`.

---

#### FLUJO E2E-005 — Registrar medición antropométrica y ver PHV calculado

| Campo | Valor |
|---|---|
| ID | E2E-005 |
| Prioridad | P0 |
| Duración estimada | 5 min |

**Pasos:**
1. Login como coach
2. Seleccionar un atleta de la lista
3. Ir a la vista detalle del atleta
4. Click en "Nueva medición" o "Registrar antropometría"
5. Completar el formulario:
   - Fecha: `2026-04-14`
   - Peso: `45.5 kg`
   - Talla de pie: `155.0 cm`
   - Talla sentado: `73.0 cm`
   - Envergadura: `157.0 cm`
   - Mesociclo: `3`
6. Click en "Guardar"
7. Verificar que el resultado muestra:
   - `Longitud de pierna: 82.0 cm`
   - Estado de maduración: uno de Pre-PHV / Circa-PHV / Post-PHV
   - `maturity_offset` y `age_at_phv` visibles

**Resultado esperado:** Registro guardado, estado PHV calculado y mostrado en pantalla. La vista detalle del atleta actualiza `latest_anthropometry`.

---

#### FLUJO E2E-006 — Previsualización PHV en tiempo real durante el formulario

| Campo | Valor |
|---|---|
| ID | E2E-006 |
| Prioridad | P1 |
| Duración estimada | 3 min |

**Pasos:**
1. Login como coach
2. Abrir formulario de nueva medición para un atleta masculino
3. Ingresar progresivamente: peso 45.5, talla pie 155.0, talla sentado 73.0
4. Verificar que la sección de "Vista previa PHV" se actualiza sin necesidad de enviar el formulario

**Resultado esperado:** El cálculo PHV se muestra en tiempo real mientras se completan los campos numéricos.

---

#### FLUJO E2E-007 — Historial de mediciones ordenado cronológicamente

| Campo | Valor |
|---|---|
| ID | E2E-007 |
| Prioridad | P1 |
| Duración estimada | 5 min |

**Pasos:**
1. Login como coach
2. Seleccionar atleta con ≥2 mediciones
3. Navegar a la sección de historial
4. Verificar orden de las filas

**Resultado esperado:** Las mediciones aparecen con la más reciente primero.

---

#### FLUJO E2E-008 — Gráficas de crecimiento se renderizan con datos

| Campo | Valor |
|---|---|
| ID | E2E-008 |
| Prioridad | P1 |
| Duración estimada | 4 min |

**Pasos:**
1. Login como coach
2. Navegar a la vista detalle de un atleta con ≥2 mediciones
3. Localizar la sección de gráficas (Recharts)

**Resultado esperado:** Las gráficas se renderizan sin errores de consola. Se pueden visualizar curvas de peso, talla y maturity_offset a lo largo del tiempo.

---

#### FLUJO E2E-009 — Acceso denegado a rutas protegidas sin login

| Campo | Valor |
|---|---|
| ID | E2E-009 |
| Prioridad | P0 |
| Duración estimada | 2 min |

**Pasos:**
1. Sin estar autenticado, navegar directamente a `/athletes`
2. Verificar comportamiento

**Resultado esperado:** Redirección automática a `/login`. No se expone contenido protegido.

---

#### FLUJO E2E-010 — Logout limpia la sesión

| Campo | Valor |
|---|---|
| ID | E2E-010 |
| Prioridad | P0 |
| Duración estimada | 2 min |

**Pasos:**
1. Login como coach
2. Click en el botón de logout
3. Verificar redirección a `/login`
4. Intentar navegar a `/athletes`

**Resultado esperado:** Redirigido a `/login`. `sessionStorage` limpiado.

---

## 6. Pruebas de seguridad y privacidad

### 6.1 Deuda de seguridad conocida (documentada — no bloquea QA funcional)

Los siguientes ítems son riesgos conocidos que deben documentarse en el registro de defectos pero **no** bloquean la aceptación de Fase 1:

| ID Riesgo | Severidad | Descripción | Validación QA |
|---|---|---|---|
| CRIT-02 | Crítico | Refresh tokens sin lista de revocación — un token robado no puede invalidarse | Verificar que `POST /api/auth/refresh` NO comprueba ninguna blacklist |
| HIGH-01 | Alto | Sin rate limiting en `/api/auth/login` — vulnerable a fuerza bruta | Enviar 100 requests seguidas y verificar que no hay throttling |
| HIGH-03 | Alto | `club_ids` embebidos en JWT payload — manipulable si el secreto se filtra | Inspecionar el payload del JWT decodificado (base64) |
| MED-02 | Medio | `GET /api/auth/me` puede exponer campos internos en la respuesta | Revisar el schema de `MeResponse` vs campos devueltos |
| MED-04 | Medio | Access y refresh tokens usan el mismo secreto — compromiso bilateral | Comparar la clave usada en `create_access_token` y `create_refresh_token` |
| LOW-02 | Bajo | Sin endpoint `/logout` — los tokens no expiran antes de su TTL natural | Verificar que no existe `POST /api/auth/logout` |

### 6.2 Casos de prueba de seguridad (`tests/test_security.py`)

| ID | Descripción | Pasos | Resultado esperado | Prioridad | Estado |
|---|---|---|---|---|---|
| SEC-001 | SQL Injection en campo email del login | `POST /api/auth/login` email=`"' OR '1'='1"` | 401 o 422, sin error de DB expuesto | P0 | ✅ Pasa |
| SEC-002 | XSS en nombre de atleta | Crear atleta con `first_name="<script>alert(1)</script>"` | 422 o cadena almacenada sin ejecutar | P0 | ✅ Pasa |
| SEC-003 | Token de coach no puede acceder a rutas de admin | Token de coach | `POST /api/clubs` | 403 | P0 | ✅ Pasa |
| SEC-004 | Token expirado no da acceso | Token con `exp` en el pasado | 401 en cualquier endpoint protegido | P0 | ✅ Pasa |
| SEC-005 | Token manipulado (firma inválida) no da acceso | Modificar payload del JWT | 401 | P0 | ✅ Pasa |
| SEC-006 | CORS no permite orígenes no autorizados | Request desde origen no listado | Respuesta bloqueada o sin `Access-Control-Allow-Origin` | P1 | ⏳ Pendiente — no testeable con httpx ASGI (requiere cliente HTTP real o E2E) |
| SEC-007 | Parámetros de URL no producen path traversal | `GET /api/athletes/../users` | 404 o 422, no acceso no autorizado | P1 | ✅ Pasa |
| SEC-008 | Parent no puede ver atletas de otros coaches | Token parent | `GET /api/athletes` | Solo ve sus propios atletas o 403 | P0 | ✅ Pasa |

### 6.3 Casos de prueba de privacidad

| ID | Descripción | Pasos | Resultado esperado | Prioridad | Estado |
|---|---|---|---|---|---|
| PRIV-001 | Tokens guardados en sessionStorage (no localStorage) | Login desde navegador real | DevTools > Application > sessionStorage tiene tokens; localStorage NO | P0 | ⏳ Escrito en E2E-001 — requiere Docker |
| PRIV-002 | Logs del servidor no exponen fechas de nacimiento ni datos médicos | Revisar stdout del servidor durante operaciones con atletas | No aparece `birth_date`, `weight_kg`, ni datos de PHV en logs | P0 | ✅ Pasa (`tests/test_privacy.py`) |
| PRIV-003 | Respuesta de error no expone stack trace en producción | Enviar request inválido con `DEBUG=false` | Error body no contiene traceback de Python | P1 | ✅ Pasa (`tests/test_privacy.py`) |
| PRIV-004 | Datos de atletas menores no aparecen en commits de git | Revisar historial de commits | No hay valores reales de atletas menores en diffs | P0 | ⏳ Revisión manual — solo seed data ficticia en repo |
| PRIV-005 | El endpoint GET /api/users no devuelve datos de atletas | Token coach | `GET /api/users` | Ningún item tiene `role=athlete` | P0 | ✅ Pasa (`tests/test_privacy.py`) |

---

## 7. Casos de borde y datos límite

### 7.1 Boundary values — Fórmula PHV Mirwald

| Parámetro | Mínimo válido | Máximo esperado | Valor inválido | Comportamiento esperado |
|---|---|---|---|---|
| age_decimal | > 0 | ~20 años | 0 o negativo | Rechazo / null |
| weight_kg | > 0 kg | ~120 kg | 0 o negativo | Rechazo / null |
| standing_height_cm | > 0 cm | ~220 cm | 0 o negativo | Rechazo / null |
| sitting_height_cm | > 0 cm y < standing | ~130 cm | 0, negativo, o > standing | Rechazo / null |
| leg_length_cm | > 0 | ~120 cm | 0 (sentado = de pie) | Rechazo / null |
| maturity_offset | sin límite teórico | — | — | Clasificación según rangos |

### 7.2 Boundary values — Categorías FCC 2026

| Año límite | Sexo | Categoría esperada |
|---|---|---|
| 2022 (inicio Teteros) | M | Teteros |
| 2023 (inicio Teteros) | F | Teteros |
| 2019 (inicio Pre-Infantil B) | M | Pre-Infantil B |
| 2018 (fin Pre-Infantil B) | F | Pre-Infantil B femenino |
| 2017 (inicio Infantil A) | M | Infantil A |
| 2016 (fin Infantil A) | F | Infantil A femenino |
| 2013 (inicio Pre-juvenil A) | M | Pre-juvenil A |
| 2012 (fin Pre-juvenil A) | F | Pre-juvenil A femenino |

### 7.3 Boundary values — API endpoints

| Escenario | Endpoint | Resultado esperado |
|---|---|---|
| `birth_date` futuro | `POST /api/athletes` | 422 |
| `birth_date` inválido (texto) | `POST /api/athletes` | 422 |
| `sex` con valor no permitido | `POST /api/athletes` | 422 |
| `club_id` no entero | `POST /api/athletes` | 422 |
| `weight_kg` con demasiados decimales | `POST /api/athletes/{id}/anthropometry` | Almacenado con precisión definida o 422 |
| `evaluation_date` futuro (mayor a hoy) | `POST /api/athletes/{id}/anthropometry` | 422 o aceptado (documentar comportamiento) |
| Paginación: `page=0` o `page=-1` | `GET /api/athletes` | 422 o primer página |
| Paginación: `per_page=1000` | `GET /api/athletes` | Limitado a máximo del servidor |

### 7.4 Concurrencia y estado

| Escenario | Descripción | Resultado esperado |
|---|---|---|
| Doble submit del formulario | Hacer doble click en "Crear atleta" | Solo un atleta creado (botón deshabilitado tras primer click) |
| Crear atleta mientras token está por expirar | Timing cerca del TTL | Refresh automático o error manejable |
| Actualizar atleta con datos sin cambios | `PATCH` con mismo valor | 200 idempotente, sin error |

---

## 8. Matriz de trazabilidad

Mapeo entre los pasos del workflow de Fase 1 (`docs/03-fase1/workflow.md`) y los casos de prueba:

| Paso Workflow | Descripción | Casos de Prueba Relacionados |
|---|---|---|
| Paso 1 | Scaffolding FastAPI | AUTH-INTG-001 (API responde) |
| Paso 2 | Modelos + migración + seed | ATHLETES-INTG-017 (transacción atómica), CAT-UNIT-001 a 010 |
| Paso 3 | Autenticación JWT | AUTH-UNIT-001 a 007, AUTH-INTG-001 a 012, AUTH-FE-001 a 009 |
| Paso 4 | CRUD clubes y usuarios | CLUBS-INTG-001 a 009, USERS-INTG-001 a 010 |
| Paso 5 | CRUD atletas + PHV Mirwald | ATHLETES-INTG-001 a 017, ANTHRO-INTG-001 a 007, PHV-UNIT-001 a 010 |
| Paso 6 | Frontend scaffolding + auth | AUTH-FE-001 a 009, E2E-001, E2E-002, E2E-009, E2E-010 |
| Paso 7 | Frontend CRUD atletas | FORM-FE-001 a 008, HOOKS-FE-001 a 005, E2E-003, E2E-004 |
| Paso 8 | Frontend antropometría + PHV | PHV-FE-001 a 011, HIST-FE-001 a 004, E2E-005, E2E-006, E2E-007, E2E-008 |

---

## 9. Criterios de aceptación de Fase 1

Para declarar Fase 1 como **aprobada** deben cumplirse todos los criterios P0 de la siguiente tabla:

### 9.1 Criterios obligatorios (P0)

| # | Criterio | Métrica | Estado |
|---|---|---|---|
| 1 | Todos los tests backend pasan | `pytest` 0 failures | ✅ 130/130 pasan |
| 2 | Todos los tests frontend pasan | `vitest --run` 0 failures | ✅ 225/225 pasan |
| 3 | Los endpoints documentados retornan el código HTTP correcto | 100% de endpoints cumplen contratos de rol (RBAC) | ✅ Cubiertos por test_clubs, test_users, test_athletes, test_security |
| 4 | Fórmula PHV Mirwald produce resultados correctos para los casos de referencia | PHV-UNIT-001 a 005 pasan + PHV-FE-001 a 006 pasan | ✅ Pasa |
| 5 | Categorías FCC 2026 son correctas para los 10 casos de la tabla CAT | CAT-UNIT-001 a 010 pasan | ✅ Pasa (27 combinaciones en parametrize) |
| 6 | La transacción de creación de atleta es atómica | ATHLETES-INTG-017 pasa | ✅ Pasa |
| 7 | Tokens se almacenan en sessionStorage | PRIV-001 pasa | ⏳ E2E-001 escrito — requiere Docker para ejecutar |
| 8 | Sin autenticación no se accede a recursos protegidos | E2E-009 pasa, AUTH-INTG-007 pasa | 🚧 AUTH-INTG-007 ✅ — E2E-009 ⏳ requiere Docker |
| 9 | El flujo completo login → crear atleta → registrar antropometría → ver PHV funciona end-to-end | E2E-001 + E2E-003 + E2E-005 pasan sin errores de consola | ⏳ Specs escritos — requieren Docker |
| 10 | Los datos de atletas (birth_date, weight, talla) no aparecen en logs de servidor | PRIV-002 pasa | ✅ Pasa (`test_privacy.py`) |

### 9.2 Criterios deseables (P1)

| # | Criterio | Métrica |
|---|---|---|
| 1 | Cobertura de líneas en `backend/app/services/` ≥ 90% | Reporte de cobertura pytest |
| 2 | Cobertura en `frontend/src/lib/` ≥ 90% | Reporte de cobertura Vitest |
| 3 | Cobertura en `frontend/src/store/` ≥ 85% | Reporte de cobertura Vitest |
| 4 | Flujos E2E P1 (E2E-006 a E2E-008) pasan | Playwright sin failures |
| 5 | Todos los casos de borde P1 de sección 7 validados | 0 fallos inesperados |
| 6 | Deuda de seguridad CRIT-02 y HIGH-01 documentada en registro de defectos | Issues creados con severidad correcta |

### 9.3 No-go conditions (bloquean la aceptación)

- Cualquier test P0 falla
- Se descubre que datos de menores se exponen en logs o respuestas de error
- La fórmula PHV produce estados incorrectos para los casos de referencia del backend
- Cualquier endpoint RBAC-crítico permite acceso no autorizado (ej: coach accede a clubes de otro coach, o público accede a /api/athletes)

---

## 10. Riesgos y mitigaciones

| ID | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| R-01 | La fórmula PHV frontend (`lib/phv.ts`) diverge del backend en casos extremos (flotantes, redondeo) | Media | Alto | Verificar los mismos 5 casos de referencia en ambos lados (PHV-UNIT vs PHV-FE). Si divergen, usar backend como fuente de verdad. |
| R-02 | Categorías FCC 2026 discrepan entre frontend ("Teteros con pedales") y backend ("Teteros") | Baja (conocida) | Medio | El frontend usa nombre extendido. Documentar la diferencia en el registro. No es un bug si la decisión es intencional. |
| R-03 | Tests de integración backend son stateful (orden de ejecución importa) | Alta | Medio | Los tests en `test_athletes.py` dependen del seed. Ejecutar siempre con `docker compose up` para garantizar estado conocido. Considerar fixtures de limpieza por test. |
| R-04 | E2E tests son frágiles ante cambios de UI | Media | Medio | Usar selectores semánticos (`role`, `aria-label`, `data-testid`) en Playwright. Evitar selectores CSS de estructura. |
| R-05 | Refresh token sin revocación (CRIT-02) puede generar sesiones zombi en pruebas | Baja | Bajo | Reiniciar el stack Docker entre sesiones de prueba. Documentar el riesgo en el registro de deuda. |
| R-06 | Datos de menores en seed pueden aparecer en evidencia de QA (capturas, logs) | Media | Alto | Usar exclusivamente los datos del seed (ficticios) para pruebas. Nunca cargar datos de atletas reales en el entorno de QA. |
| R-07 | El stack Docker tarda en aplicar migraciones + seed en el primer `up` | Baja | Bajo | Esperar a que los logs del backend muestren "Application startup complete" antes de ejecutar pruebas. |
| R-08 | Componentes React que usan Recharts pueden fallar en jsdom por SVG limitado | Media | Bajo | Para GrowthCharts.test.tsx, mockear Recharts o verificar solo que el contenedor existe, no los paths SVG internos. |

---

## 11. Apéndice — Comandos de referencia rápida

```bash
# Levantar stack completo
docker compose up

# Correr todos los tests
cd backend && pytest -v
cd frontend && pnpm test --run

# Correr con cobertura
cd backend && pytest --cov=app --cov-report=html --cov-report=term-missing
cd frontend && pnpm test --coverage --run

# Ver reporte de cobertura HTML (backend)
open backend/htmlcov/index.html

# Ver reporte de cobertura HTML (frontend)
open frontend/coverage/index.html

# Test específico por módulo
cd backend && pytest tests/test_phv.py -v
cd backend && pytest tests/test_athletes.py -v -k "anthropometry"
cd frontend && pnpm test phv.test

# Healthcheck de la API
curl http://localhost:8000/docs | head -5

# Obtener token de prueba rápido
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"entrenador@trochyruta.com","password":"Coach2026!"}' \
  | jq '.access_token'
```
