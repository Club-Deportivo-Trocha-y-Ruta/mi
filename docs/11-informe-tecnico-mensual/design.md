# Informe Técnico Mensual — Diseño técnico

**Fecha:** 2026-06-03
**Estado:** Implementado (backend + frontend + tests). Deploy a Render pendiente de aprobación.
**Migración:** Alembic `d4e5f6a7b8c9` (down_revision `c6d7e8f9a0b1`).

Este documento detalla el diseño técnico del refactor del módulo "Reporte Mensual del Club" (Fase 1.5) hacia un **Informe Técnico Mensual** estilo informe a financiador. La visión general, el alcance acordado y los pasos de implementación están en [`workflow.md`](workflow.md). La guía operativa para el coach está en [`runbook.md`](runbook.md).

---

## 1. Resumen de la solución

El reporte mensual deja de ser un único párrafo de IA (`ai_summary`, intacto y preservado) y pasa a ser un documento estructurado por capítulos, con:

- **Metadata institucional** del proyecto del club (perfil 1:1, configurado una vez).
- **Narrativa por bloques**: la IA pre-redacta seis bloques; el coach edita cada uno antes de aprobar.
- **Resultados de competencia** del mes: podios del club tomados del módulo Copa Valle (Fase 1.7).
- **PDF de distribución restringida** (coach/admin), con banner BORRADOR mientras está en `draft` y aviso de Ley 1581.

La IA nunca emite nombres reales de menores. Los padres no reciben `narrative_blocks` ni `competition_results`.

---

## 2. Modelo de datos

Todos los cambios viven en la migración `d4e5f6a7b8c9`. Patrón `batch_alter_table` + enums en minúsculas + `server_default`, de modo que funciona en MySQL (ALTER nativo) y SQLite (recrea tabla) y los registros legacy quedan en valores coherentes sin backfill.

### 2.1 Tabla nueva: `club_project_profiles`

Relación **1:1 con `clubs`** (UNIQUE en `club_id`, FK `ON DELETE RESTRICT`). Metadata estática del proyecto que encabeza cada informe.

| Columna | Tipo | Nullable | Notas |
|---|---|---|---|
| `id` | Integer PK | no | autoincrement |
| `club_id` | Integer FK → `clubs.id` | no | UNIQUE `uq_club_project_profile_club`, `ON DELETE RESTRICT` |
| `project_name` | String(200) | sí | Nombre del proyecto (ej: "Pedaleando por un Sueño") |
| `executing_entity` | String(200) | sí | Entidad ejecutora |
| `report_responsible` | String(200) | sí | Responsable del informe |
| `purpose` | Text | sí | Propósito del proyecto |
| `general_objective` | Text | sí | Objetivo general |
| `specific_objectives` | JSON | sí | Lista de strings (objetivos específicos) |
| `territory_location` | String(200) | sí | Localización (municipio/sede) |
| `territory_description` | Text | sí | Descripción del territorio |
| `created_at` / `updated_at` | DateTime | no | UTC, `onupdate` en `updated_at` |

Todos los campos de contenido son opcionales para permitir upsert incremental. El modelo no contiene datos de menores; el router aplica RBAC (coach/admin del club).

Modelo: `backend/app/models/club_project_profile.py`.

### 2.2 Columnas nuevas en `monthly_reports`

| Columna | Tipo | Nullable | Default | Notas |
|---|---|---|---|---|
| `narrative_blocks` | JSON | sí | NULL | Mapa `{block_key: {ai_draft, final_text, ai_model, ai_generated_at}}` |
| `competition_results` | JSON | sí | NULL | Snapshot de podios del mes (lista de `CompetitionResultItem`) |
| `status` | Enum(`draft`, `approved`) | no | `'draft'` | `server_default`; reportes legacy quedan en `draft` |

`ai_summary` (reporte v1) **no se migra ni se elimina**: queda intacto para compatibilidad.

### 2.3 Columnas nuevas en `training_sessions`

| Columna | Tipo | Nullable | Default | Notas |
|---|---|---|---|---|
| `session_kind` | Enum(`entrenamiento`, `actividad_conjunta`, `salida`, `otro`) | no | `'entrenamiento'` | `server_default`; sesiones legacy quedan como `entrenamiento` |
| `objectives` | Text | sí | NULL | Objetivos de la sesión (texto libre) |

