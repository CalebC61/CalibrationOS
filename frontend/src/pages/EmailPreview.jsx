import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function EmailPreview() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    api.get("/email-outbox").then(r => setRows(r.data)).catch(() => setRows([]));
  }, []);

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 8 }}>Email preview</h1>
      <p className="muted" style={{ marginBottom: 16, maxWidth: 640 }}>
        Shop email is off, so these messages were not sent. Turn on SHOP_EMAILS_ENABLED when you want them to go out. Invites and password resets still send if the address is on TEST_EMAIL_ALLOWLIST.
      </p>
      <div className="surface" style={{ overflow: "auto", marginBottom: 16 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
              <Th>When</Th><Th>To</Th><Th>Kind</Th><Th>Subject</Th><Th></Th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id} style={{ borderTop: "1px solid var(--border)" }}>
                <Td className="muted" style={{ fontSize: 12 }}>{row.created_at ? new Date(row.created_at).toLocaleString() : ""}</Td>
                <Td>{row.to}</Td>
                <Td>{row.kind}</Td>
                <Td>{row.subject}</Td>
                <Td><button className="btn btn-ghost" type="button" onClick={() => setOpen(row)} data-testid={`preview-${row.id}`}>Preview</button></Td>
              </tr>
            ))}
            {rows.length === 0 && <tr><Td colSpan="5" style={{ textAlign: "center" }} className="muted">Nothing held. Shop mail will show up here instead of being sent.</Td></tr>}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="surface" style={{ padding: 16 }} data-testid="email-preview-body">
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div>
              <div className="h3">{open.subject}</div>
              <div className="muted" style={{ fontSize: 13 }}>To {open.to} · {open.status} · {open.reason}</div>
            </div>
            <button className="btn btn-ghost" type="button" onClick={() => setOpen(null)}>Close</button>
          </div>
          <iframe
            title="Email preview"
            sandbox=""
            style={{ width: "100%", minHeight: 360, marginTop: 12, border: "1px solid var(--border)", borderRadius: 8, background: "#fff" }}
            srcDoc={open.html || ""}
          />
        </div>
      )}
    </Shell>
  );
}

const Th = ({ children }) => <th style={{ padding: "10px 14px", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>{children}</th>;
const Td = ({ children, colSpan, style, className }) => <td colSpan={colSpan} className={className} style={{ padding: "12px 14px", fontSize: 14, ...(style || {}) }}>{children}</td>;
