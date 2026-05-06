import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AthletesMultiSelect } from "./AthletesMultiSelect";

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: vi.fn(),
}));

import { useAthletes } from "@/hooks/athletes/useAthletes";
import { Sex } from "@/types/enums";

const mockAthletes = [
  {
    id: 1,
    first_name: "Sebastián",
    last_name: "García",
    category: "Pre-Infantil A",
    sex: Sex.M,
    birth_date: "2014-01-01",
    age_decimal: 12.3,
    club_id: 1,
    user_id: 10,
    club_join_date: null,
    years_in_club: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: 2,
    first_name: "Laura",
    last_name: "Martínez",
    category: "Pre-juvenil A",
    sex: Sex.F,
    birth_date: "2012-01-01",
    age_decimal: 14.1,
    club_id: 1,
    user_id: 11,
    club_join_date: null,
    years_in_club: null,
    created_at: "2026-01-01T00:00:00Z",
  },
];

beforeEach(() => {
  vi.mocked(useAthletes).mockReturnValue({
    data: { items: mockAthletes, total: 2 },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAthletes>);
});

describe("AthletesMultiSelect", () => {
  it("filtra atletas por age_group u12", () => {
    render(
      <AthletesMultiSelect ageGroup="u12" value={[]} onChange={vi.fn()} />,
    );
    expect(screen.getByText(/Sebastián García/)).toBeInTheDocument();
    expect(screen.queryByText(/Laura Martínez/)).not.toBeInTheDocument();
  });

  it("filtra atletas por age_group u15", () => {
    render(
      <AthletesMultiSelect ageGroup="u15" value={[]} onChange={vi.fn()} />,
    );
    expect(screen.queryByText(/Sebastián García/)).not.toBeInTheDocument();
    expect(screen.getByText(/Laura Martínez/)).toBeInTheDocument();
  });

  it("muestra todos los atletas cuando no hay age_group", () => {
    render(
      <AthletesMultiSelect ageGroup="" value={[]} onChange={vi.fn()} />,
    );
    expect(screen.getByText(/Sebastián García/)).toBeInTheDocument();
    expect(screen.getByText(/Laura Martínez/)).toBeInTheDocument();
  });

  it("toggle añade atleta al hacer click en checkbox", () => {
    const onChange = vi.fn();
    render(
      <AthletesMultiSelect ageGroup="" value={[]} onChange={onChange} />,
    );
    const checkbox = screen.getByRole("checkbox", {
      name: /Convocar a Sebastián García/i,
    });
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith([1]);
  });

  it("toggle elimina atleta ya seleccionado", () => {
    const onChange = vi.fn();
    render(
      <AthletesMultiSelect ageGroup="" value={[1]} onChange={onChange} />,
    );
    const checkbox = screen.getByRole("checkbox", {
      name: /Convocar a Sebastián García/i,
    });
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("botón Todos selecciona todos los filtrados", () => {
    const onChange = vi.fn();
    render(
      <AthletesMultiSelect ageGroup="" value={[]} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Todos/i }));
    expect(onChange).toHaveBeenCalledWith([1, 2]);
  });

  it("botón Limpiar vacía la selección", () => {
    const onChange = vi.fn();
    render(
      <AthletesMultiSelect ageGroup="" value={[1, 2]} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Limpiar/i }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("filtra por búsqueda de texto", () => {
    render(
      <AthletesMultiSelect ageGroup="" value={[]} onChange={vi.fn()} />,
    );
    const input = screen.getByPlaceholderText(/Buscar atleta/i);
    fireEvent.change(input, { target: { value: "laura" } });
    expect(screen.getByText(/Laura Martínez/)).toBeInTheDocument();
    expect(screen.queryByText(/Sebastián García/)).not.toBeInTheDocument();
  });

  it("muestra contador de seleccionados", () => {
    render(
      <AthletesMultiSelect ageGroup="" value={[1, 2]} onChange={vi.fn()} />,
    );
    expect(screen.getByText(/2 atletas seleccionados/i)).toBeInTheDocument();
  });

  it("muestra mensaje de error cuando se pasa", () => {
    render(
      <AthletesMultiSelect
        ageGroup=""
        value={[]}
        onChange={vi.fn()}
        error="Debes convocar al menos un atleta"
      />,
    );
    expect(screen.getByText("Debes convocar al menos un atleta")).toBeInTheDocument();
  });

  it("muestra skeleton mientras carga", () => {
    vi.mocked(useAthletes).mockReturnValueOnce({
      data: undefined,
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useAthletes>);
    const { container } = render(
      <AthletesMultiSelect ageGroup="" value={[]} onChange={vi.fn()} />,
    );
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });
});
