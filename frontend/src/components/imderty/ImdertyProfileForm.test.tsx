/**
 * Tests de ImdertyProfileForm (feature 047, US2, T037).
 *
 * Cubre: validación inline (documento numérico para R.C/T.I/C.C), el aviso
 * de documento duplicado devuelto por el backend, y que el submit dispara
 * la mutation con el payload esperado. `useUpdateImdertyProfile` y
 * `useBarrios` (usado internamente por `BarrioCombobox`) se mockean — mismo
 * patrón que `ImdertyProfileCard.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { ImdertyProfile } from "@/schemas/imderty";

// jsdom no implementa ResizeObserver — lo necesita `@radix-ui/react-checkbox`
// (checkbox de confirmación de apellidos) para dimensionar su input nativo
// oculto. Mismo patrón que `EditCourseDescriptionDialog.test.tsx`.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
// Polyfills de jsdom requeridos por Radix Select (mismo patrón que
// `ArchivedAthletesPage.test.tsx`/`StaffPage.test.tsx`).
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

const mutateMock = vi.fn();
const updateProfileState = { isPending: false };
vi.mock("@/hooks/useImderty", () => ({
  useUpdateImdertyProfile: () => ({ mutate: mutateMock, isPending: updateProfileState.isPending }),
  useBarrios: () => ({
    data: [
      { id: 1, name: "Bello Horizonte", zone: "1", is_active: true },
      { id: 2, name: "La Dolores", zone: "ZONA NORTE", is_active: true },
    ],
    isLoading: false,
    isError: false,
  }),
}));

import { ImdertyProfileForm } from "@/components/imderty/ImdertyProfileForm";

function makeProfile(overrides?: Partial<ImdertyProfile>): ImdertyProfile {
  return {
    athlete_id: 7,
    first_surname: "Ficticio",
    second_surname: "Prueba",
    surname_split: { confirmed: true, proposed_first: null, proposed_second: null },
    document_type: null,
    document_number: null,
    address: null,
    barrio: null,
    other_municipality: false,
    school: null,
    grade: null,
    eps: null,
    phone: null,
    guardians: [],
    effective_phone_source: null,
    sensitive: { authorization: null },
    ...overrides,
  };
}

function renderForm(profile: ImdertyProfile = makeProfile()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ImdertyProfileForm athleteId={profile.athlete_id} profile={profile} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  updateProfileState.isPending = false;
});

describe("ImdertyProfileForm — validación", () => {
  it("documento C.C con letras muestra el error inline y no envía el formulario", async () => {
    const user = userEvent.setup();
    renderForm(makeProfile({ document_type: "cc", document_number: "" }));

    const documentNumber = screen.getByLabelText("Número de documento");
    await user.type(documentNumber, "12A34");
    await user.click(screen.getByRole("button", { name: /Guardar perfil/i }));

    expect(await screen.findByText("Solo dígitos para R.C, T.I y C.C")).toBeInTheDocument();
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it("documento C.C solo numérico no dispara el error y sí envía el formulario", async () => {
    const user = userEvent.setup();
    renderForm(makeProfile({ document_type: "cc", document_number: "" }));

    await user.type(screen.getByLabelText("Número de documento"), "1234567");
    await user.click(screen.getByRole("button", { name: /Guardar perfil/i }));

    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    expect(
      screen.queryByText("Solo dígitos para R.C, T.I y C.C"),
    ).not.toBeInTheDocument();
  });
});

describe("ImdertyProfileForm — aviso de documento duplicado", () => {
  it("muestra la alerta cuando la respuesta trae 'duplicate_document_in_club'", async () => {
    mutateMock.mockImplementation((_values, opts) => {
      opts.onSuccess({ profile: makeProfile(), warnings: ["duplicate_document_in_club"] });
    });
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: /Guardar perfil/i }));

    expect(await screen.findByText("Documento duplicado")).toBeInTheDocument();
  });

  it("no muestra la alerta cuando no hay warnings", async () => {
    mutateMock.mockImplementation((_values, opts) => {
      opts.onSuccess({ profile: makeProfile(), warnings: [] });
    });
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: /Guardar perfil/i }));

    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Documento duplicado")).not.toBeInTheDocument();
  });
});

describe("ImdertyProfileForm — submit", () => {
  it("envía el payload con los valores del perfil", async () => {
    const user = userEvent.setup();
    renderForm(
      makeProfile({
        address: "Calle ficticia 1",
        eps: "EPS ficticia",
      }),
    );

    await user.click(screen.getByRole("button", { name: /Guardar perfil/i }));

    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    const [payload] = mutateMock.mock.calls[0] as [Record<string, unknown>, unknown];
    expect(payload).toMatchObject({
      address: "Calle ficticia 1",
      eps: "EPS ficticia",
      confirm_surname_split: true,
    });
  });
});

describe("ImdertyProfileForm — accesibilidad", () => {
  it("0 violaciones jest-axe", async () => {
    const { container } = renderForm();
    await screen.findByLabelText("Número de documento");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
