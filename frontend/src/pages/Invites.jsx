import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function Invites() {
  const [shops, setShops] = useState([]);
  const [invites, setInvites] = useState([]);
  const [emailLog, setEmailLog] = useState({ sent: [], pending_manual: [] });
  const [selectedShop, setSelectedShop] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastCreated, setLastCreated] = useState(null);

  async function load() {
    const [s, i, e] = await Promise.all([api.get("/shops"), api.get("/invites"), api.get("/email-log")]);
    setShops(s.data); setInvites(i.data); setEmailLog(e.data);
  }
  useEffect(() => { load(); }, []);

  async function send() {
    setBusy(true);
    try {
      const { data } = await api.post("/invites", { shop_id: selectedShop, recipient_email: email, origin: window.location.origin });
      setLastCreated(data);
      setEmail(""); setSelectedShop("");
      load();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  }

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Portal Invitations</h1>

      <div className="surface" style={{ padding: 20, marginBottom: 24, maxWidth: 720 }}>
        <div className="h3" style={{ marginBottom: 12 }}>Send a new invitation</div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 2fr 1fr", gap: 10 }}>
          <select className="input" value={selectedShop} onChange={e => setSelectedShop(e.target.value)} data-testid="invite-shop">
            <option value="">— Select shop —</option>
            {shops.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <input className="input" type="email" placeholder="shop@example.com" value={email}
            onChange={e => setEmail(e.target.value)} data-testid="invite-email" />
          <button className="btn btn-primary" disabled={!selectedShop || !email || busy}
            onClick={send} data-testid="send-invite">{busy ? "Sending…" : "Send invite"}</button>
        </div>
        {!emailLog.sent.length && emailLog.pending_manual.length > 0 && (
          <div className="muted" style={{ fontSize: 12, marginTop: 10, color: "var(--yellow)" }}>
            ⚠ Resend API key not configured — invites are queued below for manual sending. Add RESEND_API_KEY to /app/backend/.env to enable auto-send.
          </div>
        )}
        {lastCreated && (
          <div className="elevated" style={{ padding: 12, marginTop: 14 }} data-testid="last-invite">
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Invite created for {lastCreated.shop_name}</div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>If email didn't send, copy this link:</div>
            <div className="font-mono" style={{ fontSize: 12, padding: 8, background: "var(--bg-elevated)", borderRadius: 6, wordBreak: "break-all" }}>{lastCreated.register_url}</div>
            <button className="btn btn-ghost" style={{ marginTop: 8, fontSize: 12 }}
              onClick={() => { navigator.clipboard.writeText(lastCreated.register_url); alert("Copied!"); }}>Copy link</button>
          </div>
        )}
      </div>

      <h2 className="h3" style={{ marginBottom: 10 }}>All Invitations</h2>
      <div className="surface" style={{ overflow: "hidden", marginBottom: 24 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
            <Th>Shop</Th><Th>Email</Th><Th>Status</Th><Th>Sent</Th><Th>Expires</Th>
          </tr></thead>
          <tbody>
            {invites.map(i => (
              <tr key={i.id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`inv-${i.id}`}>
                <Td>{i.shop_name}</Td>
                <Td className="font-mono" style={{ fontSize: 12 }}>{i.recipient_email}</Td>
                <Td><span className={`badge badge-${i.status === "registered" ? "complete" : "pending"}`}>{i.status}</span></Td>
                <Td className="muted" style={{ fontSize: 12 }}>{new Date(i.created_at).toLocaleDateString()}</Td>
                <Td className="muted" style={{ fontSize: 12 }}>{new Date(i.expires_at).toLocaleDateString()}</Td>
              </tr>
            ))}
            {invites.length === 0 && <tr><Td colSpan="5" style={{ textAlign: "center", padding: 24 }} className="muted">No invitations yet.</Td></tr>}
          </tbody>
        </table>
      </div>

      {emailLog.pending_manual.length > 0 && (
        <>
          <h2 className="h3" style={{ marginBottom: 10 }}>Manual-send queue (no Resend key)</h2>
          <div className="surface" style={{ padding: 12 }}>
            {emailLog.pending_manual.slice(0, 10).map(e => (
              <div key={e.id} className="elevated" style={{ padding: 10, marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>→ {e.to}</div>
                <div className="muted" style={{ fontSize: 12 }}>{e.subject}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </Shell>
  );
}
const Th = ({ children }) => <th style={{ padding: "10px 14px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>{children}</th>;
const Td = ({ children, colSpan, className, style }) => <td colSpan={colSpan} className={className} style={{ padding: "12px 14px", fontSize: 14, ...(style || {}) }}>{children}</td>;
