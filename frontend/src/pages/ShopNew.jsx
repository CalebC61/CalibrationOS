import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function ShopNew() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    name: "", contact_name: "", contact_phone: "", contact_email: "",
    address: "", pricing_tier: "standard",
    custom_rate_static: 125, custom_rate_dynamic: 125, custom_rate_dual: 175,
    custom_rate_triple: 185, custom_rate_tesla: 225,
    notes: "",
  });
  const [zone, setZone] = useState(null);
  const [showTerms, setShowTerms] = useState(false);
  const [signature, setSignature] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null);

  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

  async function detectZone() {
    if (!form.address) return;
    const { data } = await api.post("/geocode", { address: form.address });
    setZone(data);
  }

  async function save() {
    setSaving(true);
    try {
      const payload = { ...form, terms_signed_by: signature };
      if (form.pricing_tier !== "custom") {
        ["static","dynamic","dual","triple","tesla"].forEach(k => delete payload[`custom_rate_${k}`]);
      }
      const { data } = await api.post("/shops", payload);
      setCreated(data);
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to create shop");
    } finally { setSaving(false); }
  }

  if (created) {
    const url = `${window.location.origin}/book/${created.booking_link_token}`;
    return (
      <Shell>
        <div className="page-fade" style={{ maxWidth: 640 }}>
          <h1 className="h1" style={{ marginBottom: 8 }}>Shop Created ✓</h1>
          <div className="muted" style={{ marginBottom: 20 }}>Send this booking link to <b style={{ color: "var(--text-primary)" }}>{created.name}</b>:</div>
          <div className="surface" style={{ padding: 16, marginBottom: 16 }}>
            <div className="label">Public booking link</div>
            <div className="font-mono" style={{ fontSize: 13, padding: 10, background: "var(--bg-elevated)", borderRadius: 6, wordBreak: "break-all" }} data-testid="booking-link">
              {url}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="btn btn-primary" onClick={() => { navigator.clipboard.writeText(url); alert("Copied!"); }} data-testid="copy-booking-link">Copy Link</button>
              <a className="btn btn-ghost" href={url} target="_blank" rel="noreferrer" data-testid="open-booking-link">Open Booking Page →</a>
            </div>
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
          <Row>
            <Field label="Business name *">
              <input className="input" value={form.name} onChange={e => set("name", e.target.value)} data-testid="shop-name" />
            </Field>
            <Field label="Contact name">
              <input className="input" value={form.contact_name} onChange={e => set("contact_name", e.target.value)} data-testid="shop-contact-name" />
            </Field>
          </Row>
          <Row>
            <Field label="Contact phone">
              <input className="input" value={form.contact_phone} onChange={e => set("contact_phone", e.target.value)} data-testid="shop-contact-phone" />
            </Field>
            <Field label="Contact email">
              <input className="input" type="email" value={form.contact_email} onChange={e => set("contact_email", e.target.value)} data-testid="shop-contact-email" />
            </Field>
          </Row>
          <Field label="Service address *">
            <input className="input" value={form.address}
              onChange={e => set("address", e.target.value)} onBlur={detectZone}
              placeholder="e.g. 1234 E Williams Field Rd, Gilbert, AZ"
              data-testid="shop-address" />
            {zone && zone.in_metro && (
              <div style={{ marginTop: 6, fontSize: 13 }}>
                Zone detected: <span className={`badge badge-${zone.zone}`}>{zone.zone === "west" ? "West Valley" : "East Valley"}</span>
              </div>
            )}
            {zone && !zone.in_metro && <div style={{ color: "var(--red)", fontSize: 13, marginTop: 6 }}>Outside Phoenix metro service area.</div>}
          </Field>

          <Field label="Pricing tier">
            <div style={{ display: "flex", gap: 8 }}>
              {["standard","custom"].map(t => (
                <button key={t} className={"btn " + (form.pricing_tier === t ? "btn-primary" : "btn-ghost")}
                  onClick={() => set("pricing_tier", t)} data-testid={`tier-${t}`} type="button">
                  {t === "standard" ? "Standard" : "Custom rates"}
                </button>
              ))}
            </div>
          </Field>

          {form.pricing_tier === "custom" && (
            <div className="elevated" style={{ padding: 16, marginBottom: 16 }}>
              <div className="label">Custom rates (per calibration type)</div>
              <Row>
                <Field label="Static">
                  <input className="input" type="number" value={form.custom_rate_static} onChange={e => set("custom_rate_static", parseFloat(e.target.value))} />
                </Field>
                <Field label="Dynamic">
                  <input className="input" type="number" value={form.custom_rate_dynamic} onChange={e => set("custom_rate_dynamic", parseFloat(e.target.value))} />
                </Field>
              </Row>
              <Row>
                <Field label="Dual">
                  <input className="input" type="number" value={form.custom_rate_dual} onChange={e => set("custom_rate_dual", parseFloat(e.target.value))} />
                </Field>
                <Field label="Triple / Subaru">
                  <input className="input" type="number" value={form.custom_rate_triple} onChange={e => set("custom_rate_triple", parseFloat(e.target.value))} />
                </Field>
              </Row>
              <Field label="Tesla">
                <input className="input" type="number" value={form.custom_rate_tesla} onChange={e => set("custom_rate_tesla", parseFloat(e.target.value))} />
              </Field>
            </div>
          )}

          <Field label="Notes (internal)">
            <textarea className="input" rows={2} value={form.notes} onChange={e => set("notes", e.target.value)} />
          </Field>

          <hr className="divider" />

          {!showTerms ? (
            <button className="btn btn-primary" onClick={() => setShowTerms(true)}
              disabled={!form.name || !form.address || (zone && !zone.in_metro)}
              data-testid="continue-to-terms">Continue to Terms & Sign →</button>
          ) : (
            <div className="elevated" style={{ padding: 16 }} data-testid="terms-section">
              <div className="h3" style={{ marginBottom: 8 }}>Terms & Agreement</div>
              <div className="muted" style={{ fontSize: 13, maxHeight: 160, overflow: "auto", padding: 12,
                background: "var(--bg-primary)", borderRadius: 8, marginBottom: 12 }}>
                By signing below, the shop agrees to pay invoiced amounts within 30 days of invoice date.
                The Calibration Crew will deliver calibration documentation with each invoice. Cancellations
                under 4 hours notice may incur a $50 trip charge. All ADAS calibrations follow OEM specifications.
                Disputes must be raised within 7 days of completion.
              </div>
              <Field label="Type your full name to sign">
                <input className="input" value={signature} onChange={e => setSignature(e.target.value)} data-testid="terms-signature" />
              </Field>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, marginBottom: 14 }}>
                <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} data-testid="terms-agree" />
                I have read and agree to the Terms & Agreement.
              </label>
              <button className="btn btn-primary" disabled={!signature || !agreed || saving}
                onClick={save} data-testid="sign-and-create">
                {saving ? "Creating…" : "Sign & Create Shop"}
              </button>
            </div>
          )}
        </div>
      </div>
    </Shell>
  );
}

const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}>
    <label className="label">{label}</label>
    {children}
  </div>
);