Enums persistidos en minúsculas (coherente con `values_callable` de `SessionKind` / `MonthlyReportStatus`).

### 2.4 Reversibilidad

`downgrade()` elimina las 5 columnas, la tabla `club_project_profiles` y los tipos enum nativos `sessionkind` / `monthlyreportstatus` (solo MySQL; en SQLite son VARCHAR + CHECK que desaparecen con la columna/tabla).

---

## 3. Bloques narrativos

El informe se estructura en bloques con clave fija. La IA redacta seis bloques; `competencia` es estructurado (lo llena el helper de competencia, no la IA).

| Clave | Capítulo | Generación | Máx. palabras |
|---|---|---|---|
| `objetivo` | Objetivo del período | IA | 150 |
| `desarrollo` | Desarrollo de actividades | IA | 200 |
| `resultados` | Resultados obtenidos (indicadores agregados) | IA | 180 |
| `conclusiones` | Conclusiones y recomendaciones | IA | 150 |
| `apoyos_materiales` | Apoyos y recursos materiales | IA | 120 |
| `analisis_grupo` | Análisis cualitativo del grupo de alto rendimiento | IA | 220 |
| `competencia` | Participación en competencia (podios) | Estructurado (helper) | — |

Las claves permitidas se validan contra `ALLOWED_BLOCK_KEYS` en `backend/app/schemas/training_session.py`.

El bloque `analisis_grupo` es el **capítulo cualitativo del grupo de alto rendimiento** — el "capítulo" que el jefe sumará al informe consolidado de junio. Su prompt exige tono reflexivo del entrenador, sin juicios individuales y sin mencionar pseudónimos de atletas.

### 3.1 Estructura de un bloque (`NarrativeBlock`)

```json
{
  "ai_draft": "borrador anonimizado generado por la IA",
  "final_text": "texto aprobado/editado por el coach",
  "ai_model": "<modelo>",
  "ai_generated_at": "2026-06-03T..."
}
```

- `ai_draft`: borrador de la IA, ya pasado por guardrails de privacidad.
- `final_text`: se inicializa igual al `ai_draft`; el coach lo edita antes de aprobar. Es el texto que entra al PDF.
- `ai_model` / `ai_generated_at`: trazabilidad de la generación.

### 3.2 Use case IA: `MonthlyReportBlocksUseCase`

Archivo: `backend/app/services/ai/use_cases/monthly_report_blocks.py`. Hereda de `MonthlyReportUseCase` (reporte v1) para **reutilizar** anonimización de atletas, guardrails y el cliente LLM. No se duplica lógica de privacidad.

- `run_block(ctx, block_key)`: genera el borrador de un bloque. Ante timeout, error de red o rechazo de guardrail, retorna `BlockDraft` con `ai_draft=None` y un `error` descriptivo en vez de lanzar excepción. Así un bloque fallido no tumba el resto.
- `run_all_blocks(ctx, block_keys=None)`: genera los seis bloques narrativos en paralelo (`asyncio.gather`); excluye `competencia`. Cada bloque falla de forma independiente.

Prompt: `backend/app/services/ai/prompts/monthly_report_blocks.j2` (registrado en `backend/app/services/ai/prompts/registry.py` con id `monthly_report_blocks`). Cada bloque inyecta `block_title`, `block_prompt` (instrucción específica) y `block_max_words` en el contexto. El contexto enviado al LLM solo contiene datos agregados y pseudónimos deterministas — **nunca** nombres reales ni `competition_results`.

Guardrails: `MonthlyReportGuardrails(forbidden_names=ctx.forbidden_names)`, los mismos del reporte v1: sin nombres reales (lista dinámica desde DB), sin términos médicos ni de suplementos. La salida pasa por `_scrub()`; si el guardrail rechaza, el bloque se marca con `error="guardrail: ..."`.

---

## 4. Helper de competencia

Archivo: `backend/app/services/training/competition_results.py`.

`build_competition_results(db, club_id, year, month) -> list[CompetitionResultItem]`:

