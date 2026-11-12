import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { portalApi, setPortalAuth } from "../lib/portalApi";
import Brand from "../components/Brand";
import { CardSetup, ChargeAcceptance, CHARGE_ACCEPTANCE_FALLBACK } from "../components/CardSetup";

export default function PortalRegister() {
  const { token } = useParams();
  const nav = useNavigate();
  const [invite, setInvite] = useState(null);
  const [linkProblem, setLinkProblem] = useState(null);
  const [ownerPhone, setOwnerPhone] = useState("");
  const [form, setForm] = useState({ full_name: "", password: "", confirm: "" });
  const [signature, setSignature] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [setupSecret, setSetupSecret] = useState("");
  const [checkoutUrl, setCheckoutUrl] = useState("");
  const [needsAcceptance, setNeedsAcceptance] = useState(false);
  const [acceptanceText, setAcceptanceText] = useState(CHARGE_ACCEPTANCE_FALLBACK);
  const [accepting, setAccepting] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [requestNote, setRequestNote] = useState("");

  useEffect(() => {
    portalApi.get("/public/site").then(r => setOwnerPhone(r.data.owner_phone || "")).catch(() => {});
    portalApi.get("/public/agreement").then(r => {
      if (r.data.acceptance) setAcceptanceText(r.data.acceptance);
    }).catch(() => {});
    portalApi.get(`/public/invites/${token}`)
      .then(r => setInvite(r.data))
      .catch(e => {
        const detail = e.response?.data?.detail;
        if (detail && typeof detail === "object") setLinkProblem(detail);
        else setLinkProblem({ code: "missing", message: detail || "This link is not valid." });
      });
  }, [token]);

  async function requestNew() {
    setRequesting(true);
    setRequestNote("");
    try {
      const { data } = await portalApi.post(`/public/invites/${token}/request-new`);
      setRequestNote(data.message || "A new link is on the way.");
    } catch (err) {
      const detail = err.response?.data?.detail;
      setRequestNote(typeof detail === "string" ? detail : (detail?.message || "We could not email a new link."));
      if (detail?.owner_phone) setOwnerPhone(detail.owner_phone);
    } finally {
      setRequesting(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (form.password !== form.confirm) return setError("Passwords don't match");
    if (form.password.length < 8) return setError("Password must be at least 8 characters");
    if (!agreed || !signature.trim()) return setError("Sign the agreement to continue");
    setSubmitting(true);
    try {
      const { data } = await portalApi.post(`/public/invites/${token}/register`, {
        invite_token: token,
        full_name: form.full_name,
        password: form.password,
        terms_signature: signature,
        terms_agreed: true,
      });
      setPortalAuth({
        token: data.token, full_name: form.full_name, shop_name: invite.shop_name,
        shop_user_id: data.shop_user_id, shop_id: invite.shop_id, has_payment_method: false,
      });
      if (data.stripe_unavailable) {
        setError(data.stripe_error || "Card setup is not available yet. Caleb has your account.");
        setSubmitting(false);
        return;
      }
      setSetupSecret(data.stripe_client_secret || "");
      setCheckoutUrl(data.stripe_checkout_url || "");
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : (detail?.message || "Registration failed"));
      setSubmitting(false);
    }
  }

  async function accept() {
    setAccepting(true);
    try {
      await portalApi.post("/portal/accept-charge", { accepted: true });
      nav("/portal/ready");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save that.");
      setAccepting(false);
    }
  }

  if (linkProblem) {
    return (
      <Center>
        <div className="surface" style={{ padding: 28, maxWidth: 460 }} data-testid="invite-invalid">
          <div className="h2">This link won't open</div>
          <p className="muted" style={{ marginTop: 8 }}>{linkProblem.message}</p>
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 16 }} onClick={requestNew} disabled={requesting} data-testid="request-new-link">
            {requesting ? "Sending…" : "Request a new link"}
          </button>
          {requestNote && <p style={{ marginTop: 12 }}>{requestNote}</p>}
          {ownerPhone && <p className="muted" style={{ marginTop: 12 }}>Or call {ownerPhone}.</p>}
          <p style={{ marginTop: 12 }}><Link to="/portal/login">Shop login</Link></p>
        </div>
      </Center>
    );
  }
  if (!invite) return <Center><div className="muted">Loading…</div></Center>;

  const paragraphs = invite.agreement_paragraphs || [];

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", padding: "32px 16px" }}>
      <div style={{ maxWidth: 560, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 8 }}><Brand size={28} /></div>
        <div style={{ textAlign: "center", marginBottom: 20 }}>Set up <b>{invite.shop_name}</b></div>
        {!setupSecret && !checkoutUrl ? (
          <form className="surface" style={{ padding: 24 }} onSubmit={submit} data-testid="register-form">
            <Field label="Your name *">
              <input className="input" required value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} data-testid="reg-name" />
            </Field>
            <Field label="Email">
              <input className="input" value={invite.recipient_email} disabled />
            </Field>
            <Field label="Password (at least 8 characters) *">
              <input className="input" type="password" required value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} data-testid="reg-password" />
            </Field>
            <Field label="Confirm password *">
              <input className="input" type="password" required value={form.confirm} onChange={e => setForm({ ...form, confirm: e.target.value })} data-testid="reg-confirm" />
            </Field>
            <div className="elevated" style={{ padding: 14, marginBottom: 16, fontSize: 14, lineHeight: 1.6 }} data-testid="terms-text">
              {paragraphs.map(paragraph => <p key={paragraph} style={{ marginBottom: 10 }}>{paragraph}</p>)}
            </div>
            <Field label="Type your name to sign *">
              <input className="input" value={signature} onChange={e => setSignature(e.target.value)} data-testid="reg-signature" />
            </Field>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 16 }}>
              <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} data-testid="reg-agree" />
              <span>I have read this and I am signing for the shop.</span>
            </label>
            {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }} data-testid="reg-error">{error}</div>}
            <button className="btn btn-primary" style={{ width: "100%" }} disabled={submitting} data-testid="reg-submit">
              {submitting ? "Saving…" : "Continue to card"}
            </button>
          </form>
        ) : (
          <div className="surface" style={{ padding: 24 }} data-testid="card-step">
            <h2 className="h3" style={{ marginBottom: 8 }}>Save a card</h2>
            <p className="muted" style={{ marginBottom: 16 }}>No charge today. The card is used after a job is completed, unless you asked to be invoiced.</p>
            {setupSecret ? (
              <CardSetup clientSecret={setupSecret} onSaved={() => setNeedsAcceptance(true)} />
            ) : (
              <a className="btn btn-primary" href={checkoutUrl}>Continue in Stripe</a>
            )}
            {error && <div style={{ color: "var(--red)", marginTop: 12 }}>{error}</div>}
          </div>
        )}
      </div>
      {needsAcceptance && <ChargeAcceptance text={acceptanceText} busy={accepting} onAccept={accept} />}
    </div>
  );
}

const Center = ({ children }) => (
  <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>{children}</div>
);
const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>
);
