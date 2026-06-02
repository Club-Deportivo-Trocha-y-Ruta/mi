# Unificación `/competitions` + Análisis IA — Workflow

**Fecha:** 2026-06-01
**Solicitante:** Coach
**Estado:** PRD aprobado (decisiones cerradas). Pendiente kickoff de PR1.
**Brainstorm por:** `product-manager` + `refactoring-expert`

---

## 1. Contexto

Hoy coexisten dos rutas separadas que el coach quiere unificar:

| Ruta actual | Responsabilidad | Destino |
|---|---|---|
| `/competitions` | CRUD válidas Copa Valle (Fase 1.7+/1.8) | **Permanece como hub central** |
| `/coach/race-analysis` | Landing IA v2 (LangGraph agéntico + HITL) | Absorbido en `/competitions/insights/...` |
| `/training/races/:raceEventId/club-insights` | IA grupal por carrera | Absorbido en tab `insights` del detalle |

**Objetivo coach:** todo centralizado en `/competitions`. CRUD + análisis IA en todas las combinaciones (válida, deportista, club, temporada) + bidireccionalidad con calendario + re-ingesta diff + re-trigger IA.

---

## 2. Decisiones cerradas (2026-06-01)

| # | Pregunta | Decisión |
|---|---|---|
| D1 | Crear `calendar_event` al crear competencia | **ON con opt-out visible** (checkbox marcado por default) |
| D2 | RBAC para vistas IA cross-válida | **Solo coach/admin**. Parents → 403 |
| D3 | Boletín mensual ya enviado cuando llega corrección | **Marcar `outdated`**, sin reenvío automático |
| D4 | Panorama global de temporada en MVP | **Sí**, parte de Ola 2 |
| D5 | Política re-trigger IA tras re-ingesta | **Siempre manual** con confirmación coach (sin cron) |
| D6 | Alcance re-ingesta MVP | **UI completa** con `DiffTable` confirmable end-to-end |
| D7 | Lifespan redirects 301 (`/coach/race-analysis`, `/training/races/:id/club-insights`) | **1 ciclo de release** (~PR1 a PR7), luego 410 en PR7 |

---

## 3. Mapa de rutas final

```
/competitions                          → lista
/competitions/new                      → crear válida
/competitions/import                   → wizard ingest-first
/competitions/:id                      → detalle (tabs info|results|conditions|athletes|insights)
/competitions/:id/edit                 → editar metadata
/competitions/:id/import               → re-ingesta con diff confirmable
/competitions/:id/insights/:runId      → detalle de un run IA anclado a válida
/competitions/insights                 → hub análisis (panorama cross-válidas)
/competitions/insights/athletes/:id    → longitudinal por deportista
/competitions/insights/club            → grupal/club (absorbe ClubInsightsByRacePage)
/competitions/insights/season/:year    → panorama por temporada
```

**Redirects 301 (activos durante PR1-PR7):**
- `/coach/race-analysis` → `/competitions/insights`
- `/training/races/:raceEventId/club-insights` → `/competitions/:raceEventId?tab=insights`

**PR7:** redirects pasan a 410.

---

## 4. Modelo de datos

**Una sola adición:** columna `stale_since DATETIME NULL` en tabla de runs IA (nombre exacto a confirmar con `database-architect`).

- Se puebla cuando una re-ingesta sobre el mismo `race_event_id` detecta SHA256 diferente.
- Permite ver "análisis desactualizado" sin perder el histórico.
- Nullable, sin default → migración no bloqueante.

**No se requiere tabla nueva.** `RaceResultRevision` ya existe desde Fase 1.7.

---

## 5. Roadmap en 7 PRs incrementales

### Ola 1 — Consolidación de rutas

**PR1 — Codemod rutas + redirects + sidebar único**
- Líder: `react-ui-engineer`. Soporte: `qa-engineer`.
- Archivos: `App.tsx`, `AppShell.tsx`, ajuste `MemoryRouter` en tests existentes.
- DONE: redirects 301 funcionan, sidebar unificado "Competencias", CI verde.
- Riesgo: bajo.

### Ola 2 — IA centralizada

**PR2 — Tab `insights` en `CompetitionDetailPage` (feature flag)**
- Líder: `react-ui-engineer`. Soporte: `qa-engineer`.
- Estrategia strangler: monta `RaceAnalysisPage` dentro del tab vía `VITE_INSIGHTS_IN_COMPETITION=true`. Ruta vieja sigue activa, cero duplicación.
- Medir bundle delta < 20 KB sobre lazy chunk existente.

**PR3 — Vistas IA cross-válida**
- Líder: `react-ui-engineer`. Soporte: `data-privacy-guard` (auditoría obligatoria), `fastapi-architect` (endpoint global).
- 4 subpáginas bajo `/competitions/insights/{,athletes/:id,club,season/:year}`.
- Mover `components/ai/` + `components/athletes/ai/` a `components/competitions/insights/`. Hooks NO se mueven.
- **Endpoint nuevo:** `GET /api/race-analysis/insights/season/{year}` — debe usar query agregada con JOIN (sin N+1 en Python). Diseñar con `fastapi-architect` antes de implementar UI.
- **Privacidad Ola 2:** vista global usa `forbidden_names=[]` → fuerza redacción anónima sin nombres de menores. RBAC: padres → 403 en todas las rutas `/insights/*`.

### Ola 3 — Calendario bidireccional

