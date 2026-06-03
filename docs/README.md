# docs/ — Índice de Documentación

Carpetas numeradas por feature en orden cronológico. Archivos internos por tipo: `workflow.md`, `research.md`, `design.md`, `qa.md`, `reference.md`.

| # | Carpeta / Archivo | Contenido |
|---|---|---|
| — | [01-marco-teorico.md](01-marco-teorico.md) | Fundamento científico: LTAD, PHV, fisiología, nutrición, normativa (referencia inviolable) |
| 02 | [02-scaffolding/](02-scaffolding/) | Decisiones de arquitectura y stack del proyecto |
| 03 | [03-fase1/](03-fase1/) | Auth, roles, CRUD atletas, antropometría PHV — workflow + plan QA |
| 04 | [04-percentiles/](04-percentiles/) | Percentiles OMS/CDC: investigación + implementación curvas de crecimiento |
| 05 | [05-design-system/](05-design-system/) | Sistema visual: paleta, tipografía, componentes, tokens |
| 06 | [06-parents/](06-parents/) | Módulo padres/acudientes: backend + portal frontend |
| 07 | [07-notifications/](07-notifications/) | Módulo de notificaciones: email, PDF, DOCX |
| 08 | [08-onboarding/](08-onboarding/) | Onboarding por invitación: investigación + diseño + implementación |
| 09 | [09-training-planning/](09-training-planning/) | Sesiones de entrenamiento: planificación, asistencia, rúbrica, reporte mensual con IA |
| 10 | [10-race-results/](10-race-results/) | Resultados Copa Valle XCO: ingesta de PDFs, normalización fuzzy, analíticas longitudinales (evolución, gap podio, ranking club, proyección). Extensión 2026-05-26: condiciones de carrera en UI (wizard + tarjeta tri-estado + PATCH) — ver `upload-design.md` §14. Extensión 2026-05-27: módulo **Competencias** (CRUD `race_events`, wizard reubicado, tabs URL-driven) — ver `competitions-module.md` |
| 11 | [11-informe-tecnico-mensual/](11-informe-tecnico-mensual/) | **Informe Técnico Mensual** (Fase 1.9): refactor del reporte mensual del club hacia documento estilo informe a financiador. Perfil de proyecto 1:1, narrativa IA por bloques editable por el coach, podios del mes, PDF de distribución restringida — `workflow.md` + `design.md` + `runbook.md` (guía del coach) |

## Archivo de entrenamiento

- `Plan_Entrenamiento_XCO_Copa_Valle_2026.docx` — Plan macrociclo 2026
