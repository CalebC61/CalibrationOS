import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

const fmt = (iso) => iso ? new Date(iso).toLocaleString() : "—";

export default function ChargeQueue() {
  const [queue, setQueue] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [errors, setErrors] = useState({}); // {jobId: "msg"}
  const [flash, setFlash] = useState(null); // {jobId, kind, msg}

  const load = useCallback(async () => {
    try {
      const r = await api.get("/charge-queue");
      setQueue(r.data);
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const totalPending = queue.reduce((sum, j) => sum + j.price, 0);

  async function chargeJob(jobId) {
    setBusyId(jobId);
    setErrors(e => ({ ...e, [jobId]: null }));
    try {
      const { data } = await api.post(`/jobs/${jobId}/charge`);
      setFlash({ jobId, kind: "success",
        msg: `Charged $${(data.amount_cents / 100).toFixed(2)} · PI ${data.payment_intent_id.slice(-8)}` });
      setQueue(q => q.filter(j => j.id !== jobId));
      setTimeout(() => setFlash(null), 4500);
    } catch (e) {
      setErrors(err => ({ ...err, [jobId]: e.response?.data?.detail || "Charge failed" }));
    } finally {
      setBusyId(null);
    }
  }

  async function skipJob(jobId) {
    if (!window.confirm("Remove this job from the charge queue? You'll need to bill the shop manually.")) return;
    setBusyId(jobId);
    setErrors(e => ({ ...e, [jobId]: null }));
    try {
      await api.post(`/jobs/${jobId}/skip-charge`);
      setQueue(q => q.filter(j => j.id !== jobId));
    } catch (e) {
      setErrors(err => ({ ...err, [jobId]: e.response?.data?.detail || "Failed" }));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 8 }}>Charge Queue</h1>
      <div className="muted" style={{ marginBottom: 16, fontSize: 14 }}>
        Completed portal-shop jobs awaiting card charge. Click <b>Charge Now</b> to bill the card on file (Stripe test mode).
      </div>

      <div className="surface" style={{ padding: "12px 18px", marginBottom: 16, display: "inline-flex", gap: 24 }}>
        <Metric label="Jobs" value={queue.length} />
        <Metric label="Pending total" value={`$${totalPending.toFixed(2)}`} />
      </div>

      {flash && (
        <div data-testid="charge-flash" style={{
          padding: "10px 14px", marginBottom: 14, borderRadius: 8,
          background: flash.kind === "success" ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
          border: `1px solid ${flash.kind === "success" ? "rgba(16,185,129,0.4)" : "rgba(239,68,68,0.4)"}`,
          color: flash.kind === "success" ? "var(--green)" : "var(--red)",
          fontSize: 14,
        }}>
          {flash.msg}
        </div>
      )}

      {queue.length === 0 ? (
        <div className="surface muted" style={{ padding: 24, textAlign: "center" }}>
          No jobs awaiting charge. (Portal shops with completed jobs appear here.)
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {queue.map(j => (
            <div key={j.id} className="card-job" data-testid={`charge-${j.id}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <div className="h3">{j.shop_name}</div>
                  <div className="muted" style={{ fontSize: 13 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model} · {j.calibration_label}</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Completed {fmt(j.actual_completion)}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="font-mono" style={{ fontSize: 18, fontWeight: 700 }}>${j.price.toFixed(2)}</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4, textTransform: "uppercase" }}>
                    {j.card_brand || "card"} •••• {j.card_last4 || "----"}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button className="btn btn-primary"
                  onClick={() => chargeJob(j.id)}
                  disabled={busyId === j.id}
                  data-testid={`charge-btn-${j.id}`}>
                  {busyId === j.id ? "Charging…" : `Charge $${j.price.toFixed(2)} Now`}
                </button>
                <button className="btn btn-ghost"
                  onClick={() => skipJob(j.id)}
                  disabled={busyId === j.id}
                  data-testid={`skip-btn-${j.id}`}>
                  Skip / Bill Manually
                </button>
              </div>
              {errors[j.id] && (
                <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 6,
                              background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
                              color: "var(--red)", fontSize: 13 }}
                     data-testid={`charge-error-${j.id}`}>
                  {errors[j.id]}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}
const Metric = ({ label, value }) => (
  <div>
    <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</div>
    <div className="font-display" style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
  </div>
);