**PR6 — Checkbox + sincronización**
- Líder: `react-ui-engineer`. Soporte: `integration-engineer`.
- `CompetitionFormPage`: checkbox "Crear evento en calendario" (D1 = ON por default).
- Source-of-truth: `race_event` lidera. Cambio de fecha/nombre/sede propaga a calendar event ligado.
- Reverso (`?race_event_id=` en `EventForm`) ya existe.
- Vínculo 1:1 estricto (1 válida ↔ máx 1 calendar event tipo `race`).

### Ola 4 — Re-ingesta + re-trigger IA

**PR4 — Re-ingesta con diff confirmable**
- Líder: `fastapi-architect`. Soporte: `react-ui-engineer`.
- Backend: `GET /api/race-analysis/imports/{race_event_id}/diff` (read-only, calcula delta vs última versión).
- Frontend: `/competitions/:id/import` reutiliza `DiffTable` existente, agrupando cambios por: **Posición** | **Tiempo** | **Gap GC** | **Categoría reclasificada** | **Nuevos/Eliminados**.
- Catálogo cerrado para `revision_reason` (sin texto libre — privacidad ya implementada).
- SHA256 idempotente intacto.

**PR5 — Re-trigger IA + flag `stale`**
- Líder: `fastapi-architect` + `database-architect`. Soporte: `data-privacy-guard`.
- Migración Alembic: columna `stale_since DATETIME NULL` en runs IA.
- Endpoint: `POST /api/race-analysis/runs/{run_id}/invalidate` (auto desde ingestor en re-ingesta) + `POST /api/race-analysis/runs/{run_id}/re-execute` (manual coach — D5).
- UI: badge "Análisis desactualizado" + botón "Re-ejecutar" en cada run stale.
- **D5 honrado:** todo re-trigger es manual con confirmación. NO cron, NO auto al confirmar diff.
- **Boletines:** al detectar stale, marcar `AthleteMonthlyNewsletter` afectado como `outdated` (D3). NO reenviar.

### Ola 5 — Limpieza

**PR7 — Deprecación final**
- Líder: `react-ui-engineer`. Soporte: `qa-engineer`.
- Eliminar `RaceAnalysisPage.tsx`, `ClubInsightsByRacePage.tsx`, barrel re-exports transitorios.
- Redirects 301 → 410 (D7).
- Bundle baseline debe ser ≤ PR2.

---

## 6. Riesgos críticos

| Riesgo | Mitigación | Responsable |
|---|---|---|
| Deep links externos (Spond, emails) rotos | Redirects 301 durante 1 ciclo completo (D7). Telemetría de hits. | `release-manager` |
| Bundle size en vistas insight nuevas | Lazy chunks por subpágina. Medir delta en PR2 baseline. | `react-ui-engineer` |
| Endpoint `/insights/season/:year` con N+1 | Query agregada SQL con JOIN o window functions. Benchmark antes de UI. | `fastapi-architect` + `sql-pro` |
| Privacy R2 en vista global temporada | `forbidden_names=[]` fuerza redacción anónima. Auditoría obligatoria PR3 + PR5. | `data-privacy-guard` |
| 1682 vitest + 305 race tests | Codemod mecánico de `MemoryRouter` paths. No re-escribir assertions. | `qa-engineer` |
| Coste IA por re-trigger masivo | D5 = manual con confirmación. Sin auto-trigger. | (cubierto por decisión) |
| Migración `stale_since` en prod | Nullable, sin default. No bloquea queries existentes. | `database-architect` + `release-manager` |

---

## 7. Anti-patterns explícitos

- ❌ NO duplicar hooks IA en nueva ubicación. Imports desde `hooks/ai/` y `hooks/race/` permanecen.
- ❌ NO mezclar codemod de componentes y lógica nueva en mismo PR.
- ❌ NO eliminar rutas viejas antes de tener 301 estables por al menos un ciclo de deploy.
- ❌ NO diseñar endpoint global de temporada como loop en application layer.
- ❌ NO consolidar PR4 + PR5 en uno solo (contratos de rollback distintos).
- ❌ NO hacer migración en big-bang. Cada ola debe ser shippable y reversible.

---

## 8. Delegación matriz

| PR | Líder | Soporte |
|----|-------|---------|
| PR1 | `react-ui-engineer` | `qa-engineer` |
| PR2 | `react-ui-engineer` | `qa-engineer` |
| PR3 | `react-ui-engineer` | `data-privacy-guard`, `fastapi-architect`, `sql-pro` |
| PR4 | `fastapi-architect` | `react-ui-engineer`, `qa-engineer` |
| PR5 | `fastapi-architect` + `database-architect` | `data-privacy-guard` |
| PR6 | `react-ui-engineer` | `integration-engineer` |
| PR7 | `react-ui-engineer` | `qa-engineer`, `release-manager` |

**Orquestador global:** `engineering-lead` toma este workflow y descompone PR por PR, delegando a especialistas. `head-coach-lead` se consulta solo si surge una decisión deportiva no anticipada.

---

## 9. Próximos pasos

1. ✅ PRD aprobado (este documento).
2. ⏳ Coach aprueba kickoff de PR1.
3. ⏳ `engineering-lead` toma PRD y emite plan detallado de PR1.
4. ⏳ `react-ui-engineer` ejecuta PR1 (codemod rutas + redirects + sidebar).
5. ⏳ Tras PR1 mergeado y deployado, `engineering-lead` arranca PR2.

**Sin avanzar implementación hasta confirmación explícita del coach.**
