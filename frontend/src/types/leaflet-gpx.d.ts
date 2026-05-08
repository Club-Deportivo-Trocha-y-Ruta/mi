declare module "leaflet-gpx" {
  import type * as L from "leaflet";

  interface GpxOptions {
    async?: boolean;
    marker_options?: {
      startIconUrl?: string;
      endIconUrl?: string;
      shadowUrl?: string;
    };
  }

  class GpxLayer extends L.FeatureGroup {
    constructor(gpxUrl: string, options?: GpxOptions);
  }

  export { GpxLayer };
}
