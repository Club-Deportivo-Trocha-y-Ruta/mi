/**
 * Tests para RaceUploadZone.
 *
 * Cubre:
 *  - dropzone visible idle
 *  - rechazo extensión no permitida
 *  - rechazo tamaño excede
 *  - rechazo magic bytes PDF inválido
 *  - aceptación PDF válido (magic bytes %PDF-)
 *  - aceptación CSV UTF-8 (modo resultados)
 *  - reset al hacer click en quitar
 *  - a11y axe sin violaciones
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { RaceUploadZone } from "@/components/competitions/import/RaceUploadZone";

expect.extend(toHaveNoViolations);

function makePdf(name: string, sizeBytes = 1024): File {
  // Construye un blob con cabecera %PDF- válida.
  const header = new TextEncoder().encode("%PDF-1.4\n");
  const padding = new Uint8Array(Math.max(0, sizeBytes - header.length));
  const blob = new Blob([header, padding], { type: "application/pdf" });
  return new File([blob], name, { type: "application/pdf" });
}

function makeBadPdf(name: string, sizeBytes = 1024): File {
  // Sin cabecera %PDF-: simula PDF inválido.
  const data = new Uint8Array(sizeBytes).fill(0x41); // "AAAA…"
  const blob = new Blob([data], { type: "application/pdf" });
  return new File([blob], name, { type: "application/pdf" });
}

function makeCsv(name: string, content = "id,nombre,tiempo\n1,test,01:23:45\n"): File {
  return new File([content], name, { type: "text/csv" });
}

describe("RaceUploadZone", () => {
  it("muestra el dropzone vacío inicialmente", () => {
    render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={null}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByTestId("race-upload-resultados-dropzone"),
    ).toBeInTheDocument();
  });

  it("rechaza archivo con extensión no permitida", async () => {
    const onChange = vi.fn();
    render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={null}
        onChange={onChange}
      />,
    );
    const input = screen.getByTestId(
      "race-upload-resultados-input",
    ) as HTMLInputElement;
    const file = new File(["x"], "doc.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", { value: [file] });
    fireEvent.change(input);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Formato no permitido/i,
    );
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("rechaza archivo que excede el tamaño máximo", async () => {
    const onChange = vi.fn();
    render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={null}
        onChange={onChange}
        maxMb={1}
      />,
    );
    const input = screen.getByTestId(
      "race-upload-resultados-input",
    ) as HTMLInputElement;
    const big = makePdf("big.pdf", 2 * 1024 * 1024);
    Object.defineProperty(input, "files", { value: [big] });
    fireEvent.change(input);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /excede el límite/i,
    );
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("rechaza PDF sin cabecera %PDF-", async () => {
    const onChange = vi.fn();
    render(
      <RaceUploadZone
        kind="general"
        label="General"
        value={null}
        onChange={onChange}
      />,
    );
    const input = screen.getByTestId(
      "race-upload-general-input",
    ) as HTMLInputElement;
    const bad = makeBadPdf("fake.pdf");
    Object.defineProperty(input, "files", { value: [bad] });
    fireEvent.change(input);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /cabecera %PDF-/i,
    );
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("acepta PDF válido con cabecera %PDF-", async () => {
    const onChange = vi.fn();
    render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={null}
        onChange={onChange}
      />,
    );
    const input = screen.getByTestId(
      "race-upload-resultados-input",
    ) as HTMLInputElement;
    const good = makePdf("ok.pdf");
    Object.defineProperty(input, "files", { value: [good] });
    fireEvent.change(input);

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(lastCall[0]).toBeInstanceOf(File);
    expect((lastCall[0] as File).name).toBe("ok.pdf");
  });

  it("acepta CSV UTF-8 válido en modo resultados", async () => {
    const onChange = vi.fn();
    render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={null}
        onChange={onChange}
      />,
    );
    const input = screen.getByTestId(
      "race-upload-resultados-input",
    ) as HTMLInputElement;
    const csv = makeCsv("results.csv");
    Object.defineProperty(input, "files", { value: [csv] });
    fireEvent.change(input);

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect((lastCall[0] as File).name).toBe("results.csv");
  });

  it("permite quitar archivo seleccionado", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={makePdf("preview.pdf")}
        onChange={onChange}
      />,
    );
    // Renderiza preview
    expect(
      screen.getByTestId("race-upload-resultados-preview"),
    ).toBeInTheDocument();
    await user.click(screen.getByTestId("race-upload-resultados-remove"));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("acepta archivo via drag-drop", async () => {
    const onChange = vi.fn();
    render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={null}
        onChange={onChange}
      />,
    );
    const dropzone = screen.getByTestId("race-upload-resultados-dropzone");
    const pdf = makePdf("dragged.pdf");
    fireEvent.dragOver(dropzone);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [pdf] },
    });
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect((lastCall[0] as File).name).toBe("dragged.pdf");
  });

  it("teclado: Enter en dropzone dispara click del input file", async () => {
    render(
      <RaceUploadZone
        kind="general"
        label="General"
        value={null}
        onChange={vi.fn()}
      />,
    );
    const dropzone = screen.getByTestId("race-upload-general-dropzone");
    const input = screen.getByTestId(
      "race-upload-general-input",
    ) as HTMLInputElement;
    const clickSpy = vi.spyOn(input, "click");
    fireEvent.keyDown(dropzone, { key: "Enter" });
    expect(clickSpy).toHaveBeenCalled();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <RaceUploadZone
        kind="resultados"
        label="Resultados *"
        value={null}
        onChange={vi.fn()}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 10_000);
});
