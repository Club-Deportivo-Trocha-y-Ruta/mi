import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { useParentContextStore } from "./parentContext.store";
import {
  setQueryClient,
  __resetQueryClientHandleForTests,
} from "@/lib/queryClientHandle";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useParentContextStore", () => {
  beforeEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
    window.localStorage.removeItem("parent-context");
    __resetQueryClientHandleForTests();
  });

  afterEach(() => {
    useParentContextStore.setState({ activeAthleteId: null });
    window.localStorage.removeItem("parent-context");
    __resetQueryClientHandleForTests();
    vi.restoreAllMocks();
  });

  describe("estado inicial", () => {
    it("activeAthleteId comienza como null", () => {
      expect(useParentContextStore.getState().activeAthleteId).toBeNull();
    });
  });

  describe("setActiveAthlete", () => {
    it("actualiza el id activo", () => {
      useParentContextStore.getState().setActiveAthlete(42);
      expect(useParentContextStore.getState().activeAthleteId).toBe(42);
    });

    it("acepta null para limpiar la selección", () => {
      useParentContextStore.setState({ activeAthleteId: 7 });
      // Sin QueryClient registrado, purgeQueriesForAthlete loguea warning
      // pero no debe romper.
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      useParentContextStore.getState().setActiveAthlete(null);
      expect(useParentContextStore.getState().activeAthleteId).toBeNull();
      warnSpy.mockRestore();
    });

    it("persiste el id en localStorage bajo la key 'parent-context'", () => {
      useParentContextStore.getState().setActiveAthlete(99);
      const raw = window.localStorage.getItem("parent-context");
      expect(raw).not.toBeNull();
      // zustand persist serializa { state: {...}, version: ... }
      expect(JSON.parse(raw as string)).toMatchObject({
        state: { activeAthleteId: 99 },
      });
    });

    it("solo persiste activeAthleteId (no funciones)", () => {
      useParentContextStore.getState().setActiveAthlete(5);
      const raw = window.localStorage.getItem("parent-context");
      expect(raw).not.toBeNull();
      const parsed = JSON.parse(raw as string);
      expect(Object.keys(parsed.state)).toEqual(["activeAthleteId"]);
    });
  });

  describe("purga de cache al cambiar de hijo (privacy R4)", () => {
    it("purga del cache las queries del hijo previo al cambiar a otro", () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      setQueryClient(qc);

      // Sembramos cache de TanStack con queries de dos hijos distintos
      qc.setQueryData(["parent-next-session", 1, 10], { id: 100, focus: "kid-10 data" });
      qc.setQueryData(["parent-last-session", 1, 10], { id: 101, focus: "kid-10 data" });
      qc.setQueryData(["parent-next-session", 1, 20], { id: 200, focus: "kid-20 data" });
      qc.setQueryData(["parent-last-session", 1, 20], { id: 201, focus: "kid-20 data" });

      // Inicializamos activeAthleteId = 10 sin disparar purga (setState directo)
      useParentContextStore.setState({ activeAthleteId: 10 });

      // Cambiamos a hijo 20 — debe purgar queries del 10
      useParentContextStore.getState().setActiveAthlete(20);

      // Queries del kid 10 desaparecieron del cache
      expect(qc.getQueryData(["parent-next-session", 1, 10])).toBeUndefined();
      expect(qc.getQueryData(["parent-last-session", 1, 10])).toBeUndefined();
      // Queries del kid 20 permanecen
      expect(qc.getQueryData(["parent-next-session", 1, 20])).toBeDefined();
      expect(qc.getQueryData(["parent-last-session", 1, 20])).toBeDefined();
    });

    it("NO purga cuando prevId es null (primera selección)", () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      setQueryClient(qc);
      qc.setQueryData(["parent-next-session", 1, 10], { id: 100 });

      // prev = null → no purga, simplemente selecciona
      useParentContextStore.getState().setActiveAthlete(10);

      expect(qc.getQueryData(["parent-next-session", 1, 10])).toBeDefined();
    });

    it("NO purga cuando se selecciona el mismo id", () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      setQueryClient(qc);
      qc.setQueryData(["parent-next-session", 1, 10], { id: 100 });

      useParentContextStore.setState({ activeAthleteId: 10 });
      useParentContextStore.getState().setActiveAthlete(10);

      expect(qc.getQueryData(["parent-next-session", 1, 10])).toBeDefined();
    });

    it("purga cuando se cambia a null (volver a 'ver todos')", () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      setQueryClient(qc);
      qc.setQueryData(["parent-next-session", 1, 10], { id: 100 });

      useParentContextStore.setState({ activeAthleteId: 10 });
      useParentContextStore.getState().setActiveAthlete(null);

      expect(qc.getQueryData(["parent-next-session", 1, 10])).toBeUndefined();
    });
  });

  describe("reset", () => {
    it("limpia el id activo", () => {
      useParentContextStore.setState({ activeAthleteId: 7 });
      useParentContextStore.getState().reset();
      expect(useParentContextStore.getState().activeAthleteId).toBeNull();
    });
  });
});
