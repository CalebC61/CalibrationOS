import { useEffect, useState } from "react";
import { api } from "../lib/api";
import OwnerPage, { OwnerTitle } from "../components/OwnerPage";

const KIND_LABEL = {
  booking_confirmed: "Booking Confirmed", on_my_way: "On My Way",
  completed: "Completed", cancelled: "Cancelled", generic: "Generic",
};

export default function Messages({ bare = false }) {
  const [logs, setLogs] = useState([]);
  useEffect(() => { api.get("/sms-log").then(r => setLogs(r.data)); }, []);
  return (
    <OwnerPage bare={bare}>
      <OwnerTitle bare={bare} style={{ marginBottom: 8 }}>Messages</OwnerTitle>
      <div className="muted" style={{ marginBottom: 20, fontSize: 14 }}>
        Mock SMS log — these would send via Twilio in production.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {logs.map(l => (
          <div key={l.id} className="surface" style={{ padding: 14 }} data-testid={`sms-${l.id}`}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <div className="font-mono" style={{ fontSize: 13 }}>→ {l.to}</div>
              <div className="muted" style={{ fontSize: 12 }}>{new Date(l.sent_at).toLocaleString()}</div>
            </div>
            <div className="badge badge-booked" style={{ marginTop: 6 }}>{KIND_LABEL[l.kind] || l.kind}</div>
            <div style={{ marginTop: 8, fontSize: 14 }}>{l.body}</div>
          </div>
        ))}
        {logs.length === 0 && <div className="muted">No messages yet.</div>}
      </div>
    </OwnerPage>
  );
}
