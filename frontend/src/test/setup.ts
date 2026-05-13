import "@testing-library/jest-dom";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";
import { trainingHandlers } from "./msw/trainingHandlers";
import { calendarHandlers } from "./msw/calendarHandlers";

export const mswServer = setupServer(...trainingHandlers, ...calendarHandlers);

beforeAll(() => mswServer.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => mswServer.resetHandlers());
afterAll(() => mswServer.close());
