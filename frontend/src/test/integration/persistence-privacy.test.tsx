import { afterEach, describe, expect, it } from "vitest";
import { dehydrate, QueryClient } from "@tanstack/react-query";

import { shouldDehydrateQuery } from "@/lib/persistAllowList";
import { wipePersistedCache, PERSIST_CACHE_KEY } from "@/lib/queryPersister";

afterEach(() => {
  window.localStorage.clear();
});

function seed(client: QueryClient, key: readonly unknown[], data: unknown) {
  client.setQueryData(key as never, data as never);
}

/**
 * Privacy invariants for device persistence (feature 012, INV-1 / INV-2).
 * This is the constitution-mandated regression test for minors' data: it
 * exercises a cache holding BOTH allow-listed and athlete-identifiable
 * queries, then asserts the dehydrated snapshot contains only the former.
 */
describe("persistence privacy invariants", () => {
  it("INV-1: dehydrates ONLY allow-listed keys; never minor-identifying data", () => {
    const client = new QueryClient();

    // Allow-listed, non-personal
    seed(client, ["calendar", "events", {}], [{ id: 1, title: "Valida I" }]);
    seed(client, ["raceEvents", "list", {}], [{ id: 1, name: "Copa Valle" }]);
    seed(client, ["revision-reasons"], ["typo", "missing"]);

    // Athlete-identifiable — MUST NOT be persisted
    seed(client, ["raceStandings", "event", 1, {}], [
      { rider: "MENOR_X", pos: 1 },
    ]);
    seed(client, ["raceResults", "event", 1, {}], [{ rider: "MENOR_W" }]);
    seed(client, ["anthropometry", 7], { phv: 12.3, dob: "2013-01-01" });
    seed(client, ["calendar", "attendances", 1], [{ athlete: "MENOR_Y" }]);
    // Single calendar event: birthday detail embeds a minor's first name.
    seed(client, ["calendar", "event", 1], {
      event_type: "birthday",
      event_data: { athlete_first_name: "MENOR_B", age_turning: 12 },
    });
    // Training-session list: media[].athlete_ids + free-text coach_notes.
    seed(client, ["training-sessions", 9, {}], [
      {
        id: 1,
        title: "Tecnica",
        coach_notes: "MENOR_C con molestia en rodilla",
        media: [{ athlete_ids: [7, 8] }],
      },
    ]);
    seed(client, ["athlete", 7], { name: "MENOR_Z" });
    seed(client, ["athlete-newsletters", 7], [{ child: "MENOR_N" }]);

    const dehydrated = dehydrate(client, { shouldDehydrateQuery });
    const persistedKeys = dehydrated.queries.map((q) => q.queryKey);

    // Allow-listed present
    expect(persistedKeys).toContainEqual(["calendar", "events", {}]);
    expect(persistedKeys).toContainEqual(["raceEvents", "list", {}]);
    expect(persistedKeys).toContainEqual(["revision-reasons"]);

    // Denied prefixes entirely absent
    for (const denied of [
      "raceStandings",
      "raceResults",
      "anthropometry",
      "athlete",
      "athlete-newsletters",
      "training-sessions",
    ]) {
      expect(persistedKeys.some((k) => k[0] === denied)).toBe(false);
    }
    // calendar attendances + single-event detail absent (only the LIST persists)
    expect(
      persistedKeys.some((k) => k[0] === "calendar" && k[1] === "attendances"),
    ).toBe(false);
    expect(
      persistedKeys.some((k) => k[0] === "calendar" && k[1] === "event"),
    ).toBe(false);

    // No minor token anywhere in the serialized snapshot
    const serialized = JSON.stringify(dehydrated);
    for (const token of [
      "MENOR_X",
      "MENOR_W",
      "MENOR_Y",
      "MENOR_Z",
      "MENOR_N",
      "MENOR_B",
      "MENOR_C",
      "2013-01-01",
    ]) {
      expect(serialized).not.toContain(token);
    }
  });

  it("INV-2: wipePersistedCache empties the device snapshot", () => {
    window.localStorage.setItem(
      PERSIST_CACHE_KEY,
      JSON.stringify({ clientState: { queries: [] } }),
    );
    wipePersistedCache();
    expect(window.localStorage.getItem(PERSIST_CACHE_KEY)).toBeNull();
  });
});
