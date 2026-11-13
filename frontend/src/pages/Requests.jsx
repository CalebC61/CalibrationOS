import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function Requests() {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [setupLink, setSetupLink] = useState("");
  const [linkHeld, setLinkHeld] = useState(false);
  const [loadError, setLoadError] = useState("");

  async function load() {
    setLoadError("");
    try {
      const { data } = await api.get("/shop-requests");
      const list = Array.isArray(data) ? data : data?.requests;
      if (!Array.isArray(list)) {
        setRows([]);
        setLoadError("Couldn't read shop requests. Reload the page.");
        return;
      }
      setRows(list);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setLoadError(typeof detail === "string" ? detail : "Couldn't load shop requests. Reload the page.");
    }
  }
  useEffect(() => { load(); }, []);

  async function decide(id, action) {
    setBusy(id + action);
    setNote("");
    setSetupLink("");
    setLinkHeld(false);
    try {
      const { data } = await api.post(`/shop-requests/${id}/${action}`);
      if (action === "approve") {
        const invite = data.invite || {};
        const url = data.register_url || invite.register_url || "";
        const held = invite.email_status === "held";
        setSetupLink(url);
        setLinkHeld(held);
        if (invite.email_status === "sent") {
          setNote(`Shop created and the invite was sent to ${invite.recipient_email}.`);
        } else if (held) {
          setNote(url
            ? "Shop created. Shop email is off, so the setup link is held here."
            : "Shop created. Shop email is off, and the setup link could not be built.");
        } else {
          setNote(`Shop created. Invite was not delivered${invite.email_error ? `: ${invite.email_error}` : "."}`);
        }
      }
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setNote(typeof detail === "string" ? detail : "Could not update that request.");
    } finally {
      setBusy("");
    }
  }

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 8 }}>Shop requests</h1>
      <p className="muted" style={{ marginBottom: 16 }}>Approve creates the shop and emails the setup link. Decline leaves them off the schedule.</p>
      {note && <div className="surface" style={{ padding: 12, marginBottom: 16 }} data-testid="approve-note">{note}</div>}
      {setupLink && (
        <div className="surface" style={{ padding: 12, marginBottom: 16 }} data-testid="approve-invite-link">
          <div className="font-mono" style={{ fontSize: 12, wordBreak: "break-all" }}>{setupLink}</div>
          <button type="button" className="btn btn-ghost" style={{ marginTop: 8, fontSize: 12 }}
            data-testid="copy-approve-link"
            onClick={() => { navigator.clipboard.writeText(setupLink); alert("Copied."); }}>
            {linkHeld ? "Held" : "Copy"}
          </button>
        </div>
      )}
      {loadError && <div className="surface" style={{ padding: 12, marginBottom: 16 }} role="alert">{loadError}</div>}
      <div className="surface" style={{ overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
              <Th>Shop</Th><Th>Contact</Th><Th>Address</Th><Th>Status</Th><Th></Th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`request-${row.id}`}>
                <Td>{row.shop_name}</Td>
                <Td>{row.contact_name}<div className="muted" style={{ fontSize: 12 }}>{row.mobile}<br />{row.email}</div></Td>
                <Td>{row.address}</Td>
                <Td>{row.status}</Td>
                <Td>
                  {row.status === "pending" && (
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button className="btn btn-primary" disabled={!!busy} onClick={() => decide(row.id, "approve")} data-testid={`approve-${row.id}`}>Approve</button>
                      <button className="btn btn-ghost" disabled={!!busy} onClick={() => decide(row.id, "decline")}>Decline</button>
                    </div>
                  )}
                </Td>
              </tr>
            ))}
            {rows.length === 0 && !loadError && <tr><Td colSpan="5" style={{ textAlign: "center" }} className="muted">No requests yet.</Td></tr>}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

const Th = ({ children }) => <th style={{ padding: "10px 14px", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>{children}</th>;
const Td = ({ children, colSpan, style, className }) => <td colSpan={colSpan} className={className} style={{ padding: "12px 14px", fontSize: 14, verticalAlign: "top", ...(style || {}) }}>{children}</td>;
