import { TileLayer } from "react-leaflet";

// Esri World Light Gray canvas. No key. ArcGIS order is {z}/{y}/{x}.
// The export names stay so existing imports keep working. This preview
// uses the light sheet so the map matches the paper ground.
export const DARK_BASEMAP_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
export const DARK_LABELS_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
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
