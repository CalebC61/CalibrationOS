import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

const fmt = (iso) => iso ? new Date(iso).toLocaleString() : "—";

export default function ChargeQueue() {
  const [queue, setQueue] = useState([]);
  useEffect(() => { api.get("/charge-queue").then(r => setQueue(r.data)); }, []);

  const totalPending = queue.reduce((sum, j) => sum + j.price, 0);

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
                    {j.card_brand} •••• {j.card_last4}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button className="btn btn-primary" disabled
                  title="Charge endpoint will be wired in the next iteration"
                  data-testid={`charge-btn-${j.id}`}>Charge Now (next iter)</button>
                <button className="btn btn-ghost">Skip / Bill Manually</button>
              </div>
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
