import { useEffect, useRef } from "react";
import { formatTime } from "../lib/api";
import { MapContainer, Marker, Polyline, Tooltip, useMap } from "react-leaflet";
import DarkBasemap from "./DarkBasemap";
import L from "leaflet";

// Default marker icons break in webpack; use divIcon for numbered colored pins.
function makeIcon(num, color, text = "#0a0a0a") {
  return L.divIcon({
    className: "route-pin",
    html: `<div style="background:${color};color:${text};border-radius:999px;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #111;box-shadow:0 2px 8px rgba(0,0,0,0.6);font-family:'JetBrains Mono',monospace;">${num}</div>`,
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

function pinText(color) {
  return color.toLowerCase() === "#ff5f1f" ? "#0a0a0a" : "#fff";
}

export default function RouteMap({ jobs }) {
  const valid = jobs.filter(j => j.job_lat && j.job_lng);
  const points = valid.map(j => [j.job_lat, j.job_lng]);
  const center = points[0] || [33.4484, -112.0740];
  const byTech = new Map();
  valid.forEach((job) => {
    const key = job.technician_id || "route";
    if (!byTech.has(key)) byTech.set(key, { color: job.technician_color || "#FF5F1F", points: [] });
    byTech.get(key).points.push([job.job_lat, job.job_lng]);
  });
  return (
    <div style={{ height: 380, borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)" }} data-testid="route-map">
      <MapContainer center={center} zoom={10} style={{ height: "100%", width: "100%", background: "#0d1116" }}>
        <DarkBasemap />
        {[...byTech.entries()].map(([techId, route]) => (
          route.points.length > 1 && <Polyline key={techId} positions={route.points} pathOptions={{ color: route.color, weight: 3, opacity: 0.7 }} />
        ))}
        {valid.map((j, idx) => {
          const color = j.technician_color || "#FF5F1F";
          return (
          <Marker key={j.id} position={[j.job_lat, j.job_lng]}
            icon={makeIcon(idx + 1, color, pinText(color))}>
            <Tooltip direction="top" offset={[0, -10]}>
              <div style={{ fontSize: 12 }}>
                <b>#{idx + 1} · {j.shop_name}</b><br />
                {formatTime(j.scheduled_start)}
                {j.technician_name ? <> · {j.technician_name}</> : null}
              </div>
            </Tooltip>
          </Marker>
          );
        })}
        <FitBounds points={points} />
      </MapContainer>
    </div>
  );
}
