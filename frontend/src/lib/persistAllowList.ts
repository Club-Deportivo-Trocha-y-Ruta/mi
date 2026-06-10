/**
 * persistAllowList — default-deny registry governing which TanStack Query
 * entries may be written to device storage (localStorage) for instant return
 * visits (feature 012, US1).
 *
 * PRIVACY (Ley 1581 — minors) — NON-NEGOTIABLE:
 * Only low-sensitivity, NON-personal data may ever persist on the device.
 * Anything that identifies a minor MUST be excluded. The list below is an
 * explicit allow-list: any query key that does not match a prefix here is
 * NOT persisted. New query types therefore default to "not persisted";
 * adding a prefix requires a `data-privacy-guard` review.
 *
 * This list was vetted by the data-privacy-guard audit for feature 012. The
 * deliberate exclusions below each cite the field that would leak — do NOT add
 * any of them without a fresh privacy ruling (and, where noted, a backend
 * change):
 *   - ["raceStandings"|"raceResults"|"competitors", …] — classification/finish
 *     tables embed `display_name` ("puede ser menor"). Publicly posting results
 *     at an event does NOT waive Ley 1581 obligations for device persistence.
 *   - ["calendar","event", id] — `CalendarEventRead.event_data` may be a
 *     birthday (`athlete_first_name`, `age_turning`) and `audiences` may carry
 *     `athlete_id`(s). The calendar LIST (["calendar","events"]) is safe
 *     (metadata only), but the single-event detail is not.
 *   - ["training-sessions", …] — list items expose `media[].athlete_ids` and
 *     free-text `coach_notes` (may contain athlete names / health notes).
 *     Re-enable ONLY with a backend `TrainingSessionListItem` summary schema
 *     that strips media/coach_notes/kid_attendances/route_file_path.
 *   - ["calendar","attendances", …] — who attended (athlete-identifiable).
 *     This is why we allow-list the specific calendar child, never the bare
 *     ["calendar"] root.
 *   - ["raceAnalysis"|"club-insights-by-race"|"athlete-*"|"season-panorama", …]
 *     — AI/analytics about athletes.
 *   - ["anthropometry"|"ai", …] — anthropometry/PHV/medical, AI explanations.
 *   - ["athlete"|"athletes"|"my-athletes"|"dashboard-athlete-details", …] —
 *     athlete profiles.
 *   - ["parent-*"|"my-consent", …] — parent-specific / consent data.
 *   - ["athlete-newsletters"|"athlete-newsletter", …] — newsletters.
 *   - ["training-session"|"training-session-attendance"|"training-session-media",
 *     …] — session detail / attendance / media.
 */
import type { Query, QueryKey } from "@tanstack/react-query";

/**
 * Allow-listed query-key prefixes. A query key is persistable when its leading
 * elements deep-equal one of these prefixes (element-wise). Keep this list
 * small and obviously non-personal — every entry below was confirmed by the
 * privacy audit to contain only event/competition metadata, no minor PII.
 */
export const PERSIST_ALLOWLIST_PREFIXES: readonly (readonly unknown[])[] = [
  // Calendar event LIST metadata (title/date/type). NOT the bare ["calendar"]
  // root (attendances) and NOT single-event detail (birthday athlete names).
  ["calendar", "events"],
  // Race events available for the calendar dropdown (race names/dates, no people).
  ["calendar", "race-events", "available-for-calendar"],
  // Race-event metadata: list + detail (name/date/location/conditions). No names.
  ["raceEvents"],
  // Closed catalog of revision reasons.
  ["revision-reasons"],
] as const;

/** True when `key`'s leading elements match `prefix` element-by-element. */
function keyMatchesPrefix(key: QueryKey, prefix: readonly unknown[]): boolean {
  if (key.length < prefix.length) return false;
  for (let i = 0; i < prefix.length; i += 1) {
    if (!Object.is(key[i], prefix[i])) return false;
  }
  return true;
}

/**
 * Whether a query key is eligible for device persistence. Default-deny: only
 * keys matching an allow-listed prefix return true.
 */
export function isPersistableKey(key: QueryKey): boolean {
  return PERSIST_ALLOWLIST_PREFIXES.some((prefix) =>
    keyMatchesPrefix(key, prefix),
  );
}

/**
 * `dehydrateOptions.shouldDehydrateQuery` predicate for the persister. Persists
 * only successful queries whose key is on the allow-list — never errored/pending
 * queries, never non-allow-listed (potentially personal) data.
 */
export function shouldDehydrateQuery(query: Query): boolean {
  return query.state.status === "success" && isPersistableKey(query.queryKey);
}
