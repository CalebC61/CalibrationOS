import { TileLayer } from "react-leaflet";

// CARTO's public raster URL
// (https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png)
// returns one "API KEY REQUIRED" watermark for every z/x/y. Esri's World Dark
// Gray canvas serves a real dark map with no key. ArcGIS order is {z}/{y}/{x}.
export const DARK_BASEMAP_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}";
export const DARK_LABELS_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
export const DARK_BASEMAP_ATTRIBUTION =
  "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community";

export default function DarkBasemap() {
  return (
    <>
      <TileLayer url={DARK_BASEMAP_URL} attribution={DARK_BASEMAP_ATTRIBUTION} />
      <TileLayer url={DARK_LABELS_URL} />
    </>
  );
}
