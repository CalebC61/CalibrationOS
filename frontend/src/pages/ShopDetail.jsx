import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function ShopDetail() {
  const { id } = useParams();
  const [shop, setShop] = useState(null);
  const [edit, setEdit] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let gone = false;
    api.get(`/shops/${id}`).then(({ data }) => {
      if (!gone) { setShop(data); setEdit(data); }
    });
    return () => { gone = true; };
  }, [id]);

  async function save() {
    setSaving(true);
    try {
      const { data } = await api.put(`/shops/${id}`, {
        name: edit.name,
        contact_name: edit.contact_name || null,
        contact_phone: edit.contact_phone || null,
        contact_email: edit.contact_email || null,
        address: edit.address,
        pricing_tier: edit.pricing_tier || "standard",
        status: edit.status,
        notes: edit.notes || null,
      });
      setShop(data); setEdit(data);
      alert("Saved");
    } catch (e) {
      const detail = e.response?.data?.detail;
      alert(typeof detail === "string" ? detail : "Could not save this shop. Try again.");
    } finally { setSaving(false); }
  }

  if (!shop) return <Shell><div className="muted">Loading…</div></Shell>;

  return (
    <Shell>
      <div style={{ maxWidth: 820 }}>
        <h1 className="h1" style={{ marginBottom: 6 }}>{shop.name}</h1>
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          <span className={`badge badge-${shop.zone}`}>{shop.zone === "west" ? "West Valley" : "East Valley"}</span>
          <span className="badge badge-booked" style={{ textTransform: "capitalize" }}>{shop.status}</span>
        </div>

        <div className="surface" style={{ padding: 20, marginBottom: 16 }}>
          <div className="h3" style={{ marginBottom: 8 }}>Booking</div>
          <p className="muted" style={{ fontSize: 14, marginTop: 0, marginBottom: 14 }}>
            This shop books from the shop portal after they log in. There is no public booking link.
          </p>
          <Link to={`/shops/${shop.id}/book`} className="btn btn-primary" data-testid="book-job">Book a job</Link>
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
                <option value="suspended">Suspended</option>
              </select>
            </Field>
          </Row>
          <Row>
            <Field label="Contact name"><input className="input" value={edit.contact_name || ""} onChange={e => setEdit({...edit, contact_name: e.target.value})} /></Field>
            <Field label="Contact phone"><input className="input" value={edit.contact_phone || ""} onChange={e => setEdit({...edit, contact_phone: e.target.value})} /></Field>
          </Row>
          <Field label="Address"><input className="input" value={edit.address || ""} onChange={e => setEdit({...edit, address: e.target.value})} data-testid="shop-address" /></Field>
          <div className="muted" style={{ fontSize: 13, marginTop: -8, marginBottom: 14 }}>
            A new address updates this shop’s map pin. Nothing is sent to the shop.
          </div>
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
