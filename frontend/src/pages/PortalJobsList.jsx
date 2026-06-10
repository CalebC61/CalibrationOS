import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { portalApi } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";

const fmtTime = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

export default function PortalJobsList() {
  const [jobs, setJobs] = useState([]);
  const [filter, setFilter] = useState("all");
  useEffect(() => { portalApi.get("/portal/jobs").then(r => setJobs(r.data)); }, []);

  const filtered = filter === "all" ? jobs :
    filter === "upcoming" ? jobs.filter(j => ["booked", "driving", "on_site", "dispatched_to_contractor"].includes(j.status)) :
    filter === "completed" ? jobs.filter(j => j.status === "complete") :
    jobs.filter(j => j.status === "cancelled");

  return (
    <PortalShell>
      <h1 className="h1" style={{ marginBottom: 16 }}>My Jobs</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {[
          { k: "all", label: "All" },
          { k: "upcoming", label: "Upcoming" },
          { k: "completed", label: "Completed" },
          { k: "cancelled", label: "Cancelled" },
        ].map(f => (
          <button key={f.k} className={"btn " + (filter === f.k ? "btn-primary" : "btn-ghost")}
            onClick={() => setFilter(f.k)} data-testid={`filter-${f.k}`}>{f.label}</button>
        ))}
      </div>
      {filtered.length === 0 && <div className="muted">No jobs to show.</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {filtered.map(j => (
          <Link to={`/portal/jobs/${j.id}`} key={j.id} className="card-job" data-testid={`pj-${j.id}`}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                  <span className={`badge badge-${j.status}`}>{j.status.replace(/_/g, " ")}</span>
                </div>
                <div className="h3">{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
                <div className="muted" style={{ fontSize: 13 }}>{j.calibration_label} · {j.customer_last_name}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div className="font-display" style={{ fontWeight: 700 }}>{fmtTime(j.scheduled_start)}</div>
                <div className="muted" style={{ fontSize: 12 }}>{fmtDate(j.scheduled_start)}</div>
                <div className="font-mono" style={{ fontSize: 13, marginTop: 4 }}>${j.price.toFixed(2)}</div>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </PortalShell>
  );
}
