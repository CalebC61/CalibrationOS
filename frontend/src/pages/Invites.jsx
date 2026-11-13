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
  const [loadError, setLoadError] = useState("");

  async function load() {
    setLoadError("");
    try {
      const [s, i, e] = await Promise.all([api.get("/shops"), api.get("/invites"), api.get("/email-log")]);
      const shopList = Array.isArray(s.data) ? s.data : null;
      const inviteList = Array.isArray(i.data) ? i.data : null;
      const sent = e.data && Array.isArray(e.data.sent) ? e.data.sent : null;
      const pending = e.data && Array.isArray(e.data.pending_manual) ? e.data.pending_manual : null;
      if (!shopList || !inviteList || !sent || !pending) {
        setLoadError("Couldn't read shops or invites. Reload the page.");
        return;
      }
      setShops(shopList);
      setInvites(inviteList);
      setEmailLog({ sent, pending_manual: pending });
    } catch (err) {
      const detail = err.response?.data?.detail;
      setLoadError(typeof detail === "string" ? detail : "Couldn't load shops or invites. Reload the page.");
    }
  }
  useEffect(() => { load(); }, []);

  async function resend(id) {
    setBusy(true);
    try {
      const { data } = await api.post(`/invites/${id}/resend`);
      setLastCreated(data);
      load();
    } catch (e) { alert(e.response?.data?.detail || "Could not resend"); }
    finally { setBusy(false); }
  }

  async function send() {
    setBusy(true);
    try {
      const { data } = await api.post("/invites", { shop_id: selectedShop, recipient_email: email });
      setLastCreated(data);
      setEmail(""); setSelectedShop("");
      load();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  }

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Portal Invitations</h1>
      {loadError && (
        <div role="alert" data-testid="invites-load-error" style={{ color: "var(--red)", marginBottom: 16 }}>
          {loadError}
        </div>
      )}

      <div className="surface" style={{ padding: 20, marginBottom: 24, maxWidth: 720 }}>
        <div className="h3" style={{ marginBottom: 12 }}>Send a new invitation</div>
        <div className="form-row" style={{ gridTemplateColumns: "1fr" }}>
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
      <div className="surface" style={{ overflow: "auto", marginBottom: 24 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
            <Th>Shop</Th><Th>Email</Th><Th>Status</Th><Th>Email</Th><Th>Expires</Th><Th></Th>
          </tr></thead>
          <tbody>
            {invites.map(i => (
              <tr key={i.id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`inv-${i.id}`}>
                <Td>{i.shop_name}</Td>
                <Td className="font-mono" style={{ fontSize: 12 }}>{i.recipient_email}</Td>
                <Td><span className={`badge badge-${i.status === "registered" ? "complete" : "pending"}`}>{i.status}</span></Td>
                <Td>
                  <span data-testid={`invite-email-${i.id}`}>{i.email_status === "sent" ? "Sent" : i.email_status === "held" ? "Held" : "Not delivered"}</span>
                  {i.email_error && <div className="muted" style={{ fontSize: 12 }}>{i.email_error}</div>}
                  {i.register_url && i.email_status !== "sent" && i.status !== "registered" && (
                    <div style={{ marginTop: 6 }}>
                      <div className="font-mono" style={{ fontSize: 12, wordBreak: "break-all" }} data-testid={`invite-link-${i.id}`}>{i.register_url}</div>
                      <button type="button" className="btn btn-ghost" style={{ fontSize: 12, marginTop: 6 }}
                        data-testid={`copy-invite-${i.id}`}
                        onClick={() => { navigator.clipboard.writeText(i.register_url); alert("Copied."); }}>
                        Copy
                      </button>
                    </div>
                  )}
                </Td>
                <Td className="muted" style={{ fontSize: 12 }}>{new Date(i.expires_at).toLocaleDateString()}</Td>
                <Td>
                  {i.status !== "registered" && (
                    <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => resend(i.id)} data-testid={`resend-${i.id}`}>Resend</button>
                  )}
                </Td>
              </tr>
            ))}
            {invites.length === 0 && !loadError && <tr><Td colSpan="6" style={{ textAlign: "center", padding: 24 }} className="muted">No invitations yet.</Td></tr>}
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
const Th = ({ children }) => <th style={{ padding: "10px 14px", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", fontWeight: 600 }}>{children}</th>;
const Td = ({ children, colSpan, className, style }) => <td colSpan={colSpan} className={className} style={{ padding: "12px 14px", fontSize: 14, ...(style || {}) }}>{children}</td>;
