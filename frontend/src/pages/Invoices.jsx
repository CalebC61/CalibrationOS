import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function Invoices() {
  const [invs, setInvs] = useState([]);
  useEffect(() => { api.get("/invoices").then(r => setInvs(r.data)); }, []);
  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 8 }}>Invoices</h1>
      <div className="muted" style={{ marginBottom: 20, fontSize: 14 }}>
        Mock Xero invoices — these would push to Xero as drafts in production. Maddy receives an email for each.
      </div>
      <div className="surface" style={{ overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
            <Th>Invoice ID</Th><Th>Shop</Th><Th>Status</Th><Th>Total</Th><Th>Created</Th>
          </tr></thead>
          <tbody>
            {invs.map(i => (
              <tr key={i.invoice_id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`invoice-${i.invoice_id}`}>
                <Td className="font-mono">{i.invoice_id}</Td>
                <Td>{i.contact_name}</Td>
                <Td><span className="badge badge-draft">{i.status}</span></Td>
                <Td className="font-mono">${i.total.toFixed(2)}</Td>
                <Td>{new Date(i.created_at).toLocaleString()}</Td>
              </tr>
            ))}
            {invs.length === 0 && <tr><Td colSpan="5" style={{ textAlign: "center", padding: 28 }} className="muted">No invoices yet — complete a job to generate one.</Td></tr>}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
const Th = ({ children }) => <th style={{ padding: "10px 14px", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)", fontWeight: 600 }}>{children}</th>;
const Td = ({ children, colSpan, style, className }) => <td colSpan={colSpan} className={className} style={{ padding: "12px 14px", fontSize: 14, ...(style || {}) }}>{children}</td>;
