# Informe Técnico Mensual — Workflow

**Fecha:** 2026-06-03
**Estado:** Implementado (backend + frontend + tests). Deploy a Render pendiente de aprobación.
**Origen:** Refactorización del módulo "Reporte Mensual del Club" (Fase 1.5) hacia un documento estilo informe a financiador.

---

## Contexto

El club ya generaba un "reporte mensual" con un único resumen de IA (campo `ai_summary`) y métricas agregadas. Ese formato no servía como entregable hacia un financiador o aliado institucional (estilo informe del proyecto "Pedaleando por un Sueño"): es un párrafo suelto, sin estructura de informe de gestión, sin portada institucional ni sección de competencia con podios.

Esta refactorización convierte el reporte mensual en un **Informe Técnico Mensual**: un documento estructurado por capítulos, con metadata institucional del proyecto, narrativa pre-redactada por IA y editada por el coach, resultados de competencia del mes y registro fotográfico. El entregable final es un PDF de distribución restringida (coach/admin).

El objetivo operativo concreto: que al **cerrar junio 2026** el coach tenga todos los insumos capturados durante el mes y, con pocos clics, genere un PDF estilo informe del jefe — incluyendo el "capítulo" cualitativo del grupo de alto rendimiento que el jefe sumará al informe consolidado.

## Alcance acordado con el usuario

**En alcance:**
- Documento limitado al **Grupo de Alto Rendimiento**. Sin segmentación por programa (no se documenta el programa "Teteros" ni otros programas formativos).
- Sección "Población Atendida" **OMITIDA** del informe (decisión explícita del usuario).
- Narrativa **pre-redactada por IA** bloque a bloque; el **coach edita** cada bloque antes de aprobar. La IA nunca emite el documento final sin revisión humana.
- Entrega **completa**: capa de datos (modelo + migración), motor de IA por bloques, helper de competencia, endpoints, editor frontend por bloques, página de perfil del proyecto, y plantilla PDF.
- Resultados de competencia del mes: podios del club tomados del módulo de resultados Copa Valle (Fase 1.7).

**Fuera de alcance:**
- Segmentación por programa / "Población Atendida".
- Envío automático del informe por email (el coach descarga el PDF y lo distribuye manualmente).
- Métricas individuales por atleta en el cuerpo narrativo (la IA trabaja solo con datos agregados).
- Cambios al newsletter individual a padres (Fase 1.8), que es un módulo distinto.

## Modelo de datos nuevo

Tres cambios en la capa de datos, todos en la migración Alembic `d4e5f6a7b8c9` (encadenada al head `c6d7e8f9a0b1`). Detalle de campos y justificación en [`design.md`](design.md) §2.

| Cambio | Tabla / objeto | Resumen |
|---|---|---|
| Tabla nueva | `club_project_profiles` | Metadata estática del proyecto del club (1:1 con `clubs`). Encabeza cada informe. |
| Columnas nuevas | `monthly_reports` | `narrative_blocks` (JSON), `competition_results` (JSON), `status` (enum `draft`/`approved`). |
| Columnas nuevas | `training_sessions` | `session_kind` (enum `entrenamiento`/`actividad_conjunta`/`salida`/`otro`), `objectives` (texto). |

Todas las columnas nuevas son seguras hacia atrás: `narrative_blocks` y `competition_results` son `NULL` por defecto; `status` y `session_kind` tienen `server_default` (`draft` y `entrenamiento` respectivamente), de modo que los registros legacy quedan en valores coherentes sin backfill.

## Bloques narrativos

El informe se estructura en bloques con clave fija. La IA redacta seis bloques narrativos; `competencia` es estructurado (no narrativo, se llena con el helper de competencia).

| Clave | Capítulo | Generación |
|---|---|---|
| `objetivo` | Objetivo del período | IA |
| `desarrollo` | Desarrollo de actividades | IA |
| `resultados` | Resultados obtenidos (indicadores agregados) | IA |
| `conclusiones` | Conclusiones y recomendaciones | IA |
| `apoyos_materiales` | Apoyos y recursos materiales | IA |
| `analisis_grupo` | Análisis cualitativo del grupo de alto rendimiento | IA |
| `competencia` | Participación en competencia (podios) | Estructurado (helper) |

