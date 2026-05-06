import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("leaflet", () => ({
  default: {
    map: vi.fn(() => ({
      setView: vi.fn().mockReturnThis(),
      remove: vi.fn(),
      fitBounds: vi.fn(),
    })),
    tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
    Icon: {
      Default: {
        prototype: {},
        mergeOptions: vi.fn(),
      },
    },
  },
}));

vi.mock("leaflet-gpx", () => ({
  GpxLayer: vi.fn().mockImplementation(() => ({
    on: vi.fn().mockReturnThis(),
    addTo: vi.fn().mockReturnThis(),
  })),
}));

vi.mock("leaflet/dist/leaflet.css", () => ({}));

import { RouteViewer } from "./RouteViewer";

describe("RouteViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("archivo .fit", () => {
    it("muestra fallback para archivos .fit", () => {
      render(<RouteViewer routeFilePath="static/uploads/ruta.fit" />);
      expect(screen.getByText(/Vista previa no disponible/i)).toBeInTheDocument();
      expect(screen.getByText(/\.fit/i)).toBeInTheDocument();
    });

    it("muestra enlace de descarga para .fit", () => {
      render(<RouteViewer routeFilePath="static/uploads/ruta.fit" />);
      const link = screen.getByRole("link", { name: /Descargar archivo/i });
      expect(link).toHaveAttribute("download");
    });
  });

  describe("archivo no soportado", () => {
    it("muestra fallback para extensión desconocida", () => {
      render(<RouteViewer routeFilePath="static/uploads/ruta.tcx" />);
      expect(screen.getByText(/Formato de archivo no soportado/i)).toBeInTheDocument();
    });
  });

  describe("archivo .gpx", () => {
    it("renderiza el contenedor del mapa para .gpx", () => {
      render(<RouteViewer routeFilePath="static/uploads/ruta.gpx" />);
      expect(screen.getByTestId("route-viewer-map")).toBeInTheDocument();
    });

    it("el contenedor tiene aria-label descriptivo", () => {
      render(<RouteViewer routeFilePath="static/uploads/ruta.gpx" />);
      const map = screen.getByTestId("route-viewer-map");
      expect(map).toHaveAttribute("aria-label", "Mapa del recorrido GPX");
    });
  });
});
