import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MarkdownReportViewer } from "@/components/ai/MarkdownReportViewer";

describe("MarkdownReportViewer", () => {
  it("renderiza markdown con headings y listas", () => {
    const md = `# Título\n\nPárrafo de prueba.\n\n- Item A\n- Item B`;
    render(<MarkdownReportViewer markdown={md} />);
    expect(screen.getByRole("heading", { name: "Título" })).toBeInTheDocument();
    expect(screen.getByText(/Párrafo de prueba/)).toBeInTheDocument();
    expect(screen.getByText("Item A")).toBeInTheDocument();
    expect(screen.getByText("Item B")).toBeInTheDocument();
  });

  it("renderiza citations footer cuando se proveen", () => {
    render(
      <MarkdownReportViewer
        markdown="Texto cualquiera."
        citations={["c1", "c2", "c3"]}
      />,
    );
    expect(screen.getByTestId("markdown-citations")).toBeInTheDocument();
    expect(screen.getByText("c1")).toBeInTheDocument();
    expect(screen.getByText("c2")).toBeInTheDocument();
    expect(screen.getByText("c3")).toBeInTheDocument();
  });

  it("oculta footer de citations si lista vacía", () => {
    render(<MarkdownReportViewer markdown="hola" />);
    expect(screen.queryByTestId("markdown-citations")).not.toBeInTheDocument();
  });

  it("tiene botón Copiar accesible", () => {
    render(<MarkdownReportViewer markdown="hola" />);
    const btn = screen.getByTestId("markdown-copy-button");
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/portapapeles/i),
    );
  });
});
