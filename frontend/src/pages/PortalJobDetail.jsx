import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { portalApi, API } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";

const fmt = (iso) => new Date(iso).toLocaleString();

export default function PortalJobDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    portalApi.get(`/portal/jobs/${id}`).then(r => setData(r.data))
      .catch(e => setErr(e.response?.data?.detail || "Not found"));
  }, [id]);

  if (err) return <PortalShell><div className="surface muted" style={{ padding: 24 }}>{err}</div></PortalShell>;
  if (!data) return <PortalShell><div className="muted">Loading…</div></PortalShell>;

  const j = data.job;
  return (
    <PortalShell>
      <Link to="/portal/jobs" className="muted" style={{ fontSize: 14 }}>← Back to jobs</Link>
      <h1 className="h1" style={{ marginTop: 8, marginBottom: 8 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        <span className={`badge badge-${j.status}`}>{j.status.replace(/_/g, " ")}</span>
        <span className={`badge badge-${j.zone}`}>{j.zone}</span>
      </div>

      <div className="surface" style={{ padding: 20, marginBottom: 16 }}>
        <Row k="Customer" v={j.customer_last_name} />
        <Row k="Service" v={j.calibration_label} />
        <Row k="Price" v={`$${j.price.toFixed(2)}`} />
        <Row k="Scheduled" v={fmt(j.scheduled_start)} />
        {j.actual_completion && <Row k="Completed" v={fmt(j.actual_completion)} />}
        {j.result && <Row k="Result" v={j.result.toUpperCase()} />}
        <Row k="Address" v={j.job_address} />
        {j.vehicle_vin && <Row k="VIN" v={j.vehicle_vin} />}
      </div>

      <h3 className="h3" style={{ marginBottom: 8 }}>Documentation</h3>
      {data.documents.length === 0 ? (
        <div className="surface muted" style={{ padding: 16, textAlign: "center" }}>
          {j.status === "complete" ? "Document upload pending." : "Available after completion."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {data.documents.map(d => (
            <a key={d.id} className="surface" style={{ padding: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}
              href={`${API}/portal/jobs/${j.id}/documents/${d.id}/download`}
              target="_blank" rel="noreferrer"
              data-testid={`portal-doc-${d.id}`}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{d.file_name}</div>
                <div className="muted" style={{ fontSize: 12 }}>{(d.size_bytes / 1024).toFixed(1)} KB · {d.content_type}</div>
              </div>
              <span style={{ color: "var(--accent)" }}>Download ↓</span>
            </a>
          ))}
        </div>
      )}
    </PortalShell>
  );
}

const Row = ({ k, v }) => (
  <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
    <span className="muted">{k}</span><span style={{ fontWeight: 500 }}>{v}</span>
  </div>
);
