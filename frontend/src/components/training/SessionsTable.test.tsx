import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SessionsTable } from "./SessionsTable";
import type { TrainingSession } from "@/types/trainingSession.types";

function makeSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 10,
    status: "planned",
    scheduled_date: "2026-06-15",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Pista XCO Buitrera",
    technical_focus: "Técnica de frenada",
    description: "Sesión de técnica básica",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    attendance_summary: {
      total: 10,
      presentes: 8,
      ausentes: 1,
      justificados: 1,
      tardes: 0,
      lesionados: 0,
    },
    ...overrides,
  };
}

function renderTable(
  items: TrainingSession[],
  onExecute?: (id: number) => void,
  onCancel?: (id: number) => void,
) {
  return render(
    <MemoryRouter>
      <SessionsTable items={items} onExecute={onExecute} onCancel={onCancel} />
    </MemoryRouter>,
  );
}

describe("SessionsTable", () => {
  describe("encabezados", () => {
    it("muestra los encabezados de columna", () => {
      renderTable([makeSession()]);
      expect(screen.getByText("Fecha")).toBeInTheDocument();
      expect(screen.getByText("Hora")).toBeInTheDocument();
      expect(screen.getByText("Foco técnico")).toBeInTheDocument();
      expect(screen.getByText("Lugar")).toBeInTheDocument();
      expect(screen.getByText("Estado")).toBeInTheDocument();
      expect(screen.getByText("Asistencia")).toBeInTheDocument();
      expect(screen.getByText("Acciones")).toBeInTheDocument();
    });
  });

  describe("filas con datos", () => {
    it("muestra la fecha formateada", () => {
      renderTable([makeSession()]);
      expect(screen.getAllByText("15/06/2026").length).toBeGreaterThanOrEqual(1);
    });

    it("muestra el badge de estado correcto para planned", () => {
      renderTable([makeSession({ status: "planned" })]);
      expect(screen.getAllByText("Planificada").length).toBeGreaterThanOrEqual(1);
    });

    it("muestra el badge de estado correcto para executed", () => {
      renderTable([makeSession({ status: "executed" })]);
      expect(screen.getAllByText("Ejecutada").length).toBeGreaterThanOrEqual(1);
    });

    it("muestra el badge de estado correcto para cancelled", () => {
      renderTable([makeSession({ status: "cancelled" })]);
      expect(screen.getAllByText("Cancelada").length).toBeGreaterThanOrEqual(1);
    });

    it("muestra presentes/total cuando hay summary disponible", () => {
      renderTable([makeSession()]);
      expect(screen.getAllByText("8/10").length).toBeGreaterThanOrEqual(1);
    });

    it("muestra '—' cuando no hay summary de asistencia", () => {
      renderTable([makeSession({ attendance_summary: null })]);
      expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("botones de acción", () => {
    it("muestra el link Ver apuntando al detalle", () => {
      renderTable([makeSession({ id: 1 })]);
      const verLinks = screen.getAllByRole("link", { name: /Ver/i });
      expect(verLinks.some((l) => l.getAttribute("href") === "/training/sessions/1")).toBe(true);
    });

    it("muestra el link Editar para sesiones no canceladas", () => {
      renderTable([makeSession({ status: "planned" })]);
      const editLinks = screen.getAllByRole("link", { name: /Editar/i });
      expect(editLinks.some((l) => l.getAttribute("href") === "/training/sessions/1/edit")).toBe(true);
    });

    it("no muestra Editar para sesiones canceladas", () => {
      renderTable([makeSession({ status: "cancelled" })]);
      const editLinks = screen.queryAllByRole("link", { name: /Editar/i });
      expect(editLinks.length).toBe(0);
    });

    it("muestra botón Ejecutar solo para planned", () => {
      const onExecute = vi.fn();
      renderTable([makeSession({ status: "planned" })], onExecute);
      const btns = screen.getAllByRole("button", { name: /Ejecutar/i });
      expect(btns.length).toBeGreaterThanOrEqual(1);
    });

    it("no muestra botón Ejecutar para executed", () => {
      const onExecute = vi.fn();
      renderTable([makeSession({ status: "executed" })], onExecute);
      expect(screen.queryAllByRole("button", { name: /Ejecutar/i }).length).toBe(0);
    });

    it("llama onExecute con el id correcto", () => {
      const onExecute = vi.fn();
      renderTable([makeSession({ id: 5 })], onExecute);
      const btns = screen.getAllByRole("button", { name: /Ejecutar/i });
      fireEvent.click(btns[0]);
      expect(onExecute).toHaveBeenCalledWith(5);
    });

    it("llama onCancel con el id correcto", () => {
      const onCancel = vi.fn();
      renderTable([makeSession({ id: 7, status: "planned" })], undefined, onCancel);
      const btns = screen.getAllByRole("button", { name: /Cancelar/i });
      fireEvent.click(btns[0]);
      expect(onCancel).toHaveBeenCalledWith(7);
    });
  });

  describe("lista vacía", () => {
    it("renderiza la tabla sin filas cuando la lista está vacía", () => {
      renderTable([]);
      expect(screen.getByText("Fecha")).toBeInTheDocument();
      expect(screen.queryAllByRole("button", { name: /Ejecutar/i }).length).toBe(0);
    });
  });
});
