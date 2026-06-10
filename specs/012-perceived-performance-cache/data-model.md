# Data Model: Perceived Performance — Frontend Cache & Cold-Start Experience

**Feature**: 012-perceived-performance-cache · **Date**: 2026-06-09

Frontend-only feature: **no database tables, no Alembic migrations, no Pydantic
schema changes**. The entities below are client-side structures.

## E1 — PersistedCacheSnapshot

The single payload stored on the device (localStorage key `tyr:rq-cache:v1`),
in the shape produced by the TanStack persister.

| Field | Type | Notes |
|---|---|---|
| `buster` | string | `"{APP_VERSION}:{userId}"` — mismatch ⇒ snapshot silently discarded on restore |
| `timestamp` | number (epoch ms) | Written on every save; restore discards if older than `maxAge` (24 h) |
| `clientState.queries[]` | dehydrated queries | **Only** queries accepted by the allow-list predicate (E2) |
| `clientState.mutations[]` | dehydrated mutations | Always empty — mutations are never persisted in this feature |

**Validation rules / invariants**

- INV-1 (FR-002): every dehydrated query's key matches an allow-listed prefix;
  default-deny for everything else. Asserted by privacy-invariant tests.
- INV-2 (FR-004): the key `tyr:rq-cache:v1` is removed from storage inside
  `logout()` — data at rest is deleted, not merely unrestorable.
- INV-3 (FR-005/FR-006): restore requires exact buster match (same account
  AND same app version).
- INV-4 (FR-007): read/parse failures (quota, corruption, private mode) are
  caught and degrade to in-memory behavior; never surfaced to the user.

**Lifecycle (state transitions)**

```
(saved) ──restore, buster ok, age ≤ 24 h──▶ RESTORED (stale → background revalidate)
(saved) ──buster mismatch / age > 24 h────▶ DISCARDED (silent, fresh first load)
(saved) ──logout()────────────────────────▶ WIPED (key removed)
(saved) ──storage corrupt/unavailable─────▶ IGNORED (in-memory fallback)
```

## E2 — PersistenceAllowList

Reviewable registry in `frontend/src/lib/persistAllowList.ts`; the audit
surface for `data-privacy-guard`.

| Field | Type | Notes |
|---|---|---|
| `prefixes` | readonly QueryKey-prefix list | Final (post-audit 2026-06-10): `["calendar","events"]`, `["calendar","race-events","available-for-calendar"]`, `["raceEvents"]`, `["revision-reasons"]`. Standings/results/competitors, calendar-event detail, and training-session lists were EXCLUDED by the privacy audit (minor-identifying fields). |
| `shouldDehydrateQuery(query)` | predicate | `status === 'success'` AND prefix match; exported for direct unit/mutation testing |

**Rules**: additions require a privacy review (constitution gate); per-athlete,
parent-specific, newsletter, AI-content, and anthropometry/PHV keys are never
eligible (FR-002 exclusions documented alongside the registry).

## E3 — ServerWakingState

Zustand store `frontend/src/store/serverWaking.store.ts`, fed by the axios
interceptors; not persisted.

| Field | Type | Notes |
|---|---|---|
| `pendingCount` | number | In-flight requests registered by request/response interceptors |
| `oldestPendingSince` | number \| null | Epoch ms of the oldest in-flight request |
| `isWaking` | boolean | `true` when oldest pending exceeds the 3 s threshold |

**State transitions**

```
IDLE ──request starts──▶ PENDING ──3 s elapsed, still pending──▶ WAKING
PENDING/WAKING ──all requests settled──▶ IDLE (banner clears automatically, FR-008)
WAKING ──retries exhausted──▶ IDLE + the failing surface shows its localized error state
```

**Rules**: threshold constant (3 000 ms) lives in the store module so the
banner, tests, and mutation testing target one definition. The banner is
informational (amber/attention semantics) — it never replaces per-surface
error states (Principle III).

## Relationships

- `App.tsx` wires E1+E2 into `PersistQueryClientProvider`
  (`persistOptions = { persister, maxAge, buster, dehydrateOptions: { shouldDehydrateQuery } }`).
- `auth.store.ts` (existing) → triggers E1 wipe on logout via the
  `queryClientHandle` singleton seam (same pattern as the existing
  `queryClient.clear()`).
- `api/client.ts` (existing interceptors) → feeds E3; `ServerWakingBanner`
  subscribes to E3.
- Existing per-athlete purge (`purgeQueriesForAthlete`) is unaffected:
  per-athlete keys are never allow-listed, so the parent child-switch decision
  (logout-only device wipe) holds by construction.
