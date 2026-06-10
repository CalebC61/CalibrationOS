import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, formatTime, formatDate } from "../lib/api";
import Brand from "../components/Brand";

export default function PublicShopStatus() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/public/shop-status/${token}`).then(r => setData(r.data))
      .catch(e => setError(e.response?.data?.detail || "Not found"));
  }, [token]);

  if (error) return <Center>{error}</Center>;
  if (!data) return <Center>Loading…</Center>;

  const { stats } = data;
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", padding: "32px 16px" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 4 }}>
          <Brand size={26} />
        </div>
        <div className="muted" style={{ textAlign: "center", fontSize: 12, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: 24 }}>Shop Scorecard</div>

        <div className="surface" style={{ padding: 20, marginBottom: 20 }}>
          <div className="h2" style={{ marginBottom: 6 }}>{data.shop_name}</div>
          <div className="muted" style={{ fontSize: 13 }}>{data.shop_address}</div>
          <div style={{ marginTop: 8 }}>
            <span className={`badge badge-${data.zone}`}>{data.zone === "west" ? "West Valley" : "East Valley"}</span>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 24 }}>
          <Stat label="Jobs (30 days)" value={stats.jobs_last_30_days} />
          <Stat label="Completed" value={stats.completed_count} />
          <Stat label="Upcoming" value={stats.upcoming_count} />
          <Stat label="Total spent" value={`$${stats.total_spent_last_30_days.toFixed(0)}`} />
        </div>

        <Link to={`/book/${token}`} className="btn btn-primary" style={{ width: "100%", padding: 14, marginBottom: 24 }}
          data-testid="cta-book">+ Book a new calibration</Link>

        {data.upcoming.length > 0 && (
          <Section title="Upcoming">
            {data.upcoming.map(j => (
              <div key={j.id} className="surface" style={{ padding: 12, marginBottom: 8 }} data-testid={`upcoming-${j.id}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
                    <div className="muted" style={{ fontSize: 13 }}>{j.calibration_label}</div>
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
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
                    <div className="muted" style={{ fontSize: 13 }}>{j.calibration_label}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="font-mono" style={{ fontWeight: 600 }}>${j.price.toFixed(2)}</div>
                    <div className="muted" style={{ fontSize: 12 }}>{j.actual_completion ? formatDate(j.actual_completion) : formatDate(j.scheduled_start)}</div>
                  </div>
                </div>
              </div>
            ))}
          </Section>
        )}

        {data.upcoming.length === 0 && data.completed.length === 0 && (
          <div className="surface muted" style={{ padding: 32, textAlign: "center" }}>
            No bookings yet. Click above to book your first calibration.
          </div>
        )}
      </div>
    </div>
  );
}

const Center = ({ children }) => (
  <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
    <div className="muted">{children}</div>
  </div>
);
const Stat = ({ label, value }) => (
  <div className="surface" style={{ padding: 14, textAlign: "center" }}>
    <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</div>
    <div className="font-display" style={{ fontSize: 26, fontWeight: 700, marginTop: 2 }}>{value}</div>
  </div>
);
const Section = ({ title, children }) => (
  <section style={{ marginBottom: 24 }}>
    <div className="h3" style={{ marginBottom: 10 }}>{title}</div>
    {children}
  </section>
);
