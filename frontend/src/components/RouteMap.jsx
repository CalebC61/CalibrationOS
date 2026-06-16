import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";

// Default marker icons break in webpack; use divIcon for numbered colored pins.
function makeIcon(num, color) {
  return L.divIcon({
    className: "route-pin",
    html: `<div style="background:${color};color:#fff;border-radius:999px;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #111;box-shadow:0 2px 8px rgba(0,0,0,0.6);font-family:'JetBrains Mono',monospace;">${num}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) { map.setView(points[0], 11); return; }
    const bounds = L.latLngBounds(points);
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [points, map]);
  return null;
}

export default function RouteMap({ jobs, height = 520 }) {
  const valid = jobs.filter(j => j.job_lat && j.job_lng);
  const points = valid.map(j => [j.job_lat, j.job_lng]);
  const center = points[0] || [33.4484, -112.0740];
  const westLine = valid.filter(j => j.zone === "west").map(j => [j.job_lat, j.job_lng]);
  const eastLine = valid.filter(j => j.zone === "east").map(j => [j.job_lat, j.job_lng]);
  return (
    <div style={{ height, borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)" }} data-testid="route-map">
      <MapContainer center={center} zoom={10} style={{ height: "100%", width: "100%", background: "#0d1116" }}>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; OpenStreetMap &copy; CARTO'
        />
        {westLine.length > 1 && <Polyline positions={westLine} pathOptions={{ color: "#F97316", weight: 3, opacity: 0.7 }} />}
        {eastLine.length > 1 && <Polyline positions={eastLine} pathOptions={{ color: "#3B82F6", weight: 3, opacity: 0.7 }} />}
        {valid.map((j, idx) => (
          <Marker key={j.id} position={[j.job_lat, j.job_lng]}
            icon={makeIcon(idx + 1, j.zone === "west" ? "#F97316" : "#3B82F6")}>
            <Tooltip direction="top" offset={[0, -10]}>
              <div style={{ fontSize: 12 }}>
                <b>#{idx + 1} · {j.shop_name}</b><br />
                {new Date(j.scheduled_start).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
              </div>
            </Tooltip>
          </Marker>
        ))}
        <FitBounds points={points} />
      </MapContainer>
    </div>
  );
}
