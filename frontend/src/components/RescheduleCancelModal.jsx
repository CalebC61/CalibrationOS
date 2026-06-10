import { useEffect, useState } from "react";
import { api, formatTime, todayStr } from "../lib/api";

const QUICK_REASONS = [
  "Customer requested",
  "Weather",
  "Vehicle not ready",
  "Equipment issue",
  "Schedule conflict",
];

export default function RescheduleCancelModal({ open, job, mode, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [date, setDate] = useState(todayStr());
  const [slots, setSlots] = useState([]);
  const [chosen, setChosen] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || mode !== "reschedule" || !job) return;
    // Find the shop to use its booking token (we need it for availability)
    let cancelled = false;
    (async () => {
      const shop = (await api.get(`/shops/${job.shop_id}`)).data;
      const { data } = await api.post("/public/availability", {
        booking_token: shop.booking_link_token,
        job_address: job.job_address,
        date,
      });
      if (!cancelled) setSlots(data.slots || []);
    })().catch(() => {});
    return () => { cancelled = true; };
  }, [open, mode, job, date]);

  if (!open || !job) return null;

  async function submit() {
    setBusy(true); setError("");
    try {
      if (mode === "reschedule") {
        if (!chosen) { setError("Pick a new time"); setBusy(false); return; }
        await api.post(`/jobs/${job.id}/reschedule`, { scheduled_start: chosen.start, reason: reason || null });
      } else {
        await api.post(`/jobs/${job.id}/cancel`, { reason: reason || null });
      }
      onDone?.();
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  }

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 50,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }} data-testid="reschedule-cancel-modal">
      <div onClick={e => e.stopPropagation()} className="surface page-fade" style={{ padding: 24, maxWidth: 520, width: "100%" }}>
        <h2 className="h2" style={{ marginBottom: 4 }}>
          {mode === "reschedule" ? "Reschedule Job" : "Cancel Job"}
        </h2>
        <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
          {mode === "reschedule"
            ? "The customer will receive an SMS with the new time."
            : "The customer will receive a cancellation SMS."}
        </div>
        <div className="elevated" style={{ padding: 12, marginBottom: 16, fontSize: 14 }}>
          <div style={{ fontWeight: 600 }}>{job.shop_name}</div>
          <div className="muted">{job.vehicle_year} {job.vehicle_make} {job.vehicle_model}</div>
          <div className="muted">Currently: {formatTime(job.scheduled_start)}</div>
        </div>

        {mode === "reschedule" && (
          <>
            <div className="label">New date</div>
            <input className="input" type="date" value={date} onChange={e => { setDate(e.target.value); setChosen(null); }}
              min={todayStr()} style={{ marginBottom: 12 }} data-testid="reschedule-date" />
            <div className="label">New time</div>
            {slots.length === 0 ? (
              <div className="muted" style={{ fontSize: 13, padding: 12, background: "var(--bg-elevated)", borderRadius: 8, marginBottom: 12 }}>
                No slots available on this date. Try another.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 8, marginBottom: 12 }}>
                {slots.slice(0, 12).map(s => (
                  <button key={s.start} type="button"
                    className={"btn " + (chosen?.start === s.start ? "btn-primary" : "btn-ghost")}
                    onClick={() => setChosen(s)} data-testid={`reschedule-slot-${s.start}`}>
                    {formatTime(s.start)}
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        <div className="label">Reason {mode === "reschedule" ? "(optional)" : ""}</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
          {QUICK_REASONS.map(r => (
            <button key={r} type="button" className={"btn " + (reason === r ? "btn-primary" : "btn-ghost")}
              style={{ padding: "4px 10px", fontSize: 12 }}
              onClick={() => setReason(r === reason ? "" : r)} data-testid={`reason-${r}`}>
              {r}
            </button>
          ))}
        </div>
        <input className="input" value={reason} onChange={e => setReason(e.target.value)}
          placeholder="Or type a custom reason…" data-testid="reason-text" />

        {error && <div style={{ color: "var(--red)", fontSize: 13, marginTop: 10 }} data-testid="modal-error">{error}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>Back</button>
          <button className={"btn " + (mode === "reschedule" ? "btn-primary" : "btn-danger")}
            onClick={submit} disabled={busy} data-testid="modal-confirm">
            {busy ? "Submitting…" : (mode === "reschedule" ? "Confirm Reschedule" : "Confirm Cancellation")}
          </button>
        </div>
      </div>
    </div>
  );
}
