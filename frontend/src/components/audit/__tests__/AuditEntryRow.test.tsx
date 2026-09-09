import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { AuditEntryRow } from "@/components/audit/AuditEntryRow";
import type { AuditEntryOut } from "@/types/audit.types";

expect.extend(toHaveNoViolations);

function makeEntry(overrides?: Partial<AuditEntryOut>): AuditEntryOut {
  return {
    id: 1,
    occurred_at: "2026-03-14T22:05:41.482913",
    actor_user_id: 10,
    actor_kind: "user",
    actor_role: "coach",
    actor_display_name: "Ana Coach",
    action: "update",
    entity_type: "training_session",
    entity_id: 55,
    entity_label: "la sesión de entrenamiento",
    club_id: 1,
    athlete_id: null,
    reason_code: null,
    reason_label: null,
    sentence_es: "Ana Coach actualizó la sesión de entrenamiento.",
    request_id: "9f1c2b7a4d5e46a8b0c3d9e2f1a7b6c4",
    detail: {
      changed_fields: ["scheduled_date"],
      changed_field_labels: ["Fecha programada"],
      diff: { scheduled_date: { before: "2026-03-10", after: "2026-03-14" } },
      meta: null,
    },
    ...overrides,
  };
}

describe("AuditEntryRow", () => {
  it("renderiza la frase y la hora formateada", () => {
    render(<AuditEntryRow entry={makeEntry()} />);
    expect(
      screen.getByText("Ana Coach actualizó la sesión de entrenamiento."),
    ).toBeInTheDocument();
  });

  it("muestra el motivo cuando reason_label está presente", () => {
    render(
      <AuditEntryRow
        entry={makeEntry({ reason_label: "Clima adverso" })}
      />,
    );
    expect(screen.getByText(/Motivo: Clima adverso/)).toBeInTheDocument();
  });

  it('no muestra "Ver detalle" cuando no hay campos cambiados ni diff', () => {
    render(
      <AuditEntryRow
        entry={makeEntry({
          detail: { changed_fields: [], changed_field_labels: [], diff: null, meta: null },
        })}
      />,
    );
    expect(screen.queryByText("Ver detalle")).not.toBeInTheDocument();
  });

  it('despliega el detalle al hacer clic en "Ver detalle"', async () => {
    const user = userEvent.setup();
    render(<AuditEntryRow entry={makeEntry()} />);

    expect(screen.queryByText(/Fecha programada/)).not.toBeInTheDocument();

    await user.click(screen.getByText("Ver detalle"));

    expect(screen.getByText(/Fecha programada/)).toBeInTheDocument();
    expect(screen.getByText(/scheduled_date/)).toBeInTheDocument();
    expect(screen.getByText(/2026-03-10/)).toBeInTheDocument();
    expect(screen.getByText(/2026-03-14/)).toBeInTheDocument();
  });

  it("nunca renderiza el nombre del atleta ni identificadores de menor — solo el actor adulto", () => {
    render(<AuditEntryRow entry={makeEntry()} />);
    // El único nombre propio permitido es el del actor.
    expect(screen.getByText(/Ana Coach/)).toBeInTheDocument();
    expect(screen.queryByText(/athlete_id/)).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(<AuditEntryRow entry={makeEntry()} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
