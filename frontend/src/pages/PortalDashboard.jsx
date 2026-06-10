import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapContainer, TileLayer, Marker, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import { portalApi, getPortalAuth } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";

function pinIcon(num, color, ghost = false) {
  const opacity = ghost ? 0.55 : 1;
  return L.divIcon({
    className: "route-pin",
    html: `<div style="background:${color};color:#fff;border-radius:999px;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;border:2px solid #111;opacity:${opacity};font-family:'JetBrains Mono',monospace;">${num}</div>`,
    iconSize: [26, 26], iconAnchor: [13, 13],
  });
}
function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) { map.setView(points[0], 11); return; }
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
  }, [points, map]);
  return null;
}

const fmt = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

export default function PortalDashboard() {
  const auth = getPortalAuth();
  const [data, setData] = useState(null);
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));

  useEffect(() => {
    portalApi.get(`/portal/day-map?date_str=${date}`).then(r => setData(r.data));
  }, [date]);

  if (!data) return <PortalShell><div className="muted">Loading…</div></PortalShell>;

  const own = data.own || [];
  const others = data.others || [];
  const allPoints = [...own, ...others].filter(j => j.job_lat && j.job_lng).map(j => [j.job_lat, j.job_lng]);

  return (
    <PortalShell>
      {!auth?.has_payment_method && (
        <div className="surface" style={{ padding: 14, marginBottom: 16, borderColor: "var(--yellow)" }} data-testid="no-card-banner">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontWeight: 600 }}>⚠ No card on file</div>
              <div className="muted" style={{ fontSize: 13 }}>Add a payment method to continue booking. Required by Terms.</div>
            </div>
            <Link to="/portal/settings" className="btn btn-primary" data-testid="add-card-cta">Add Card</Link>
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 16, gap: 12, flexWrap: "wrap" }}>
        <div>
          <div className="muted" style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase" }}>Day map</div>
          <h1 className="h1" style={{ margin: "4px 0" }}>
            {new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </h1>
        </div>
        <input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} style={{ width: 200 }} data-testid="day-map-date" />
      </div>

      <div className="surface" style={{ padding: 12, marginBottom: 20 }}>
        <div style={{ height: 380, borderRadius: 8, overflow: "hidden" }} data-testid="portal-map">
          <MapContainer center={allPoints[0] || [33.4484, -112.0740]} zoom={10}
            style={{ height: "100%", width: "100%", background: "#0d1116" }}>
            <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; OpenStreetMap &copy; CARTO' />
            {own.map((j, idx) => (
              <Marker key={j.id} position={[j.job_lat, j.job_lng]}
                icon={pinIcon(`Y${idx + 1}`, j.zone === "west" ? "#F97316" : "#3B82F6")}>
                <Tooltip>
                  <div style={{ fontSize: 12 }}>
                    <b>Your job · {fmt(j.scheduled_start)}</b><br />
                    {j.vehicle_year} {j.vehicle_make} {j.vehicle_model}
                  </div>
                </Tooltip>
              </Marker>
            ))}
            {others.map((j) => (
              <Marker key={j.id} position={[j.job_lat, j.job_lng]}
                icon={pinIcon("·", "#666", true)}>
                <Tooltip>
                  <div style={{ fontSize: 12 }}>
                    <b>{fmt(j.scheduled_start)} — {j.zone === "west" ? "West Valley" : "East Valley"}</b><br />
                    ~{j.drive_minutes_from_you} min drive from your shop
                  </div>
                </Tooltip>
              </Marker>
            ))}
            <FitBounds points={allPoints} />
          </MapContainer>
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 12 }} className="muted">
          <span>🟧/🟦 Your jobs</span>
          <span>⚫ Other shops (anonymized) — tap for time + drive estimate</span>
        </div>
      </div>

      <section style={{ marginBottom: 24 }}>
        <h2 className="h3" style={{ marginBottom: 10 }}>Your jobs today ({own.length})</h2>
        {own.length === 0 ? (
          <div className="surface muted" style={{ padding: 20, textAlign: "center" }}>No jobs from your shop today.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {own.map((j, idx) => (
              <Link to={`/portal/jobs/${j.id}`} key={j.id} className="card-job" data-testid={`portal-own-job-${j.id}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                  <div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                      <span className="font-mono" style={{ background: "var(--bg-elevated)", padding: "2px 8px", borderRadius: 6, fontSize: 12, fontWeight: 600 }}>Y{idx + 1}</span>
                      <span className={`badge badge-${j.status}`}>{j.status.replace(/_/g, " ")}</span>
                      {j.is_at_risk && <span className="badge" style={{ background: "rgba(239,68,68,0.15)", color: "var(--red)" }}>⚠ AT RISK</span>}
                    </div>
                    <div className="h3" style={{ marginTop: 4 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
                    <div className="muted" style={{ fontSize: 13 }}>{j.calibration_label} · {j.customer_last_name}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="font-display" style={{ fontWeight: 700 }}>{fmt(j.scheduled_start)}</div>
                    <div className="font-mono" style={{ fontSize: 13, marginTop: 4 }}>${j.price.toFixed(2)}</div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      <Link to="/portal/book" className="btn btn-primary" style={{ width: "100%", padding: 14 }} data-testid="portal-book-cta">+ Book a new calibration</Link>
    </PortalShell>
  );
}
