import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, formatDate } from "../lib/api";
import Shell from "../components/Shell";

export default function ShopDetail() {
  const { id } = useParams();
  const [shop, setShop] = useState(null);
  const [edit, setEdit] = useState({});
  const [saving, setSaving] = useState(false);

  async function load() {
    const { data } = await api.get(`/shops/${id}`);
    setShop(data); setEdit(data);
  }
  useEffect(() => { load(); }, [id]);

  async function save() {
    setSaving(true);
    try {
      const { data } = await api.put(`/shops/${id}`, edit);
      setShop(data); setEdit(data);
      alert("Saved");
    } finally { setSaving(false); }
  }

  async function regen() {
    if (!window.confirm("Generate a new booking link? The old one will stop working.")) return;
    const { data } = await api.post(`/shops/${id}/regenerate-link`);
    setShop(s => ({ ...s, booking_link_token: data.booking_link_token }));
  }

  if (!shop) return <Shell><div className="muted">Loading…</div></Shell>;

  const url = `${window.location.origin}/book/${shop.booking_link_token}`;

  return (
    <Shell>
      <div style={{ maxWidth: 820 }}>
        <h1 className="h1" style={{ marginBottom: 6 }}>{shop.name}</h1>
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          <span className={`badge badge-${shop.zone}`}>{shop.zone === "west" ? "West Valley" : "East Valley"}</span>
          <span className="badge badge-booked" style={{ textTransform: "capitalize" }}>{shop.status}</span>
        </div>

        <div className="surface" style={{ padding: 20, marginBottom: 16 }}>
          <div className="h3" style={{ marginBottom: 12 }}>Booking Link</div>
          <div className="font-mono" style={{ background: "var(--bg-elevated)", padding: 10, borderRadius: 6, fontSize: 13, wordBreak: "break-all" }} data-testid="shop-booking-link">{url}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="btn btn-primary" onClick={() => { navigator.clipboard.writeText(url); alert("Copied!"); }}>Copy</button>
            <a className="btn btn-ghost" href={url} target="_blank" rel="noreferrer">Open Public Page</a>
            <button className="btn btn-ghost" onClick={regen} data-testid="regen-link">Regenerate</button>
          </div>
        </div>

        <div className="surface" style={{ padding: 20 }}>
          <div className="h3" style={{ marginBottom: 12 }}>Details</div>
          <Row>
            <Field label="Name"><input className="input" value={edit.name || ""} onChange={e => setEdit({...edit, name: e.target.value})} /></Field>
            <Field label="Status">
              <select className="input" value={edit.status} onChange={e => setEdit({...edit, status: e.target.value})}>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="inactive">Inactive</option>
              </select>
            </Field>
          </Row>
          <Row>
            <Field label="Contact name"><input className="input" value={edit.contact_name || ""} onChange={e => setEdit({...edit, contact_name: e.target.value})} /></Field>
            <Field label="Contact phone"><input className="input" value={edit.contact_phone || ""} onChange={e => setEdit({...edit, contact_phone: e.target.value})} /></Field>
          </Row>
          <Field label="Address"><input className="input" value={edit.address || ""} onChange={e => setEdit({...edit, address: e.target.value})} /></Field>
          <Field label="Contact email"><input className="input" value={edit.contact_email || ""} onChange={e => setEdit({...edit, contact_email: e.target.value})} /></Field>
          <button className="btn btn-primary" disabled={saving} onClick={save} data-testid="save-shop">{saving ? "Saving…" : "Save Changes"}</button>
        </div>
      </div>
    </Shell>
  );
}

const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>
);
