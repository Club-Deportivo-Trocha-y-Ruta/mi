import "@testing-library/jest-dom";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect } from "vitest";
import { toHaveNoViolations } from "jest-axe";
import { trainingHandlers } from "./msw/trainingHandlers";
import { calendarHandlers } from "./msw/calendarHandlers";
import {
  athleteRaceAnalysisHandlers,
  clubInsightsByRaceHandler,
} from "./msw/athleteRaceAnalysisHandlers";
import { sessionAssistantHandlers } from "./msw/sessionAssistantHandlers";

// Extend Vitest's expect with jest-axe matchers (idempotente: extend
// usa Object.assign internamente, así que múltiples llamadas son no-op).
expect.extend(toHaveNoViolations);

export const mswServer = setupServer(
  ...trainingHandlers,
  ...calendarHandlers,
  ...athleteRaceAnalysisHandlers,
  clubInsightsByRaceHandler,
  ...sessionAssistantHandlers,
);

beforeAll(() => mswServer.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => mswServer.resetHandlers());
afterAll(() => mswServer.close());
