/**
 * ProjectProfilePage.test.tsx
 *
 * Tests para la página de edición del perfil de proyecto del club.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/trainingSessions", () => ({
  useProjectProfile: vi.fn(),
  useUpsertProjectProfile: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "T", club_ids: [1] },
    }),
  ),
}));

import { useProjectProfile, useUpsertProjectProfile } from "@/api/trainingSessions";
import { ProjectProfilePage } from "./ProjectProfilePage";
import type { ProjectProfile } from "@/types/trainingSession.types";

// ---------------------------------------------------------------------------
// Stubs
// ---------------------------------------------------------------------------

const mutationStub = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  isIdle: true,
  data: undefined,
  error: null,
  reset: vi.fn(),
  mutateAsync: vi.fn(),
};

function makeProfile(overrides?: Partial<ProjectProfile>): ProjectProfile {
  return {
    project_name: "Formación XCO",
    executing_entity: "Club Trocha y Ruta",
    report_responsible: "Entrenador Principal",
    purpose: "Promover el deporte juvenil.",
    general_objective: "Desarrollar ciclistas XCO.",
    specific_objectives: ["Técnica de frenada", "Resistencia aeróbica"],
    territory_location: "Cali, Valle del Cauca",
    territory_description: "Zona montañosa del sur del Valle.",
    ...overrides,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training/reports/project-profile"]}>
        <Routes>
          <Route path="/training/reports/project-profile" element={<ProjectProfilePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useUpsertProjectProfile).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useUpsertProjectProfile>,
  );
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ProjectProfilePage", () => {
  it("muestra skeleton durante la carga", () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    } as unknown as ReturnType<typeof useProjectProfile>);
    const { container } = renderPage();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("renderiza el formulario con todos los campos", async () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: null,
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText(/Nombre del proyecto/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Entidad ejecutora/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Responsable del informe/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Propósito/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Objetivo general/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Municipio/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Descripción del territorio/i)).toBeInTheDocument();
    });
  });

  it("puebla el form con datos existentes del perfil", async () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeProfile(),
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText(/Nombre del proyecto/i)).toHaveValue("Formación XCO");
      expect(screen.getByLabelText(/Entidad ejecutora/i)).toHaveValue("Club Trocha y Ruta");
    });
  });

  it("trata 404 como perfil vacío (data=null) — muestra form vacío", async () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: null,
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText(/Nombre del proyecto/i)).toHaveValue("");
    });
  });

  it("muestra los objetivos específicos como campos editables", async () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeProfile(),
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();
    await waitFor(() => {
      expect(screen.getByDisplayValue("Técnica de frenada")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Resistencia aeróbica")).toBeInTheDocument();
    });
  });

  it("puede añadir un objetivo específico", async () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeProfile({ specific_objectives: [] }),
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("add-objective-btn")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("add-objective-btn"));
    await waitFor(() => {
      expect(screen.getByLabelText("Objetivo específico 1")).toBeInTheDocument();
    });
  });

  it("puede eliminar un objetivo específico", async () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: makeProfile({ specific_objectives: ["Objetivo A"] }),
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();
    await waitFor(() => {
      expect(screen.getByDisplayValue("Objetivo A")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText("Eliminar objetivo 1"));
    await waitFor(() => {
      expect(screen.queryByDisplayValue("Objetivo A")).not.toBeInTheDocument();
    });
  });

  it("el botón Guardar llama a upsertMutation con el payload", async () => {
    const mutateMock = vi.fn();
    vi.mocked(useUpsertProjectProfile).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useUpsertProjectProfile>);
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: null,
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText(/Nombre del proyecto/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Nombre del proyecto/i), {
      target: { value: "Mi proyecto" },
    });

    fireEvent.click(screen.getByTestId("save-profile-btn"));

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith(
        expect.objectContaining({ project_name: "Mi proyecto" }),
        expect.anything(),
      );
    });
  });

  it("muestra mensaje de éxito tras guardar", async () => {
    const mutateMock = vi.fn((_payload, opts) => opts?.onSuccess?.());
    vi.mocked(useUpsertProjectProfile).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useUpsertProjectProfile>);
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: null,
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();

    await waitFor(() => screen.getByTestId("save-profile-btn"));

    fireEvent.change(screen.getByLabelText(/Nombre del proyecto/i), {
      target: { value: "X" },
    });
    fireEvent.click(screen.getByTestId("save-profile-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("save-success-msg")).toBeInTheDocument();
    });
  });

  it("muestra mensaje de error cuando falla el guardado", async () => {
    const mutateMock = vi.fn((_payload, opts) => opts?.onError?.());
    vi.mocked(useUpsertProjectProfile).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useUpsertProjectProfile>);
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: null,
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();

    await waitFor(() => screen.getByTestId("save-profile-btn"));

    fireEvent.change(screen.getByLabelText(/Nombre del proyecto/i), {
      target: { value: "X" },
    });
    fireEvent.click(screen.getByTestId("save-profile-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("save-error-msg")).toBeInTheDocument();
    });
  });

  it("tiene el enlace de vuelta a informes mensuales", async () => {
    vi.mocked(useProjectProfile).mockReturnValue({
      isLoading: false,
      isError: false,
      data: null,
    } as unknown as ReturnType<typeof useProjectProfile>);
    renderPage();
    await waitFor(() => {
      const link = screen.getByText(/← Informes del club/i);
      expect(link).toBeInTheDocument();
      expect(link.closest("a")).toHaveAttribute("href", "/training/reports");
    });
  });
});
