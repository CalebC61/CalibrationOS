import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapContainer, Marker, Tooltip, useMap } from "react-leaflet";
import DarkBasemap from "../components/DarkBasemap";
import L from "leaflet";
import { phoenixTodayStr, jobStatusLabel } from "../lib/api";
import { portalApi } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";
import WarrantyBadge from "../components/WarrantyBadge";

function pinIcon(num, color, ghost = false, text = "#fff") {
  const opacity = ghost ? 0.55 : 1;
  return L.divIcon({
    className: "route-pin",
    html: `<div style="background:${color};color:${text};border-radius:999px;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;border:2px solid #111;opacity:${opacity};font-family:'JetBrains Mono',monospace;">${num}</div>`,
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
  const [data, setData] = useState(null);
  const [setup, setSetup] = useState(null);
  const [stats, setStats] = useState(null);
  const [date, setDate] = useState(() => phoenixTodayStr());

  useEffect(() => {
    portalApi.get(`/portal/day-map?date_str=${date}`).then(r => setData(r.data));
  }, [date]);
  useEffect(() => {
    portalApi.get("/portal/me").then(r => setSetup(r.data.setup));
  }, []);
  useEffect(() => {
    let cancelled = false;
    portalApi.get("/portal/scorecard").then(r => {
      if (!cancelled) setStats(r.data?.stats || null);
    }).catch(() => {
      if (!cancelled) setStats(null);
    });
    return () => { cancelled = true; };
  }, []);

  if (!data) return <PortalShell><div className="muted">Loading…</div></PortalShell>;

  const own = data.own || [];
  const others = data.others || [];
  const points = [...own, ...others].filter(j => j.job_lat && j.job_lng).map(j => [j.job_lat, j.job_lng]);
  const windowFor = (start, end) => (start && end ? `${fmt(start)}–${fmt(end)}` : (start ? fmt(start) : ""));

  return (
    <PortalShell>
      {setup?.banner && (
        <div className="surface" style={{ padding: 14, marginBottom: 16, borderColor: "var(--yellow)" }} data-testid="no-card-banner">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{setup.suspended ? "Booking is paused" : "Booking is closed"}</div>
              <div className="muted" style={{ fontSize: 13 }}>{setup.message}</div>
            </div>
            <Link to="/portal/settings" className="btn btn-primary" data-testid="add-card-cta">
              {setup.has_card && !setup.charge_failed && !setup.accepted ? "Accept charge terms" : "Update card"}
            </Link>
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 16, gap: 12, flexWrap: "wrap" }}>
        <h1 className="h1" style={{ margin: 0 }}>
          {new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
        </h1>
        <input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} style={{ width: "100%", maxWidth: 220 }} data-testid="day-map-date" />
      </div>

      {stats && (
        <section className="portal-stats" data-testid="portal-scorecard" aria-label="Last 30 days">
          <h2 className="portal-stats-title">Last 30 days</h2>
          <dl className="portal-stats-row">
            <div><dt>Jobs</dt><dd data-testid="stat-jobs">{stats.jobs_last_30_days}</dd></div>
            <div><dt>Completed</dt><dd data-testid="stat-completed">{stats.completed_count}</dd></div>
            <div><dt>Upcoming</dt><dd data-testid="stat-upcoming">{stats.upcoming_count}</dd></div>
            <div><dt>Total spent</dt><dd data-testid="stat-spent">${Number(stats.total_spent_last_30_days || 0).toFixed(0)}</dd></div>
          </dl>
        </section>
      )}

      {points.length === 0 ? (
        <div className="surface" data-testid="portal-day-empty" style={{ padding: "28px 20px", marginBottom: 20, textAlign: "center" }}>
          <h2 className="h3" style={{ marginBottom: 8 }}>No stops on this day</h2>
          <p className="muted" style={{ margin: "0 auto", maxWidth: "36rem", lineHeight: 1.5 }}>
            When a calibration is on the route, it shows up here. Your jobs include the details. Other stops show the time only.
          </p>
        </div>
      ) : (
        <div className="surface" style={{ padding: 12, marginBottom: 20 }}>
          <div style={{ height: 380, borderRadius: 8, overflow: "hidden" }} data-testid="portal-map">
            <MapContainer center={points[0]} zoom={10}
              style={{ height: "100%", width: "100%", background: "#0d1116" }}>
              <DarkBasemap />
              {own.filter(j => j.job_lat && j.job_lng).map((j) => (
                <Marker key={j.id} position={[j.job_lat, j.job_lng]}
                  icon={pinIcon(j.route_order || "Y", "#1FE0C4", false, "#07110F")}>
                  <Tooltip>
                    <div style={{ fontSize: 12 }}>
                      <b>Your job · {windowFor(j.scheduled_start, j.scheduled_end)}</b><br />
                      {j.vehicle_year} {j.vehicle_make} {j.vehicle_model}<br />
                      {j.job_address}
                    </div>
                  </Tooltip>
                </Marker>
              ))}
              {others.filter(j => j.job_lat && j.job_lng).map((j) => (
                <Marker key={`stop-${j.route_order}`} position={[j.job_lat, j.job_lng]}
                  icon={pinIcon(j.route_order || "·", "#8E95A3", false, "#0a0a0a")}>
                  <Tooltip>
                    <div style={{ fontSize: 12 }} data-testid={`portal-other-stop-${j.route_order}`}>
                      <b>Stop {j.route_order}</b><br />
                      {windowFor(j.arrival_start, j.arrival_end)}
                    </div>
                  </Tooltip>
                </Marker>
              ))}
              <FitBounds points={points} />
            </MapContainer>
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 12, flexWrap: "wrap" }} className="muted" data-testid="portal-map-legend">
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 1, background: "#1FE0C4", display: "inline-block" }} />
              Your jobs
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 999, background: "#8E95A3", display: "inline-block" }} />
              Other stops on the route — time window only
            </span>
          </div>
        </div>
      )}

      <section style={{ marginBottom: 24 }}>
        <h2 className="h3" style={{ marginBottom: 10 }}>Your jobs ({own.length})</h2>
        {own.length === 0 ? (
          <div className="surface muted" style={{ padding: 20, textAlign: "center" }}>No jobs from your shop on this day.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {own.map((j, idx) => (
              <Link to={`/portal/jobs/${j.id}`} key={j.id} className="card-job" data-testid={`portal-own-job-${j.id}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                  <div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                      <span className="font-mono" style={{ background: "var(--bg-elevated)", padding: "2px 8px", borderRadius: 6, fontSize: 12, fontWeight: 600 }}>{j.route_order || idx + 1}</span>
                      <span className={`badge badge-${j.status}`}>{jobStatusLabel(j.status)}</span>
                      {j.is_at_risk && <span className="badge" style={{ background: "rgba(239,68,68,0.15)", color: "var(--red)" }}>⚠ AT RISK</span>}
                    </div>
                    <div className="h3" style={{ marginTop: 4 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
                    <div className="muted" style={{ fontSize: 13 }}>{j.calibration_label} · {j.customer_last_name}</div>
                    <WarrantyBadge job={j} />
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
