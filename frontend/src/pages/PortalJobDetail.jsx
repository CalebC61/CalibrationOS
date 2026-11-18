import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { jobStatusLabel } from "../lib/api";
import { portalApi } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";
import JobEditModal from "../components/JobEditModal";
import WarrantyBadge from "../components/WarrantyBadge";

const fmt = (iso) => new Date(iso).toLocaleString();

export default function PortalJobDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [editing, setEditing] = useState(false);
  const [version, setVersion] = useState(0);
  const [docError, setDocError] = useState("");

  useEffect(() => {
    portalApi.get(`/portal/jobs/${id}`).then(r => setData(r.data))
      .catch(e => setErr(e.response?.data?.detail || "Not found"));
  }, [id, version]);

  async function cancelJob() {
    if (!window.confirm("Cancel this booking? The shop contact gets a cancellation email.")) return;
    try {
      await portalApi.post(`/portal/jobs/${id}/cancel`);
      setVersion(value => value + 1);
    } catch (e) {
      const detail = e.response?.data?.detail;
      alert(typeof detail === "string" ? detail : "Could not cancel this booking. Try again.");
    }
  }

  if (err) return <PortalShell><div className="surface muted" style={{ padding: 24 }}>{err}</div></PortalShell>;
  if (!data) return <PortalShell><div className="muted">Loading…</div></PortalShell>;

  const j = data.job;

  async function downloadReport(doc) {
    setDocError("");
    try {
      const response = await portalApi.get(
        `/portal/jobs/${j.id}/documents/${doc.id}/download`,
        { responseType: "blob" },
      );
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data]);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = doc.file_name || "report";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDocError("That file didn't download. Try again.");
    }
  }

  return (
    <PortalShell>
      <Link to="/portal/jobs" className="muted" style={{ fontSize: 14 }}>← Back to jobs</Link>
      <h1 className="h1" style={{ marginTop: 8, marginBottom: 8 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        <span className={`badge badge-${j.status}`}>{jobStatusLabel(j.status)}</span>
        <WarrantyBadge job={j} />
        {j.status === "requested" && (
          <span className="muted" style={{ fontSize: 13 }}>This time is held until the owner approves it.</span>
        )}
        <span className={`badge badge-${j.zone}`}>{j.zone}</span>
      </div>

      {!["complete", "cancelled", "declined"].includes(j.status) && (
        <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          <button type="button" className="btn btn-ghost" onClick={() => setEditing(true)} data-testid="portal-edit-job">Edit</button>
          <button type="button" className="btn btn-ghost" onClick={cancelJob} data-testid="portal-cancel-job">Cancel booking</button>
        </div>
      )}
      <JobEditModal open={editing} job={j} shopEdit client={portalApi}
        onClose={() => setEditing(false)} onDone={() => setVersion(value => value + 1)} />

      <div className="surface" style={{ padding: 20, marginBottom: 16 }}>
        <Row k="Customer" v={[j.customer_first_name, j.customer_last_name].filter(Boolean).join(" ")} />
        <Row k="Service" v={j.calibration_label} />
        <Row k="Price" v={`$${j.price.toFixed(2)}`} />
        {j.warranty_skip_reason && (
          <div style={{ padding: "8px 0", fontSize: 14 }} data-testid={`warranty-reason-${j.id}`}>{j.warranty_skip_reason}</div>
        )}
        <Row k="Scheduled" v={fmt(j.scheduled_start)} />
        {j.actual_completion && <Row k="Completed" v={fmt(j.actual_completion)} />}
        {j.result && <Row k="Result" v={j.result.toUpperCase()} />}
        <Row k="Address" v={j.job_address} />
        {j.notes && (
          <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
            <div className="muted">Notes</div>
            <div style={{ marginTop: 4, whiteSpace: "pre-wrap" }} data-testid="portal-job-notes">{j.notes}</div>
          </div>
        )}
        {j.vehicle_vin && <Row k="VIN" v={j.vehicle_vin} />}
      </div>

      <h2 className="h3" style={{ marginBottom: 8 }}>Documentation</h2>
      {data.documents.length === 0 ? (
        <div className="surface muted" style={{ padding: 16, textAlign: "center" }}>
          {j.status === "complete" ? "Document upload pending." : "Available after completion."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {docError && (
            <div role="alert" data-testid="portal-doc-error" style={{ color: "var(--red)", fontSize: 14 }}>{docError}</div>
          )}
          {data.documents.map(d => (
            <button key={d.id} type="button" className="surface"
              style={{ padding: 14, display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", textAlign: "left", cursor: "pointer", color: "inherit", font: "inherit" }}
              onClick={() => downloadReport(d)}
              data-testid={`portal-doc-${d.id}`}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{d.file_name}</div>
                <div className="muted" style={{ fontSize: 12 }}>{(d.size_bytes / 1024).toFixed(1)} KB · {d.content_type}</div>
              </div>
              <span style={{ color: "var(--accent-ink)" }}>Download ↓</span>
            </button>
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
