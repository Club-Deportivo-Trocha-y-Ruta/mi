import { describe, expect, it } from "vitest";
import type { Query } from "@tanstack/react-query";

import {
  isPersistableKey,
  shouldDehydrateQuery,
} from "@/lib/persistAllowList";

function fakeQuery(
  queryKey: readonly unknown[],
  status: "success" | "error" | "pending" = "success",
): Query {
  return { queryKey, state: { status } } as unknown as Query;
}

describe("persistAllowList — isPersistableKey (default-deny)", () => {
  it("allows the calendar event LIST (metadata only)", () => {
    expect(isPersistableKey(["calendar", "events", {}])).toBe(true);
  });

  it("does NOT allow the single calendar EVENT detail (birthday athlete name)", () => {
    // CalendarEventRead.event_data may be a birthday with athlete_first_name,
    // and audiences may carry athlete_id(s) — privacy audit BLOCK.
    expect(isPersistableKey(["calendar", "event", 5])).toBe(false);
  });

  it("does NOT allow the bare calendar root (would capture attendances)", () => {
    expect(isPersistableKey(["calendar"])).toBe(false);
  });

  it("allows available-race-events for the calendar dropdown", () => {
    expect(
      isPersistableKey([
        "calendar",
        "race-events",
        "available-for-calendar",
        2026,
      ]),
    ).toBe(true);
  });

  it("allows race-event metadata (list + detail) and revision reasons", () => {
    expect(isPersistableKey(["raceEvents", "list", {}])).toBe(true);
    expect(isPersistableKey(["raceEvents", "detail", 7])).toBe(true);
    expect(isPersistableKey(["revision-reasons"])).toBe(true);
  });

  it("does NOT allow training sessions (list, detail, attendance, media)", () => {
    // The list item exposes media[].athlete_ids + free-text coach_notes
    // (privacy audit BLOCK); detail/attendance/media are obviously personal.
    expect(isPersistableKey(["training-sessions", 1, {}])).toBe(false);
    expect(isPersistableKey(["training-session", 1, 99])).toBe(false);
    expect(isPersistableKey(["training-session-attendance", 1, 99])).toBe(false);
    expect(isPersistableKey(["training-session-media", 1, 99])).toBe(false);
  });

  it("DENIES minor-identifying race data (standings/results/competitors)", () => {
    expect(isPersistableKey(["raceStandings", "event", 1, {}])).toBe(false);
    expect(isPersistableKey(["raceResults", "event", 1, {}])).toBe(false);
    expect(isPersistableKey(["competitors", "event", 1])).toBe(false);
  });

  it("DENIES attendance, anthropometry, AI, athlete, parent, newsletter, consent", () => {
    expect(isPersistableKey(["calendar", "attendances", 5])).toBe(false);
    expect(isPersistableKey(["anthropometry", 7])).toBe(false);
    expect(isPersistableKey(["ai", "phv", 7])).toBe(false);
    expect(isPersistableKey(["athlete", 7])).toBe(false);
    expect(isPersistableKey(["athletes", {}])).toBe(false);
    expect(isPersistableKey(["my-athletes", 3])).toBe(false);
    expect(isPersistableKey(["parent-sessions", 3, {}, []])).toBe(false);
    expect(isPersistableKey(["parent-monthly-summary", 3, 2026, 6, 1])).toBe(
      false,
    );
    expect(isPersistableKey(["athlete-newsletters", 42])).toBe(false);
    expect(isPersistableKey(["my-consent", 3])).toBe(false);
    expect(isPersistableKey(["raceAnalysis", "event", 1])).toBe(false);
    expect(isPersistableKey(["club-insights-by-race", 1])).toBe(false);
    expect(isPersistableKey(["season-panorama", 2026, 1])).toBe(false);
  });

  it("denies an unknown/new key by default (default-deny)", () => {
    expect(isPersistableKey(["some-brand-new-feature", 1])).toBe(false);
    expect(isPersistableKey([])).toBe(false);
  });
});

describe("persistAllowList — shouldDehydrateQuery", () => {
  it("persists only successful allow-listed queries", () => {
    expect(
      shouldDehydrateQuery(fakeQuery(["calendar", "events", {}], "success")),
    ).toBe(true);
  });

  it("does NOT persist non-success queries even if allow-listed", () => {
    expect(
      shouldDehydrateQuery(fakeQuery(["calendar", "events", {}], "error")),
    ).toBe(false);
    expect(
      shouldDehydrateQuery(fakeQuery(["calendar", "events", {}], "pending")),
    ).toBe(false);
  });

  it("does NOT persist denied keys even when successful", () => {
    expect(
      shouldDehydrateQuery(fakeQuery(["raceStandings", "event", 1, {}])),
    ).toBe(false);
    expect(shouldDehydrateQuery(fakeQuery(["anthropometry", 7]))).toBe(false);
  });
});
