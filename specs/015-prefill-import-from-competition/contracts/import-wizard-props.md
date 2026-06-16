# Contract: ImportWizard component props

Component: `frontend/src/components/competitions/import/ImportWizard.tsx`

## Before (today)
```ts
interface ImportWizardProps {
  onCompleted?: (response: ImportCommitResponse) => void;
}
```
Container renders `<ImportWizard onCompleted={handleCompleted} />` — no competition context.

## After (this feature)
```ts
interface ImportWizardProps {
  onCompleted?: (response: ImportCommitResponse) => void;
  /**
   * When provided, the wizard runs in "prefilled from competition" mode:
   * fetches the event + its series, prefills and LOCKS identity fields,
   * derives series_kind (not editable), hides válida # for championships,
   * and blocks with an "edit metadata" escape hatch if the series/type
   * cannot be determined (FR-009). When undefined, the wizard behaves
   * exactly as today (standalone create-and-import). FR-007.
   */
  raceEventId?: number;
}
```

### Container change
`CompetitionImportPage.tsx` MUST pass the parsed id:
```tsx
<ImportWizard
  raceEventId={hasExistingEvent ? raceEventId! : undefined}
  onCompleted={handleCompleted}
/>
```

## Behavioral contract

| Condition | Required behavior | Spec ref |
|---|---|---|
| `raceEventId` undefined | Identical to today: empty, editable, `series_kind` default `cup`, no locking. | FR-007, SC-005 |
| `raceEventId` set, prefill `ready` | Identity fields (name, date, city, series, type, round) prefilled and **locked/read-only**; conditions prefilled but editable; files required. | FR-001..FR-004, SC-001/SC-004 |
| `raceEventId` set, type derived | `series_kind` taken from `series.kind`; **no in-flow control** to change type/series. Never defaults to `cup` for a championship. | FR-005, SC-004 |
| Championship | `válida #` concept absent (not shown, not requested). | FR-008, SC-006 |
| Cup round | `válida #` shown as part of locked prefilled metadata. | FR-008, SC-006 |
| Prefill `blocked` (series/type undeterminable) | Designed blocked state; import cannot proceed; explicit link to `/competitions/{id}/edit`. | FR-009 |
| Prefill `loading` | Designed loading state (cold-start aware), not an unbounded spinner. | Constitution III/IV |
| Escape hatch | Explicit "Editar metadata" → `/competitions/{id}/edit`. | FR-006 |
| RBAC | No new access; coach/admin only, same as today. | FR-010 |

## Non-goals (must NOT change)
- Parse/dry-run/commit pipeline and result matching (FR-011).
- Standalone flow (FR-007).
- Any backend schema/endpoint (FR-012).