- Une `RaceResult` → `RaceEvent` (evento dentro del mes) → `RaceCategory` → `Athlete` (del club), con `deleted_at IS NULL` y `position IS NOT NULL`.
- Ordena por `event_date ASC, position ASC`.
- Devuelve `CompetitionResultItem` con `athlete_name`, `category`, `position`, `points`, `event_name`, `event_date`.
- **Degrada limpio**: cualquier error de BD devuelve `[]` sin romper el informe.

Los nombres de atletas aquí son **intencionales**: alimentan el PDF (documento controlado), no la IA. La IA nunca recibe este objeto.

---

## 5. Endpoints

Router: `backend/app/routers/monthly_reports.py`. Montado en `main.py` con prefijo `/api/clubs` (router coach/admin) y `/api/parents` (router padre de solo lectura).

| Método | Ruta | Rol | Propósito |
|---|---|---|---|
| GET | `/api/clubs/{id}/project-profile` | coach/admin | Lee el perfil de proyecto del club |
| PUT | `/api/clubs/{id}/project-profile` | coach/admin | Crea o reemplaza el perfil (upsert) |
| PATCH | `/api/clubs/{id}/project-profile` | coach/admin | Actualiza parcial (`exclude_unset`) |
| POST | `/api/clubs/{id}/monthly-reports` | coach/admin | Genera/regenera el reporte del período (incluye bloques IA + competencia) |
| GET | `/api/clubs/{id}/monthly-reports` | coach/admin | Lista reportes del club |
| GET | `/api/clubs/{id}/monthly-reports/{year}/{month}` | coach/admin | Detalle del reporte (con bloques y competencia) |
| PATCH | `/api/clubs/{id}/monthly-reports/{year}/{month}/blocks` | coach/admin | Actualiza `final_text` de bloques y/o transiciona `draft → approved` |
| POST | `/api/clubs/{id}/monthly-reports/{year}/{month}/blocks/{block_key}/regenerate` | coach/admin | Regenera el `ai_draft` de un bloque individual |
| GET | `/api/clubs/{id}/monthly-reports/{year}/{month}/pdf` | coach/admin | Descarga el PDF (template técnico) |
| GET | `/api/parents/.../monthly-summary` | parent | Resumen filtrado, sin bloques ni competencia |

Notas de contrato:

- `PATCH .../blocks` (`MonthlyReportBlocksUpdate`): solo acepta claves en `ALLOWED_BLOCK_KEYS`; la transición de estado es solo `draft → approved` (no hay reversión a draft). Devuelve `MonthlyReportRead` con `athlete_names` resuelto para el rol coach/admin.
- `POST .../regenerate`: preserva el `final_text` editado por el coach si ya difería del `ai_draft` previo.
- `GET .../pdf`: usa el template `DocumentTemplate.TRAINING_MONTHLY_TECHNICAL_REPORT` (registrado en `backend/app/services/notification/template_registry.py`, ruta `documents/pdf/training_monthly_technical_report.html`). El reporte v1 (`TRAINING_MONTHLY_REPORT`) sigue existiendo.

---

## 6. PDF — `training_monthly_technical_report.html`

Template: `backend/templates/documents/pdf/training_monthly_technical_report.html`. Variable `is_draft: bool` controla el banner BORRADOR.

Secciones en orden:

1. Portada institucional / datos del proyecto (desde `ClubProjectProfile`).
2. Contexto del proyecto.
3. Localización territorial.
4. Objetivo del período (bloque `objetivo`).
5. Actividades ejecutadas — Grupo de Alto Rendimiento (bloque `desarrollo` + tabla de sesiones).
6. Participación en competencia (`competition_results`, con podios).
7. Actividades conjuntas y salidas (sesiones con `session_kind` `actividad_conjunta` / `salida`).
8. Apoyos y recursos materiales (bloque `apoyos_materiales`).
9. Resultados (bloque `resultados`).
10. Análisis del grupo de alto rendimiento (bloque `analisis_grupo`).
11. Conclusiones y recomendaciones (bloque `conclusiones`).
12. Registro fotográfico (media consentida).

