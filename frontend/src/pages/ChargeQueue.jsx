import { useState, useCallback, useEffect } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

const fmt = (iso) => iso ? new Date(iso).toLocaleString() : "—";

export default function ChargeQueue() {
  const [queue, setQueue] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [errors, setErrors] = useState({}); // job_id -> message

  const load = useCallback(() => api.get("/charge-queue").then(r => setQueue(r.data)), []);
  useEffect(() => { load(); }, [load]);

  const totalPending = queue.reduce((sum, j) => sum + j.price, 0);

  async function chargeNow(jobId) {
    setBusyId(jobId);
    setErrors(prev => ({ ...prev, [jobId]: null }));
    try {
      await api.post(`/charge-queue/${jobId}/charge`);
    } catch (e) {
      setErrors(prev => ({ ...prev, [jobId]: e.response?.data?.detail || "Charge failed." }));
    } finally {
      setBusyId(null);
      await load(); // resyncs card-on-file + any persisted charge_error either way
    }
  }

  async function skipBillManually(jobId) {
    if (!window.confirm("Mark this job as billed manually? It will leave the charge queue and will NOT be charged via Stripe.")) return;
    setBusyId(jobId);
    try {
      await api.post(`/charge-queue/${jobId}/skip`);
      await load();
    } catch (e) {
      setErrors(prev => ({ ...prev, [jobId]: e.response?.data?.detail || "Could not skip this job." }));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 8 }}>Charge Queue</h1>
      <div className="muted" style={{ marginBottom: 16, fontSize: 14 }}>
        Completed portal-shop jobs awaiting card charge. Click <b>Charge Now</b> to bill the card on file.
      </div>

      <div className="surface" style={{ padding: "12px 18px", marginBottom: 16, display: "inline-flex", gap: 24 }}>
        <Metric label="Jobs" value={queue.length} />
        <Metric label="Pending total" value={`$${totalPending.toFixed(2)}`} />
      </div>

      {queue.length === 0 ? (
        <div className="surface muted" style={{ padding: 24, textAlign: "center" }}>
          No jobs awaiting charge. (Portal shops with completed jobs appear here.)
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {queue.map(j => {
            const busy = busyId === j.id;
            const errorMsg = errors[j.id] || j.charge_error;
            return (
              <div key={j.id} className="card-job" data-testid={`charge-${j.id}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                  <div>
                    <div className="h3">{j.shop_name}</div>
                    <div className="muted" style={{ fontSize: 13 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model} · {j.calibration_label}</div>
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Completed {fmt(j.actual_completion)}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="font-mono" style={{ fontSize: 18, fontWeight: 700 }}>${j.price.toFixed(2)}</div>
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                      {j.card_brand} •••• {j.card_last4}
                    </div>
                  </div>
                </div>

                {errorMsg && (
                  <div data-testid={`charge-error-${j.id}`} style={{
                    marginTop: 10, padding: "8px 10px", borderRadius: 6, fontSize: 13,
                    background: "rgba(239,68,68,0.12)", color: "var(--red)",
                  }}>{errorMsg}</div>
                )}

                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <button className="btn btn-primary" disabled={busy}
                    onClick={() => chargeNow(j.id)}
                    data-testid={`charge-btn-${j.id}`}>{busy ? "Charging…" : "Charge Now"}</button>
                  <button className="btn btn-ghost" disabled={busy}
                    onClick={() => skipBillManually(j.id)}
                    data-testid={`skip-btn-${j.id}`}>Skip / Bill Manually</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Shell>
  );
}
const Metric = ({ label, value }) => (
  <div>
    <div className="muted" style={{ fontSize: 12 }}>{label}</div>
    <div className="font-display" style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
  </div>
);
