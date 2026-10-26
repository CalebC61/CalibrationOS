import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { portalApi, setPortalAuth } from "../lib/portalApi";
import Brand from "../components/Brand";

export default function PortalRegister() {
  const { token } = useParams();
  const nav = useNavigate();
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ full_name: "", password: "", confirm: "" });
  const [signature, setSignature] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    portalApi.get(`/public/invites/${token}`)
      .then(r => setInvite(r.data))
      .catch(e => setError(e.response?.data?.detail || "Invitation invalid"));
  }, [token]);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (form.password !== form.confirm) return setError("Passwords don't match");
    if (form.password.length < 8) return setError("Password must be at least 8 characters");
    if (!agreed) return setError("You must agree to the terms");
    if (!signature.trim()) return setError("Please sign by typing your full name");
    setSubmitting(true);
    try {
      const { data } = await portalApi.post(`/public/invites/${token}/register`, {
        invite_token: token, full_name: form.full_name, password: form.password,
        terms_signature: signature, terms_agreed: true,
        origin: window.location.origin,
      });
      setPortalAuth({
        token: data.token, full_name: form.full_name, shop_name: invite.shop_name,
        shop_user_id: data.shop_user_id, shop_id: invite.shop_id, has_payment_method: false,
      });
      if (data.stripe_checkout_url) {
        // Redirect to Stripe for card capture
        window.location.href = data.stripe_checkout_url;
      } else {
        // Stripe unavailable — skip card setup, go to portal with banner
        nav("/portal");
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed");
      setSubmitting(false);
    }
  }

  if (error && !invite) return <Center><div className="surface" style={{ padding: 28, maxWidth: 460, textAlign: "center" }}>
    <div className="h2">Link not valid</div>
    <div className="muted" style={{ marginTop: 8 }}>{error}</div>
  </div></Center>;
  if (!invite) return <Center><div className="muted">Loading…</div></Center>;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", padding: "32px 16px" }}>
      <div style={{ maxWidth: 560, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 6 }}>
          <Brand size={28} />
        </div>
        <div className="muted" style={{ textAlign: "center", fontSize: 12, marginBottom: 8 }}>Shop Portal Registration</div>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          Welcome, <b>{invite.shop_name}</b>
        </div>
        <form className="surface" style={{ padding: 28 }} onSubmit={submit} data-testid="register-form">
          <Field label="Full name *">
            <input className="input" required value={form.full_name}
              onChange={e => setForm({...form, full_name: e.target.value})} data-testid="reg-name" />
          </Field>
          <Field label="Email">
            <input className="input" value={invite.recipient_email} disabled style={{ opacity: 0.7 }} />
          </Field>
          <Field label="Password (min 8 chars) *">
            <input className="input" type="password" required value={form.password}
              onChange={e => setForm({...form, password: e.target.value})} data-testid="reg-password" />
          </Field>
          <Field label="Confirm password *">
            <input className="input" type="password" required value={form.confirm}
              onChange={e => setForm({...form, confirm: e.target.value})} data-testid="reg-confirm" />
          </Field>

          <div className="elevated" style={{ padding: 14, marginBottom: 16, maxHeight: 200, overflow: "auto", fontSize: 13, lineHeight: 1.6 }} data-testid="terms-text">
            <b>Terms & Agreement — Shop Portal</b>
            <ol style={{ paddingLeft: 18 }}>
              <li><b>Card on file:</b> A valid credit card must be kept on file at all times. By signing below, you authorize The Calibration Crew to charge this card for completed calibrations within the same business day.</li>
              <li><b>Pricing:</b> Charges follow your shop's agreed rate card. Custom rates are visible in your portal.</li>
              <li><b>Documentation:</b> Recalibration documents are uploaded to your portal within 24 hours of completion.</li>
              <li><b>Cancellation:</b> Cancellations made less than 4 hours before the scheduled start may incur a $50 trip charge.</li>
              <li><b>Disputes:</b> All disputes must be raised within 7 days of the charge date.</li>
              <li><b>Service area:</b> Services are limited to the Phoenix metro service zones unless otherwise agreed in writing.</li>
            </ol>
          </div>
          <Field label="Type your full legal name to sign *">
            <input className="input" value={signature} onChange={e => setSignature(e.target.value)} data-testid="reg-signature" />
          </Field>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 14, marginBottom: 16 }}>
            <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} style={{ marginTop: 3 }} data-testid="reg-agree" />
            <span>I have read and agree to the Terms & Agreement, including the card-on-file authorization.</span>
          </label>
          {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }} data-testid="reg-error">{error}</div>}
          <button className="btn btn-primary" style={{ width: "100%", padding: 12 }} disabled={submitting} data-testid="reg-submit">
            {submitting ? "Creating account…" : "Continue to Card Setup →"}
          </button>
          <div className="muted" style={{ fontSize: 12, marginTop: 12, textAlign: "center" }}>
            Next: Stripe will securely collect your card details. No charge during signup.
          </div>
        </form>
      </div>
    </div>
  );
}

const Center = ({ children }) => (
  <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>{children}</div>
);
const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>
);
