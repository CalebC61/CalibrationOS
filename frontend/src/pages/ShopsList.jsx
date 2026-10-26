import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function ShopsList() {
  const [shops, setShops] = useState([]);
  const [q, setQ] = useState("");
  const nav = useNavigate();

  async function load() { const { data } = await api.get("/shops"); setShops(data); }
  useEffect(() => { load(); }, []);

  function copyLink(token) {
    const url = `${window.location.origin}/book/${token}`;
    navigator.clipboard.writeText(url);
    alert(`Booking link copied:\n${url}`);
  }

  const filtered = shops.filter(s => s.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <Shell>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <h1 className="h1">Shops</h1>
        <Link to="/shops/new" className="btn btn-primary" data-testid="add-shop-btn">+ Add Shop</Link>
      </div>
      <input className="input" placeholder="Search shops…" value={q} onChange={e => setQ(e.target.value)}
        style={{ maxWidth: 320, marginBottom: 16 }} data-testid="shop-search" />
      <div className="surface" style={{ overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-elevated)", textAlign: "left" }}>
              <Th>Name</Th><Th>Zone</Th><Th>Tier</Th><Th>Status</Th><Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(s => (
              <tr key={s.id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`shop-row-${s.id}`}>
                <Td><Link to={`/shops/${s.id}`} style={{ color: "var(--accent)" }}>{s.name}</Link>
                  <div className="muted" style={{ fontSize: 12 }}>{s.address}</div>
                </Td>
                <Td><span className={`badge badge-${s.zone}`}>{s.zone}</span></Td>
                <Td><span style={{ textTransform: "capitalize" }}>{s.pricing_tier}</span></Td>
                <Td><span className="badge badge-booked" style={{ textTransform: "capitalize" }}>{s.status}</span></Td>
                <Td>
                  <button className="btn btn-ghost" onClick={() => copyLink(s.booking_link_token)} data-testid={`copy-link-${s.id}`}>
                    Copy Link
                  </button>
                </Td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><Td colSpan="5" style={{ textAlign: "center", padding: 32 }} className="muted">No shops yet.</Td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

const Th = ({ children }) => <th style={{ padding: "10px 14px", fontSize: 12,
  letterSpacing: "0.08em", color: "var(--text-muted)", fontWeight: 600 }}>{children}</th>;
const Td = ({ children, colSpan, style }) => <td colSpan={colSpan} style={{ padding: "12px 14px", fontSize: 14, ...(style || {}) }}>{children}</td>;
