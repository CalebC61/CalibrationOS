import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import AddressField from "../components/AddressField";
import Shell from "../components/Shell";

const EMPTY = {
  name: "", contact_name: "", contact_phone: "", contact_email: "",
  address: "", place_id: null, pricing_tier: "standard",
  custom_rate_static: 125, custom_rate_dynamic: 125, custom_rate_dual: 175,
  custom_rate_triple: 185, custom_rate_tesla: 225, notes: "",
};

function messageFrom(error) {
  const detail = error?.response?.data?.detail;
  if (!detail) return "Could not save the shop.";
  if (typeof detail === "string") return detail;
  if (detail.message) return detail.message;
  return Object.values(detail).join(" ");
}

export default function ShopNew() {
  const nav = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [confirm, setConfirm] = useState(null);
  const [accepted, setAccepted] = useState(false);
  const [duplicate, setDuplicate] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);
  const [inviteState, setInviteState] = useState(null);

  function set(key, value) {
    setForm(prev => ({ ...prev, [key]: value }));
    if (key === "address") { setConfirm(null); setAccepted(false); }
  }

  async function save(acknowledge) {
    setSaving(true);
    setError("");
    try {
      const payload = {
        ...form,
        address_confirmed: accepted,
        confirmed_address: confirm?.formatted_address || null,
        acknowledge_duplicate: Boolean(acknowledge),
        place_id: form.place_id,
      };
      if (form.pricing_tier !== "custom") {
        ["static", "dynamic", "dual", "triple", "tesla"].forEach(key => delete payload[`custom_rate_${key}`]);
      }
      const { data } = await api.post("/shops", payload);
      setCreated(data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.code === "needs_confirmation") {
        setConfirm(detail);
        setError("Confirm the address Google found, then save.");
      } else if (detail?.code === "duplicate") {
        setDuplicate(detail);
        setError(detail.message);
      } else {
        setError(messageFrom(err));
      }
    } finally {
      setSaving(false);
    }
  }

  async function sendInvite() {
    setInviteState("sending");
    try {
      const { data } = await api.post("/invites", {
        shop_id: created.id,
        recipient_email: created.contact_email,
      });
      setInviteState(data);
    } catch (err) {
      setInviteState({ email_status: "failed", email_error: messageFrom(err) });
    }
  }

  if (created) {
    const url = `${window.location.origin}/book/${created.booking_link_token}`;
    return (
      <Shell>
        <div className="page-fade" style={{ maxWidth: 640 }}>
          <h1 className="h1" style={{ marginBottom: 8 }}>Shop saved</h1>
          <p className="muted" style={{ marginBottom: 16 }}>
            {created.name} is on file at {created.formatted_address || created.address}. The shop contact signs the agreement from the invite. You do not sign for them.
          </p>
          <div className="surface" style={{ padding: 16, marginBottom: 16 }}>
            <div className="label">Contact</div>
            <div>{created.contact_name || "—"} · {created.contact_phone} · {created.contact_email}</div>
            <button className="btn btn-primary" style={{ marginTop: 14 }} onClick={sendInvite} disabled={inviteState === "sending"} data-testid="send-invite">
              {inviteState === "sending" ? "Sending…" : "Send invite"}
            </button>
            {inviteState && inviteState !== "sending" && (
              <div style={{ marginTop: 12 }} data-testid="invite-result">
                <div>{inviteState.email_status === "sent" ? "Invite sent." : inviteState.email_status === "held" ? "Held in Email preview. Shop email is off." : "Not delivered."}</div>
                {inviteState.email_error && <div className="muted" style={{ fontSize: 13 }}>{inviteState.email_error}</div>}
                {inviteState.register_url && (
                  <div className="font-mono" style={{ fontSize: 12, marginTop: 8, wordBreak: "break-all" }}>{inviteState.register_url}</div>
                )}
              </div>
            )}
          </div>
          <div className="surface" style={{ padding: 16, marginBottom: 16 }}>
            <div className="label">Booking link (opens after they sign and save a card)</div>
            <div className="font-mono" style={{ fontSize: 13, wordBreak: "break-all" }} data-testid="booking-link">{url}</div>
          </div>
          <button className="btn btn-ghost" onClick={() => nav("/shops")}>Back to Shops</button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div style={{ maxWidth: 720 }}>
        <h1 className="h1" style={{ marginBottom: 20 }}>Add a Shop</h1>
        <div className="surface" style={{ padding: 24 }}>
          <Field label="Business name *">
            <input className="input" value={form.name} onChange={e => set("name", e.target.value)} data-testid="shop-name" />
          </Field>
          <div className="form-row">
            <Field label="Contact name">
              <input className="input" value={form.contact_name} onChange={e => set("contact_name", e.target.value)} data-testid="shop-contact-name" />
            </Field>
            <Field label="Mobile *">
              <input className="input" value={form.contact_phone} onChange={e => set("contact_phone", e.target.value)} inputMode="tel" data-testid="shop-contact-phone" />
            </Field>
          </div>
          <Field label="Email *">
            <input className="input" type="email" value={form.contact_email} onChange={e => set("contact_email", e.target.value)} data-testid="shop-contact-email" />
          </Field>
          <Field label="Service address *">
            <AddressField
              value={form.address}
              onChange={value => set("address", value)}
              onPlace={place => setForm(prev => ({ ...prev, address: place.address, place_id: place.placeId }))}
              placeholder="1234 E Williams Field Rd, Gilbert, AZ"
              testId="shop-address"
            />
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>Must be a real Phoenix Valley address. You'll confirm the formatted address before it saves.</p>
          </Field>
          {confirm && (
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 14 }} data-testid="confirm-address">
              <input type="checkbox" checked={accepted} onChange={e => { setAccepted(e.target.checked); if (e.target.checked) setForm(prev => ({ ...prev, address: confirm.formatted_address })); }} />
              <span>Google found: <b>{confirm.formatted_address}</b>{confirm.zone ? ` · ${confirm.zone === "west" ? "West Valley" : "East Valley"}` : ""}</span>
            </label>
          )}

          <Field label="Pricing tier">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {["standard", "custom"].map(tier => (
                <button key={tier} type="button" className={"btn " + (form.pricing_tier === tier ? "btn-primary" : "btn-ghost")}
                  onClick={() => set("pricing_tier", tier)} data-testid={`tier-${tier}`}>
                  {tier === "standard" ? "Standard" : "Custom rates"}
                </button>
              ))}
            </div>
          </Field>
          {form.pricing_tier === "custom" && (
            <div className="elevated" style={{ padding: 16, marginBottom: 16 }}>
              <div className="form-row">
                <Field label="Static"><input className="input" type="number" value={form.custom_rate_static} onChange={e => set("custom_rate_static", parseFloat(e.target.value))} /></Field>
                <Field label="Dynamic"><input className="input" type="number" value={form.custom_rate_dynamic} onChange={e => set("custom_rate_dynamic", parseFloat(e.target.value))} /></Field>
              </div>
              <div className="form-row">
                <Field label="Dual"><input className="input" type="number" value={form.custom_rate_dual} onChange={e => set("custom_rate_dual", parseFloat(e.target.value))} /></Field>
                <Field label="Triple / Subaru"><input className="input" type="number" value={form.custom_rate_triple} onChange={e => set("custom_rate_triple", parseFloat(e.target.value))} /></Field>
              </div>
              <Field label="Tesla"><input className="input" type="number" value={form.custom_rate_tesla} onChange={e => set("custom_rate_tesla", parseFloat(e.target.value))} /></Field>
            </div>
          )}
          <Field label="Notes (internal)">
            <textarea className="input" rows={2} value={form.notes} onChange={e => set("notes", e.target.value)} />
          </Field>
          {error && <div style={{ color: "var(--red)", fontSize: 14, marginBottom: 12 }} data-testid="shop-error">{error}</div>}
          {duplicate && (
            <button className="btn btn-ghost" style={{ marginRight: 8 }} type="button" onClick={() => save(true)} disabled={saving} data-testid="save-anyway">
              Save anyway
            </button>
          )}
          <button className="btn btn-primary" type="button" onClick={() => save(false)} disabled={saving || !form.name || !form.address} data-testid="save-shop">
            {saving ? "Saving…" : "Save shop"}
          </button>
        </div>
      </div>
    </Shell>
  );
}

const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}>
    <label className="label">{label}</label>
    {children}
  </div>
);