> La sección **"Población Atendida" está OMITIDA** por decisión explícita del usuario; el documento se limita al grupo de alto rendimiento, sin segmentación por programa (no se documenta "Teteros" ni otros programas formativos).

Avisos legales:

- **Banner BORRADOR** visible solo si `is_draft=True` ("pendiente de aprobación por el entrenador responsable").
- **Aviso Ley 1581/2012** (+ Decreto 1377/2013): documento de **distribución restringida**, contiene datos de menores de edad, uso exclusivo del equipo técnico, no distribuir externamente.

---

## 7. Privacidad

Resumen del contrato de privacidad (auditoría reutiliza el marco del reporte v1 y del newsletter de Fase 1.8):

| Regla | Mecanismo |
|---|---|
| La IA nunca recibe ni emite nombres reales | Anonimización con pseudónimos deterministas + `MonthlyReportGuardrails(forbidden_names)` + `_scrub()`; `competition_results` no se pasa al LLM |
| Padres no reciben `narrative_blocks` | El router fuerza `narrative_blocks=None` para el rol `parent` |
| Padres no reciben `competition_results` | El router fuerza `competition_results=None` para el rol `parent` (contiene nombres de otros menores) |
| `athlete_names` solo para coach/admin | Se rellena únicamente en endpoints coach/admin; ausente en la vista padre |
| Nombres de menores en el PDF | **Excepción deliberada**: el informe es un documento externo controlado. Gated por: RBAC coach/admin + aprobación + aviso Ley 1581 en el documento. Sin nombres en `draft` distribuido sin aprobación → banner BORRADOR |

Los nombres de menores aparecen en el PDF únicamente en podios (`competition_results`) y tablas de asistencia. Es una excepción consciente al principio general "sin nombres en artefactos", justificada porque el PDF es de distribución restringida bajo control del coach/admin.

---

## 8. Frontend

- **`ReportDetailPage`** (`frontend/src/routes/training/ReportDetailPage.tsx`): reescrita como **editor por bloques**. Por bloque: generar/regenerar con IA, editar `final_text`, ver trazabilidad del modelo. Acciones globales: aprobar (`draft → approved`), descargar PDF. Vista de solo lectura para padres (sin bloques internos ni competencia).
- **`ProjectProfilePage`** (`frontend/src/routes/training/ProjectProfilePage.tsx`): edición del perfil de proyecto (RHF + Zod; objetivos específicos como lista). Se configura una vez por club.
- **`ReportsListPage`**: badge de estado (`draft` / `approved`) + enlace a los datos del proyecto.
- **`SessionFormPage`**: campos nuevos `session_kind` (selector) y `objectives` (texto).
- **Tipos / API / hooks**: `useProjectProfile`, `useUpsertProjectProfile`, `useUpdateReportBlocks`, `useRegenerateBlock` + handlers MSW. Schemas Zod en `frontend/src/schemas/trainingSession.schema.ts`.

---

## 9. Pruebas

- **Backend**: 52 tests targeted verdes (incluye `backend/tests/models/test_monthly_report_refactor_columns.py` para las columnas/enums nuevos).
- **Frontend**: 1742 tests vitest verdes + `tsc` limpio.
- Migración encadenada al head `c6d7e8f9a0b1` → `d4e5f6a7b8c9`, verificada en SQLite vía tests.

---

## 10. Referencias

- [`workflow.md`](workflow.md) — visión general, alcance, pasos.
- [`runbook.md`](runbook.md) — guía operativa del coach.
- [`../09-training-planning/`](../09-training-planning/) — módulo base de sesiones y reporte mensual v1.
- [`../10-race-results/`](../10-race-results/) — origen de los resultados de competencia.
- `backend/app/models/club_project_profile.py`
- `backend/alembic/versions/d4e5f6a7b8c9_informe_tecnico_mensual.py`
- `backend/app/services/ai/use_cases/monthly_report_blocks.py`
- `backend/app/services/ai/prompts/monthly_report_blocks.j2`
- `backend/app/services/training/competition_results.py`
- `backend/app/routers/monthly_reports.py`
- `backend/templates/documents/pdf/training_monthly_technical_report.html`
