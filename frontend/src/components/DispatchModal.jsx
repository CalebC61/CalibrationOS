import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, formatTime } from "../lib/api";

export default function DispatchModal({ open, job, onClose, onDone }) {
  const [contractors, setContractors] = useState([]);
  const [selected, setSelected] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/contractors").then(r => {
      const active = r.data.filter(c => c.is_active);
      setContractors(active);
      if (active[0]) setSelected(active[0].id);
    });
  }, [open]);

  if (!open || !job) return null;

  async function submit() {
    if (!selected) return;
    setSubmitting(true);
    try {
      await api.post(`/jobs/${job.id}/dispatch`, { contractor_id: selected });
      onDone?.();
      onClose();
    } catch (e) {
      alert(e.response?.data?.detail || "Dispatch failed");
    } finally { setSubmitting(false); }
  }

  return createPortal(
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: 16,
    }} data-testid="dispatch-modal">
      <div onClick={e => e.stopPropagation()} className="surface page-fade" style={{ padding: 24, maxWidth: 480, width: "100%" }}>
        <h2 className="h2" style={{ marginBottom: 4 }}>Dispatch to Contractor</h2>
        <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
          A 30-minute offer SMS will be sent. If declined or unanswered, the job returns to your board.
        </div>
        <div className="elevated" style={{ padding: 12, marginBottom: 16, fontSize: 14 }}>
          <div style={{ fontWeight: 600 }}>{job.shop_name}</div>
          <div className="muted">{job.vehicle_year} {job.vehicle_make} {job.vehicle_model} · {job.calibration_label}</div>
          <div className="muted">{formatTime(job.scheduled_start)} · {job.job_address}</div>
          <div className="font-mono" style={{ marginTop: 4 }}>${job.price.toFixed(2)}</div>
        </div>
        <div className="label">Send to</div>
        <select className="input" value={selected} onChange={e => setSelected(e.target.value)} data-testid="dispatch-select">
          {contractors.length === 0 && <option value="">No active contractors</option>}
          {contractors.map(c => (
            <option key={c.id} value={c.id}>{c.name} · {c.phone}</option>
          ))}
        </select>
        <div style={{ display: "flex", gap: 8, marginTop: 18, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={submit}
            disabled={!selected || submitting} data-testid="dispatch-confirm">
            {submitting ? "Dispatching…" : "Send Offer"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
