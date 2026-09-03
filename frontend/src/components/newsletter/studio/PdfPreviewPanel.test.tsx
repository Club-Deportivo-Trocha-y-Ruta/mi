import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";

import { PdfPreviewPanel } from "@/components/newsletter/studio/PdfPreviewPanel";

describe("PdfPreviewPanel", () => {
  it("muestra el botón de descarga y dispara onDownloadPdf al hacer click", () => {
    const onDownloadPdf = vi.fn();
    render(<PdfPreviewPanel onDownloadPdf={onDownloadPdf} />);
    expect(screen.getByTestId("pdf-preview-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("pdf-preview-download-pdf"));
    expect(onDownloadPdf).toHaveBeenCalledTimes(1);
  });

  it("respeta canDownloadPdf=false deshabilitando el botón", () => {
    render(<PdfPreviewPanel onDownloadPdf={vi.fn()} canDownloadPdf={false} />);
    expect(screen.getByTestId("pdf-preview-download-pdf")).toBeDisabled();
  });

  it("deshabilita el botón y cambia la etiqueta mientras se descarga", () => {
    render(<PdfPreviewPanel onDownloadPdf={vi.fn()} isDownloadingPdf />);
    const button = screen.getByTestId("pdf-preview-download-pdf");
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Generando…");
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = render(<PdfPreviewPanel onDownloadPdf={vi.fn()} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
