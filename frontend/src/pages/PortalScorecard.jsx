import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { formatTime, formatDate } from "../lib/api";
import { portalApi } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";
import WarrantyBadge from "../components/WarrantyBadge";

export default function PortalScorecard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    portalApi.get("/portal/scorecard").then(r => setData(r.data))
      .catch(e => setError(e.response?.data?.detail || "Couldn't load the scorecard."));
  }, []);

  if (error) return <PortalShell><div className="surface muted" style={{ padding: 24 }}>{error}</div></PortalShell>;
  if (!data) return <PortalShell><div className="muted">Loading…</div></PortalShell>;

  const { stats } = data;
  return (
    <PortalShell>
      <h1 className="h1" style={{ marginBottom: 6 }}>{data.shop_name}</h1>
      <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>{data.shop_address}</div>
      {data.zone && (
        <div style={{ marginBottom: 20 }}>
          <span className={`badge badge-${data.zone}`}>{data.zone === "west" ? "West Valley" : "East Valley"}</span>
        </div>
      )}

      <h2 className="h2" style={{ marginBottom: 12 }}>Last 30 days</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 24 }} data-testid="portal-scorecard">
        <Stat label="Jobs" value={stats.jobs_last_30_days} />
        <Stat label="Completed" value={stats.completed_count} />
        <Stat label="Upcoming" value={stats.upcoming_count} />
        <Stat label="Total spent" value={`$${Number(stats.total_spent_last_30_days || 0).toFixed(0)}`} />
      </div>

      <Link to="/portal/book" className="btn btn-primary" style={{ width: "100%", padding: 14, marginBottom: 24 }}
        data-testid="cta-book">Book a calibration</Link>

      {data.upcoming.length > 0 && (
        <Section title="Upcoming">
          {data.upcoming.map(j => (
            <div key={j.id} className="surface" style={{ padding: 12, marginBottom: 8 }} data-testid={`upcoming-${j.id}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
                  <div className="muted" style={{ fontSize: 13 }}>{j.calibration_label}</div>
                  <WarrantyBadge job={j} />
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="font-display" style={{ fontWeight: 700 }}>{formatTime(j.scheduled_start)}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{formatDate(j.scheduled_start)}</div>
                </div>
              </div>
            </div>
          ))}
        </Section>
      )}

      {data.completed.length > 0 && (
        <Section title="Recent completions">
          {data.completed.slice(0, 10).map(j => (
            <div key={j.id} className="surface" style={{ padding: 12, marginBottom: 8 }} data-testid={`completed-${j.id}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
                  <div className="muted" style={{ fontSize: 13 }}>{j.calibration_label}</div>
                  <WarrantyBadge job={j} />
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="font-mono" style={{ fontWeight: 600 }}>${Number(j.price || 0).toFixed(2)}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{j.actual_completion ? formatDate(j.actual_completion) : formatDate(j.scheduled_start)}</div>
                </div>
              </div>
            </div>
          ))}
        </Section>
      )}

      {data.upcoming.length === 0 && data.completed.length === 0 && (
        <div className="surface muted" style={{ padding: 32, textAlign: "center" }}>
          No bookings in the last 30 days.
        </div>
      )}
    </PortalShell>
  );
}

const Stat = ({ label, value }) => (
  <div className="surface" style={{ padding: 14 }}>
    <div className="muted" style={{ fontSize: 13 }}>{label}</div>
    <div className="font-display" style={{ fontSize: 26, fontWeight: 700, marginTop: 2 }}>{value}</div>
  </div>
);
const Section = ({ title, children }) => (
  <section style={{ marginBottom: 24 }}>
    <h3 className="h3" style={{ marginBottom: 10 }}>{title}</h3>
    {children}
  </section>
);
