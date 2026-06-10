import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatTime, todayStr, dateStr } from "../lib/api";
import Shell from "../components/Shell";

const STATUS_FLOW = {
  booked: { next: "driving", label: "Start Driving" },
  driving: { next: "on_site", label: "I've Arrived" },
  on_site: { next: "complete", label: "Complete Job" },
};

export default function Dashboard() {
  const [date, setDate] = useState(todayStr());
  const [jobs, setJobs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState({ count: 0, alerts: [] });
  const [alertsOpen, setAlertsOpen] = useState(false);

  async function load() {
    try {
      const [j, s, a] = await Promise.all([
        api.get(`/jobs?date_str=${date}`),
        api.get(`/dashboard/summary?date_str=${date}`),
        api.get(`/notifications/new-bookings`),
      ]);
      setJobs(j.data); setSummary(s.data); setAlerts(a.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [date]);

  async function markSeen() {
    await api.post("/notifications/mark-seen");
    setAlerts({ count: 0, alerts: [] });
    setAlertsOpen(false);
  }

  const newJobIds = new Set(alerts.alerts.map(a => a.job_id));

  const west = jobs.filter(j => j.zone === "west").sort((a,b) => a.scheduled_start.localeCompare(b.scheduled_start));
  const east = jobs.filter(j => j.zone === "east").sort((a,b) => a.scheduled_start.localeCompare(b.scheduled_start));

  function shiftDate(days) {
    const d = new Date(date + "T00:00:00");
    d.setDate(d.getDate() + days);
    setDate(dateStr(d));
  }

  async function setStatus(jobId, status) {
    if (status === "complete") {
      const ok = window.confirm("Complete this job? This will generate a draft Xero invoice (mocked).");
      if (!ok) return;
      await api.post(`/jobs/${jobId}/complete`, { result: "pass", notes: null });
    } else {
      await api.post(`/jobs/${jobId}/status`, { status });
    }
    load();
  }

  return (
    <Shell>
      {/* New booking alert pill */}
      {alerts.count > 0 && (
        <div className="new-booking-pill page-fade" style={{ marginBottom: 16, position: "relative" }}
          data-testid="new-bookings-banner">
          <button
            onClick={() => setAlertsOpen(o => !o)}
            data-testid="new-bookings-pill"
            style={{
              display: "inline-flex", alignItems: "center", gap: 10,
              background: "var(--accent-dim)", color: "var(--accent)",
              border: "1px solid var(--border-active)", borderRadius: 999,
              padding: "8px 16px", fontWeight: 600, fontSize: 14, cursor: "pointer",
            }}>
            <span className="pulse-dot" style={{
              width: 8, height: 8, borderRadius: 999, background: "var(--accent)",
              boxShadow: "0 0 0 0 var(--accent)",
            }} />
            <span data-testid="new-bookings-count">{alerts.count}</span> new booking{alerts.count === 1 ? "" : "s"} since you last looked
            <span style={{ opacity: 0.7, fontSize: 12 }}>{alertsOpen ? "▲" : "▼"}</span>
          </button>

          {alertsOpen && (
            <div className="surface page-fade" style={{
              position: "absolute", top: "calc(100% + 8px)", left: 0, zIndex: 30,
              minWidth: 360, maxWidth: 480, padding: 12, boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
            }} data-testid="new-bookings-panel">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div className="h3">New bookings</div>
                <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                  onClick={markSeen} data-testid="mark-bookings-seen">Mark all seen</button>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 320, overflowY: "auto" }}>
                {alerts.alerts.map(a => (
                  <div key={a.id} className="elevated" style={{ padding: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>{a.shop_name}</div>
                        <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{a.vehicle}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <span className={`badge badge-${a.zone}`}>{a.zone}</span>
                        <div className="font-mono" style={{ fontSize: 12, marginTop: 4 }}>{formatTime(a.scheduled_start)}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Date strip + summary */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, flexWrap: "wrap", gap: 16 }}>
        <div>
          <div className="muted" style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase" }}>Dispatch board</div>
          <h1 className="h1" style={{ margin: "4px 0" }}>
            {new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </h1>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <button className="btn btn-ghost" onClick={() => shiftDate(-1)} data-testid="prev-day">← Prev</button>
            <button className="btn btn-ghost" onClick={() => setDate(todayStr())} data-testid="today-btn">Today</button>
            <button className="btn btn-ghost" onClick={() => shiftDate(1)} data-testid="next-day">Next →</button>
          </div>
        </div>
        {summary && (
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            <Metric label="Jobs" value={summary.job_count} />
            <Metric label="Revenue" value={`$${summary.revenue.toFixed(0)}`} />
            <Metric label="Est. Miles" value={summary.estimated_miles} />
            <Metric label="Done By" value={summary.done_by ? formatTime(summary.done_by) : "—"} />
          </div>
        )}
      </div>

      {/* Split panel: West / East */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 16 }}>
        <ZonePanel title="West Valley" subtitle="8:00 AM – 2:00 PM" zone="west" jobs={west}
          onStatus={setStatus} headerClass="zone-header-west" newJobIds={newJobIds} />
        <ZonePanel title="East Valley" subtitle="2:30 PM – 7:00 PM" zone="east" jobs={east}
          onStatus={setStatus} headerClass="zone-header-east" newJobIds={newJobIds} />
      </div>

      {loading && jobs.length === 0 && <div className="muted" style={{ marginTop: 24 }}>Loading…</div>}
    </Shell>
  );
}

function Metric({ label, value }) {
  return (
    <div className="surface" style={{ padding: "10px 16px", minWidth: 100 }}>
      <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</div>
      <div className="font-display" style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function ZonePanel({ title, subtitle, zone, jobs, onStatus, headerClass, newJobIds }) {
  return (
    <section data-testid={`zone-panel-${zone}`}>
      <div className={`zone-header ${headerClass}`}>
        <span>{title}</span>
        <span style={{ fontSize: 12, opacity: 0.8 }}>{subtitle} · {jobs.length} jobs</span>
      </div>
      {jobs.length === 0 && (
        <div className="surface muted" style={{ padding: 20, textAlign: "center" }}>
          No jobs in this zone yet.
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {jobs.map((j, idx) => <JobCard key={j.id} job={j} index={idx + 1} onStatus={onStatus} isNew={newJobIds?.has(j.id)} />)}
      </div>
    </section>
  );
}

function JobCard({ job, index, onStatus, isNew }) {
  const flow = STATUS_FLOW[job.status];
  return (
    <div className={"card-job" + (isNew ? " card-job-new" : "")} data-testid={`job-card-${job.id}`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span className="font-mono" style={{
              background: "var(--bg-elevated)", padding: "2px 8px", borderRadius: 6,
              fontSize: 12, fontWeight: 600,
            }}>#{index}</span>
            <span className={`badge badge-${job.status}`}>{job.status.replace(/_/g, " ")}</span>
            {isNew && <span className="badge" style={{ background: "var(--accent-dim)", color: "var(--accent)", border: "1px solid var(--border-active)" }} data-testid="badge-new">NEW</span>}
            {job.invoice_status === "draft" && <span className="badge badge-draft">Invoice: Draft</span>}
          </div>
          <div className="h3" style={{ marginTop: 4 }}>{job.shop_name}</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            {job.vehicle_year} {job.vehicle_make} {job.vehicle_model} · {job.calibration_label}
          </div>
          <a href={`https://maps.google.com/?q=${encodeURIComponent(job.job_address)}`} target="_blank" rel="noreferrer"
            style={{ display: "inline-block", marginTop: 6, fontSize: 13, color: "var(--accent)" }}>
            {job.job_address} →
          </a>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="font-display" style={{ fontSize: 18, fontWeight: 700 }}>{formatTime(job.scheduled_start)}</div>
          <div className="muted" style={{ fontSize: 12 }}>{job.drive_time_minutes} min drive</div>
          <div className="font-mono" style={{ fontSize: 13, marginTop: 4 }}>${job.price.toFixed(2)}</div>
        </div>
      </div>
      {flow && (
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="btn btn-primary" onClick={() => onStatus(job.id, flow.next)}
            data-testid={`job-action-${job.id}`}>{flow.label}</button>
          {job.status === "booked" && (
            <button className="btn btn-ghost" onClick={() => onStatus(job.id, "cancelled")}
              data-testid={`job-cancel-${job.id}`}>Cancel</button>
          )}
        </div>
      )}
    </div>
  );
}
