import { useEffect, useState } from "react";
import { api, formatTime, formatDate } from "../lib/api";

export default function TomorrowStrip({ baseDate }) {
  const [jobs, setJobs] = useState([]);
  useEffect(() => {
    const d = new Date(baseDate + "T00:00:00");
    d.setDate(d.getDate() + 1);
    const tomorrow = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
    api.get(`/jobs?date_str=${tomorrow}`).then(r => setJobs(r.data));
  }, [baseDate]);

  if (jobs.length === 0) return null;
  const west = jobs.filter(j => j.zone === "west").length;
  const east = jobs.filter(j => j.zone === "east").length;
  const revenue = jobs.filter(j => j.status !== "cancelled").reduce((a, b) => a + b.price, 0);

  return (
    <section style={{ marginTop: 24 }} data-testid="tomorrow-strip">
      <div className="h3" style={{ marginBottom: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Tomorrow Preview</span>
        <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
          {west} West · {east} East · ${revenue.toFixed(0)}
        </span>
      </div>
      <div className="surface" style={{ padding: 12 }}>
        <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
          {jobs.map((j, idx) => (
            <div key={j.id} className="elevated" style={{ minWidth: 220, padding: 10, flexShrink: 0 }}
              data-testid={`tomorrow-job-${j.id}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className={`badge badge-${j.zone}`}>{j.zone}</span>
                <span className="font-display" style={{ fontWeight: 700 }}>{formatTime(j.scheduled_start)}</span>
              </div>
              <div style={{ fontWeight: 600, marginTop: 6, fontSize: 14 }}>{j.shop_name}</div>
              <div className="muted" style={{ fontSize: 12 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
