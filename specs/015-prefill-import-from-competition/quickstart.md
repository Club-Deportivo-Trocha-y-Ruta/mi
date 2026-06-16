# Quickstart / Manual verification: Prefill import from competition

Branch: `015-prefill-import-from-competition` · Frontend-only feature.

## Prerequisites
```bash
# backend (seeded dev data)
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload

# frontend
cd frontend && npm run dev
```
Login as coach (`entrenador@trochyruta.com` / `Coach2026!`).

## Happy path — cup round (FR-001..FR-005, FR-008)
1. Go to a completed **cup** competition detail, e.g. `/competitions/{cupId}`.
2. Click **Importar resultados** (or open `/competitions/{cupId}/import`).
3. Expect step 1 ("Archivos y datos") to show **prefilled, locked**: Tipo = **Copa** (not the blank default), Nombre de la serie, Temporada, **Válida #**, Nombre del evento, Fecha, Ciudad — all read-only, matching the detail "Información" card.
4. Expect **no** input control to change Tipo/serie; an **"Editar metadata"** link is available.
5. Fill (optional) conditions, attach the results PDF, **Continuar** → dry-run → commit.
6. Expect redirect to `/competitions/{cupId}?tab=results`; results linked to that exact competition.

## Happy path — championship (FR-008, SC-006)
1. Open `/competitions/15/import` (Ginebra · Campeonato · CD).
2. Expect Tipo = **Campeonato** (never Copa) and **no "Válida #"** field anywhere.
3. Remaining identity fields locked; proceed with the PDF as above.

## Standalone unchanged (FR-007, SC-005)
1. Open `/competitions/import` (no id).
2. Expect today's behavior: empty, all fields editable, Tipo defaults to Copa, no locking imposed.

## Block path — undeterminable series/type (FR-009)
1. Open the import for a competition whose series cannot be resolved.
2. Expect a designed **blocked** state (not a raw error) explaining the import can't proceed, with a link to **Editar metadata** (`/competitions/{id}/edit`). Import cannot continue until classified.

## Automated checks
```bash
cd frontend

# Unit + integration (Vitest + RTL + MSW) and a11y (jest-axe)
npm run test -- src/components/competitions/import src/routes/competitions/CompetitionImportPage.tsx src/hooks/race/useImportPrefill.ts

# Type + lint (constitution gate)
npm run typecheck
npx eslint src/components/competitions/import src/hooks/race/useImportPrefill.ts

# Mutation testing (scoped to prefill logic)
npm run test:mutation     # → stryker run ; expect mutation score ≥ 60 (break), target ≥ 85

# E2E (Playwright)
npm run test:e2e -- prefill-import-from-competition
```

## Acceptance signals (map to Success Criteria)
- **SC-001**: zero re-typed identity fields from a competition.
- **SC-004**: identity fields read-only; no in-flow type/series edit control.
- **SC-005**: standalone flow byte-for-byte behavior unchanged.
- **SC-006**: championship shows no `Válida #`; cup shows its round.
- **Privacy**: no athlete name visible before the dry-run match step.
