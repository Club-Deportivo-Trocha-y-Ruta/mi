import { useEffect, useRef } from "react";
import { Download } from "lucide-react";

interface RouteViewerProps {
  routeFilePath: string;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function RouteViewer({ routeFilePath }: RouteViewerProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const isGpx = routeFilePath.toLowerCase().endsWith(".gpx");

  const absoluteUrl = routeFilePath.startsWith("http")
    ? routeFilePath
    : `${API_BASE}/${routeFilePath.replace(/^\//, "")}`;

  useEffect(() => {
    if (!isGpx || !mapRef.current) return;

    let mapInstance: import("leaflet").Map | null = null;

    async function initMap() {
      const L = (await import("leaflet")).default;
      await import("leaflet/dist/leaflet.css");
      const { GpxLayer } = await import("leaflet-gpx");

      if (!mapRef.current) return;

      // Fix leaflet default icon paths broken by bundlers
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      mapInstance = L.map(mapRef.current).setView([0, 0], 2);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors",
      }).addTo(mapInstance);

      new GpxLayer(absoluteUrl, {
        async: true,
        marker_options: { startIconUrl: "", endIconUrl: "", shadowUrl: "" },
      })
        .on("loaded", (e: { target: { getBounds: () => import("leaflet").LatLngBounds } }) => {
          mapInstance?.fitBounds(e.target.getBounds());
        })
        .addTo(mapInstance);
    }

    void initMap();

    return () => {
      mapInstance?.remove();
    };
  }, [absoluteUrl, isGpx]);

  if (!isGpx) {
    const isFit = routeFilePath.toLowerCase().endsWith(".fit");
    return (
      <div className="rounded-xl bg-light-gray px-4 py-6 text-center">
        <p className="text-sm text-mid-gray">
          {isFit
            ? "Vista previa no disponible aún para archivos .fit."
            : "Formato de archivo no soportado para vista previa."}
        </p>
        <a
          href={absoluteUrl}
          download
          className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
        >
          <Download size={14} aria-hidden="true" />
          Descargar archivo
        </a>
      </div>
    );
  }

  return (
    <div
      ref={mapRef}
      className="h-64 w-full rounded-xl overflow-hidden"
      role="img"
      aria-label="Mapa del recorrido GPX"
      data-testid="route-viewer-map"
      style={{ zIndex: 0 }}
    />
  );
}
