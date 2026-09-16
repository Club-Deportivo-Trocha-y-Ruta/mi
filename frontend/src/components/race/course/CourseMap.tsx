/**
 * CourseMap — mapa Leaflet de UNA vuelta de circuito (feature 043, US5).
 *
 * A diferencia de `RouteViewer` (que descarga y parsea un archivo `.gpx` vía
 * el plugin `leaflet-gpx`), acá no hay archivo que descargar: `geometry` ya
 * viene en memoria (`CourseVariant.geometry`, reducido por el backend a los
 * puntos de una sola vuelta), así que la polilínea se construye
 * directamente a partir del prop. Sin `leaflet-gpx`.
 *
 * Mismo patrón de import dinámico + workaround de íconos que
 * `training/RouteViewer.tsx`, para no pagar el bundle de Leaflet en el
 * chunk inicial (este componente en sí se consume lazy desde `CourseSummary`).
 */
import { useEffect, useRef } from "react";

export interface CourseMapProps {
  /** `CourseVariant.geometry` verbatim — `[lat, lon, elevación|null]`, una vuelta. */
  geometry: Array<[number, number, number | null]>;
  label: string;
}

export function CourseMap({ geometry, label }: CourseMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mapRef.current) return;

    let mapInstance: import("leaflet").Map | null = null;

    async function initMap() {
      const L = (await import("leaflet")).default;
      await import("leaflet/dist/leaflet.css");

      if (!mapRef.current) return;

      // Fix leaflet default icon paths broken by bundlers (mismo workaround
      // que RouteViewer.tsx).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl:
          "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl:
          "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const map = L.map(mapRef.current);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors",
      }).addTo(map);

      // Sin archivo GPX que descargar: la polilínea sale directo de
      // `geometry` — solo [lat, lon], sin la elevación.
      const coords: Array<[number, number]> = geometry.map(
        ([lat, lon]): [number, number] => [lat, lon],
      );
      const polyline = L.polyline(coords);
      // `setStyle` no existe en el stub de "leaflet" usado por los tests
      // (solo en la instancia real de Leaflet) — de ahí el optional
      // chaining, para no acoplar el test al detalle de cómo se pinta.
      polyline.setStyle?.({ color: "var(--color-primary)" });
      polyline.addTo(map);
      map.fitBounds(polyline.getBounds());

      mapInstance = map;
    }

    void initMap();

    return () => {
      mapInstance?.remove();
    };
  }, [geometry]);

  return (
    <div
      ref={mapRef}
      role="region"
      aria-label={`Mapa del circuito ${label}`}
      tabIndex={0}
      className="h-60 w-full rounded-xl overflow-hidden"
      data-testid="course-map"
      style={{ zIndex: 0 }}
    />
  );
}
