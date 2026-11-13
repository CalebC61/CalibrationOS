import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

function copyText(value) {
  navigator.clipboard.writeText(value);
}

export default function Requests() {
  const [shops, setShops] = useState([]);
  const [requests, setRequests] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [lastInvite, setLastInvite] = useState(null);

  async function load() {
    setLoadError("");
    try {
      const [created, pending] = await Promise.all([
        api.get("/new-shops"),
        api.get("/shop-requests"),
      ]);
      setShops(created.data);
      setRequests(pending.data);
    } catch {
      setLoadError("Could not load new shops.");
    }
  }
  useEffect(() => { load(); }, []);

  async function review(id, action, body) {
    setBusy(id + action);
    setNote("");
    try {
      await api.post(`/shops/${id}/${action}`, body);
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setNote(typeof detail === "string" ? detail : "Could not update that shop.");
    } finally {
      setBusy("");
    }
  }

  async function decide(id, action) {
    setBusy(id + action);
    setNote("");
    setLastInvite(null);
    try {
      const { data } = await api.post(`/shop-requests/${id}/${action}`);
      if (action === "approve") {
        const status = data.invite?.email_status;
        setLastInvite(data.invite || null);
        if (status === "sent") setNote(`Shop created and the invite was sent to ${data.invite.recipient_email}.`);
        else if (status === "held") setNote("Shop created. Shop email is held. Copy the setup link.");
        else setNote(`Shop created. Invite was not delivered${data.invite?.email_error ? `: ${data.invite.email_error}` : "."}`);
      }
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setNote(typeof detail === "string" ? detail : "Could not update that request.");
    } finally {
      setBusy("");
    }
  }

  const pending = requests.filter(row => row.status === "pending");

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 8 }}>New shops</h1>
      <p className="muted" style={{ marginBottom: 16 }}>
        These shops created their own accounts. Flag one to look at later. Suspend one to stop booking. You do not approve them first.
      </p>
      {note && <div className="surface" style={{ padding: 12, marginBottom: 16 }}>{note}</div>}
      {lastInvite?.register_url && (
        <div className="surface" style={{ padding: 12, marginBottom: 16 }} data-testid="request-invite-link">
          <div className="font-mono" style={{ fontSize: 12, wordBreak: "break-all" }}>{lastInvite.register_url}</div>
          <button type="button" className="btn btn-ghost" style={{ marginTop: 8 }}
            onClick={() => copyText(lastInvite.register_url)} data-testid="copy-request-invite">
            {lastInvite.email_status === "held" ? "Held" : "Copy"}
          </button>
        </div>
      )}
      {loadError && <p role="alert" style={{ color: "var(--red)", marginBottom: 12 }}>{loadError}</p>}
      <div className="surface" style={{ overflow: "auto", marginBottom: 28 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
              <Th>Shop</Th><Th>Contact</Th><Th>Address</Th><Th>Status</Th><Th></Th>
            </tr>
          </thead>
          <tbody>
            {shops.map(row => (
              <tr key={row.id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`new-shop-${row.id}`}>
                <Td>{row.name}{row.flagged && <div className="muted" style={{ fontSize: 12 }}>Flagged</div>}</Td>
                <Td>{row.contact_name}<div className="muted" style={{ fontSize: 12 }}>{row.contact_phone}<br />{row.contact_email}</div></Td>
                <Td>{row.address}</Td>
                <Td>{row.status}</Td>
                <Td>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button className="btn btn-ghost" disabled={!!busy} onClick={() => review(row.id, "flag", { flagged: !row.flagged })} data-testid={`flag-${row.id}`}>
                      {row.flagged ? "Clear flag" : "Flag"}
                    </button>
                    <button className="btn btn-primary" disabled={!!busy} onClick={() => review(row.id, "suspend", { suspended: row.status !== "suspended" })} data-testid={`suspend-${row.id}`}>
                      {row.status === "suspended" ? "Reinstate" : "Suspend"}
                    </button>
                  </div>
                </Td>
              </tr>
            ))}
            {shops.length === 0 && !loadError && <tr><Td colSpan="5" style={{ textAlign: "center" }} className="muted">No new shops yet.</Td></tr>}
          </tbody>
        </table>
      </div>

      <h2 className="h2" style={{ marginBottom: 8 }}>Earlier requests</h2>
      <p className="muted" style={{ marginBottom: 16 }}>
        Requests sent before shops could sign up themselves. Approve still creates the shop and the invite.
      </p>
      <div className="surface" style={{ overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
              <Th>Shop</Th><Th>Contact</Th><Th>Address</Th><Th>Status</Th><Th></Th>
            </tr>
          </thead>
          <tbody>
            {pending.map(row => (
              <tr key={row.id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`request-${row.id}`}>
                <Td>{row.shop_name}</Td>
                <Td>{row.contact_name}<div className="muted" style={{ fontSize: 12 }}>{row.mobile}<br />{row.email}</div></Td>
                <Td>{row.address}</Td>
                <Td>{row.status}</Td>
                <Td>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button className="btn btn-primary" disabled={!!busy} onClick={() => decide(row.id, "approve")} data-testid={`approve-${row.id}`}>Approve</button>
                    <button className="btn btn-ghost" disabled={!!busy} onClick={() => decide(row.id, "decline")}>Decline</button>
                  </div>
                </Td>
              </tr>
            ))}
            {pending.length === 0 && !loadError && <tr><Td colSpan="5" style={{ textAlign: "center" }} className="muted">No pending requests.</Td></tr>}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

const Th = ({ children }) => <th style={{ padding: "10px 14px", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>{children}</th>;
const Td = ({ children, colSpan, style, className }) => <td colSpan={colSpan} className={className} style={{ padding: "12px 14px", fontSize: 14, verticalAlign: "top", ...(style || {}) }}>{children}</td>;
