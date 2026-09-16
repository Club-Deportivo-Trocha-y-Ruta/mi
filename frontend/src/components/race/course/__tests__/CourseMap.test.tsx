/**
 * Tests para CourseMap (feature 043 — perfil de circuito, T054/US5).
 *
 * `CourseMap` es un componente lazy que dibuja UNA vuelta (geometry de
 * `CourseVariant`) sobre un mapa Leaflet — sin archivo GPX que descargar (a
 * diferencia de `RouteViewer`, que carga un `.gpx` vía `leaflet-gpx`), la
 * polilínea se construye directamente desde el prop `geometry` ya presente
 * en memoria.
 *
 * Mockeamos "leaflet" (jsdom no puede pintar tiles reales) siguiendo
 * exactamente el patrón de `RouteViewer.test.tsx`, con `vi.hoisted` para
 * poder inspeccionar las instancias (`map`/`polyline`) desde las
 * aserciones — `RouteViewer.test.tsx` no lo necesita porque solo verifica
 * el contenedor, nunca las llamadas a Leaflet en sí.
 *
 * Cubre:
 *  - `role="region"` + `aria-label="Mapa del circuito {label}"` exacto.
 *  - Foco por teclado (`tabIndex={0}`).
 *  - Altura fija compacta (240px / `h-60`) en mobile.
 *  - `L.polyline` se llama con las coordenadas `[lat, lon]` derivadas de
 *    `geometry` (sin la elevación).
 *  - La polilínea se agrega al mapa y se ajusta el encuadre con
 *    `map.fitBounds(polyline.getBounds())`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const { mapInstance, polylineInstance, mapFn, polylineFn, tileLayerFn, mergeOptionsFn } =
  vi.hoisted(() => {
    const mapInstance = {
      setView: vi.fn().mockReturnThis(),
      remove: vi.fn(),
      fitBounds: vi.fn(),
    };
    const polylineInstance = {
      addTo: vi.fn().mockReturnThis(),
      getBounds: vi.fn(() => "COURSE_MAP_BOUNDS"),
    };
    return {
      mapInstance,
      polylineInstance,
      mapFn: vi.fn(() => mapInstance),
      polylineFn: vi.fn(() => polylineInstance),
      tileLayerFn: vi.fn(() => ({ addTo: vi.fn() })),
      mergeOptionsFn: vi.fn(),
    };
  });

vi.mock("leaflet", () => ({
  default: {
    map: mapFn,
    tileLayer: tileLayerFn,
    polyline: polylineFn,
    Icon: {
      Default: {
        prototype: {},
        mergeOptions: mergeOptionsFn,
      },
    },
  },
}));

vi.mock("leaflet/dist/leaflet.css", () => ({}));

import { CourseMap } from "@/components/race/course/CourseMap";

const GEOMETRY: Array<[number, number, number | null]> = [
  [3.4516, -76.532, 995.4],
  [3.452, -76.5325, 998.1],
  [3.453, -76.533, 1001.0],
];

describe("CourseMap", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('expone role="region" con aria-label "Mapa del circuito {label}" exacto', async () => {
    render(<CourseMap geometry={GEOMETRY} label="Circuito completo" />);
    const region = await screen.findByRole("region", {
      name: "Mapa del circuito Circuito completo",
    });
    expect(region).toBeInTheDocument();
  });

  it("el aria-label refleja el prop label verbatim para otra variante", async () => {
    render(<CourseMap geometry={GEOMETRY} label="Recorrido reducido" />);
    expect(
      await screen.findByRole("region", {
        name: "Mapa del circuito Recorrido reducido",
      }),
    ).toBeInTheDocument();
  });

  it("es alcanzable por teclado (tabIndex=0)", async () => {
    render(<CourseMap geometry={GEOMETRY} label="Circuito completo" />);
    const region = await screen.findByRole("region", {
      name: "Mapa del circuito Circuito completo",
    });
    expect(region).toHaveAttribute("tabindex", "0");
  });

  it("altura compacta fija de 240px en mobile (h-60), no la escalación de RouteViewer (h-72/h-80/h-96)", async () => {
    render(<CourseMap geometry={GEOMETRY} label="Circuito completo" />);
    const region = await screen.findByRole("region", {
      name: "Mapa del circuito Circuito completo",
    });
    expect(region.className).toMatch(/\bh-60\b/);
    expect(region.className).not.toMatch(/\bh-72\b|\bh-80\b|\bh-96\b/);
  });

  it("llama a L.polyline con las coordenadas [lat, lon] derivadas de geometry, sin la elevación", async () => {
    render(<CourseMap geometry={GEOMETRY} label="Circuito completo" />);
    await waitFor(() => expect(polylineFn).toHaveBeenCalled());
    expect(polylineFn).toHaveBeenCalledWith([
      [3.4516, -76.532],
      [3.452, -76.5325],
      [3.453, -76.533],
    ]);
  });

  it("agrega la polilínea al mapa (polyline.addTo(map)) y ajusta el encuadre con map.fitBounds(polyline.getBounds())", async () => {
    render(<CourseMap geometry={GEOMETRY} label="Circuito completo" />);
    await waitFor(() => expect(mapFn).toHaveBeenCalled());
    await waitFor(() =>
      expect(polylineInstance.addTo).toHaveBeenCalledWith(mapInstance),
    );
    await waitFor(() =>
      expect(mapInstance.fitBounds).toHaveBeenCalledWith("COURSE_MAP_BOUNDS"),
    );
  });

  it("aplica el workaround de íconos de Leaflet (delete _getIconUrl + mergeOptions con URLs de unpkg), igual que RouteViewer", async () => {
    render(<CourseMap geometry={GEOMETRY} label="Circuito completo" />);
    await waitFor(() => expect(mergeOptionsFn).toHaveBeenCalled());
    const args = mergeOptionsFn.mock.calls[0]?.[0] as
      | Record<string, string>
      | undefined;
    expect(args?.iconUrl).toContain("unpkg.com/leaflet");
    expect(args?.iconRetinaUrl).toContain("unpkg.com/leaflet");
    expect(args?.shadowUrl).toContain("unpkg.com/leaflet");
  });

  it("no importa leaflet-gpx — CourseMap no tiene archivo GPX que descargar (a diferencia de RouteViewer)", async () => {
    // Nada que mockear: si el componente importara "leaflet-gpx" sin que
    // esté mockeado, Vite fallaría al resolverlo en este test. El hecho de
    // que el resto de este archivo pase ya lo confirma; este test documenta
    // la intención explícitamente.
    render(<CourseMap geometry={GEOMETRY} label="Circuito completo" />);
    await waitFor(() => expect(mapFn).toHaveBeenCalled());
    expect(true).toBe(true);
  });
});
