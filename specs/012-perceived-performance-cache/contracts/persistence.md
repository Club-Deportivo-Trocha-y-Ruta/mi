# Contract: Device-Storage Persistence

**Feature**: 012-perceived-performance-cache

This feature exposes no new backend endpoints. Its externally observable
contract is the device-storage payload and its governance rules — relied on by
tests, the privacy audit, and any future feature that wants to persist a query.

## Storage key

| Property | Value |
|---|---|
| Key | `tyr:rq-cache:v1` (follows existing `tyr:` namespace, e.g. session-wizard drafts) |
| Medium | `window.localStorage` |
| Format | JSON — TanStack persist-client envelope: `{ buster, timestamp, clientState }` |
| Version bump | Breaking changes to the envelope or allow-list semantics bump the key suffix (`v2`), never mutate `v1` in place |

## Guarantees (testable)

1. **Allow-list only**: every query under `clientState.queries` has a key
   matching a prefix in `persistAllowList.ts`. Anything else present is a
   contract violation (privacy-invariant test + mutation-testing target).
2. **Wipe on logout**: after `logout()` resolves, `localStorage.getItem('tyr:rq-cache:v1') === null`.
3. **Account scoping**: `buster` is `"{APP_VERSION}:{userId}"`; restore with a
   different userId or APP_VERSION discards the snapshot before hydration.
4. **Expiry**: snapshots older than 24 h (`timestamp` vs now) are discarded on
   restore.
5. **Graceful degradation**: storage read/write/parse failures never throw to
   the UI; the app operates in-memory as today.
6. **No mutations persisted**: `clientState.mutations` is always empty.

## Consumers

- `App.tsx` (`PersistQueryClientProvider`) — sole writer/reader.
- `auth.store.ts` — wipe trigger (via `queryClientHandle` seam).
- Privacy-invariant tests and the `data-privacy-guard` audit — verify
  guarantees 1–4 after exercising athlete/parent flows.