El bloque `analisis_grupo` es el **capítulo cualitativo del grupo** — el "capítulo" que el jefe sumará al informe consolidado de junio.

## Pasos de implementación

| # | Tarea | Owner | Estado | Fecha |
|---|---|---|---|---|
| 1 | Modelo `ClubProjectProfile` + columnas nuevas en `MonthlyReport` y `TrainingSession` + enums `SessionKind`/`MonthlyReportStatus` + migración `d4e5f6a7b8c9` | backend-dev | ✅ Completo | 2026-06-03 |
| 2 | Schemas Pydantic (`ClubProjectProfile*`, `NarrativeBlock`, `CompetitionResultItem`, `MonthlyReportBlocksUpdate`) + servicios `reports.py` (update/regenerate bloques) | backend-dev | ✅ Completo | 2026-06-03 |
| 3 | Use case IA `MonthlyReportBlocksUseCase` + prompt `monthly_report_blocks.j2` con límites de palabras por bloque y guardrails de privacidad reutilizados | backend-dev | ✅ Completo | 2026-06-03 |
| 4 | Helper `competition_results.py` (podios del club en válidas del mes) | backend-dev | ✅ Completo | 2026-06-03 |
| 5 | Endpoints: CRUD `project-profile`, `PATCH .../blocks`, `POST .../blocks/{key}/regenerate`, `GET .../pdf` con template técnico | backend-dev | ✅ Completo | 2026-06-03 |
| 6 | Plantilla PDF `training_monthly_technical_report.html` + registro en `template_registry.py` (`TRAINING_MONTHLY_TECHNICAL_REPORT`) | backend-dev | ✅ Completo | 2026-06-03 |
| 7 | Frontend: `ReportDetailPage` como editor por bloques, `ProjectProfilePage`, badges de estado, campos `session_kind`/`objectives` en form de sesión | frontend-dev | ✅ Completo | 2026-06-03 |
| 8 | Tests: 52 backend targeted verdes; 1742 frontend vitest verdes + `tsc` limpio | qa | ✅ Completo | 2026-06-03 |
| 9 | Documentación (este módulo) | technical-writer | ✅ Completo | 2026-06-03 |
| 10 | Deploy a Render | ops | ⏳ Pendiente | — |

## Criterios de aceptación

- [x] El coach puede registrar sesiones clasificadas por `session_kind` y con `objectives`.
- [x] El coach configura una sola vez el perfil del proyecto del club.
- [x] La IA pre-redacta los seis bloques narrativos sin emitir nombres reales de menores.
- [x] El coach edita y aprueba cada bloque; el PDF en `draft` lleva banner BORRADOR.
- [x] Los podios del mes se toman automáticamente de los resultados Copa Valle.
- [x] Los padres NO reciben `narrative_blocks` ni `competition_results`.
- [x] El informe omite la sección "Población Atendida" y se limita al grupo de alto rendimiento.
- [ ] Deploy a Render aprobado y aplicado.

## Runbook del coach

El paso a paso operativo para capturar insumos durante el mes y cerrar el informe está en [`runbook.md`](runbook.md).

## Referencias

- [`design.md`](design.md) — diseño técnico detallado.
- [`runbook.md`](runbook.md) — guía operativa para el coach.
- `backend/app/models/club_project_profile.py`
- `backend/app/models/training_session.py`
- `backend/alembic/versions/d4e5f6a7b8c9_informe_tecnico_mensual.py`
- `backend/app/services/ai/use_cases/monthly_report_blocks.py`
- `backend/app/services/training/competition_results.py`
- `backend/app/routers/monthly_reports.py`
- `backend/templates/documents/pdf/training_monthly_technical_report.html`
- `frontend/src/routes/training/ReportDetailPage.tsx`
- `frontend/src/routes/training/ProjectProfilePage.tsx`
- [`../09-training-planning/design.md`](../09-training-planning/design.md) — módulo base de sesiones y reporte mensual v1.
- [`../10-race-results/`](../10-race-results/) — origen de los resultados de competencia.
