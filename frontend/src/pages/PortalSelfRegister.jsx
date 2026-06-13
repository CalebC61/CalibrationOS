import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { portalApi, setPortalAuth } from "../lib/portalApi";
import Brand from "../components/Brand";

const STEPS = [
  { n: 1, label: "Business Info" },
  { n: 2, label: "Terms & Signature" },
  { n: 3, label: "Card on File" },
];

export default function PortalSelfRegister() {
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [biz, setBiz] = useState({
    shop_legal_name: "", shop_display_name: "", contact_full_name: "",
    email: "", password: "", confirm: "",
    contact_phone: "", shop_address: "", shop_city: "", shop_state: "AZ", shop_zip: "",
  });
  const [terms, setTerms] = useState(null);
  const [scrolledToBottom, setScrolledToBottom] = useState(false);
  const [signature, setSignature] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [stripeCheckoutUrl, setStripeCheckoutUrl] = useState(null);
  const termsScrollRef = useRef(null);

  useEffect(() => {
    portalApi.get("/portal/terms/current").then(r => setTerms(r.data));
  }, []);

  function handleTermsScroll() {
    const el = termsScrollRef.current;
    if (!el) return;
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (remaining < 8) setScrolledToBottom(true);
  }

  // STEP 1 — Business Info → submit creates account & stores Stripe checkout URL
  async function submitBiz(e) {
    e?.preventDefault();
    setError("");
    if (biz.password.length < 8) return setError("Password must be at least 8 characters");
    if (biz.password !== biz.confirm) return setError("Passwords don't match");
    if (!biz.shop_address.trim()) return setError("Shop address is required");
    setSubmitting(true);
    try {
      const { data } = await portalApi.post("/portal/self-register", {
        shop_legal_name: biz.shop_legal_name,
        shop_display_name: biz.shop_display_name,
        contact_full_name: biz.contact_full_name,
        email: biz.email, password: biz.password,
        contact_phone: biz.contact_phone,
        shop_address: biz.shop_address, shop_city: biz.shop_city,
        shop_state: biz.shop_state, shop_zip: biz.shop_zip,
      });
      setPortalAuth({
        token: data.token, full_name: biz.contact_full_name,
        shop_name: biz.shop_display_name, shop_user_id: data.shop_user_id,
        shop_id: data.shop_id, has_payment_method: false,
      });
      setStripeCheckoutUrl(data.stripe_checkout_url);
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  // STEP 2 — Sign T&A
  async function submitTerms() {
    setError("");
    if (!scrolledToBottom) return setError("Please scroll to the end of the Terms to continue");
    if (!agreed) return setError("You must check the agreement box");
    if (!signature.trim()) return setError("Please type your full legal name as your signature");
    setSubmitting(true);
    try {
      await portalApi.post("/portal/accept-terms", {
        terms_version: terms.version,
        signature_full_name: signature.trim(),
      });
      setStep(3);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not record signature");
    } finally {
      setSubmitting(false);
    }
  }

  // STEP 3 — Stripe Checkout
  function goToStripe() {
    if (!stripeCheckoutUrl) {
      setError("Stripe is unavailable — please contact support to add a card");
      return;
    }
    window.location.href = stripeCheckoutUrl;
  }

  if (!terms) return <Center><div className="muted">Loading…</div></Center>;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", padding: "32px 16px" }}>
      <div style={{ maxWidth: 640, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 6 }}>
          <Brand size={28} />
        </div>
        <div className="muted" style={{ textAlign: "center", fontSize: 12, letterSpacing: "0.16em",
             textTransform: "uppercase", marginBottom: 18 }}>Register your shop</div>

        {/* Stepper */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 24, gap: 8 }}>
          {STEPS.map(s => (
            <div key={s.n} style={{ flex: 1, opacity: step >= s.n ? 1 : 0.4 }} data-testid={`step-indicator-${s.n}`}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{
                  width: 26, height: 26, borderRadius: "50%",
                  background: step > s.n ? "var(--green)" : step === s.n ? "var(--accent)" : "var(--border)",
                  color: "white", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 13, fontWeight: 700,
                }}>{step > s.n ? "✓" : s.n}</div>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{s.label}</div>
              </div>
              {s.n < STEPS.length && (
                <div style={{ height: 2, background: step > s.n ? "var(--green)" : "var(--border)",
                              marginTop: 6, marginLeft: 13 }} />
              )}
            </div>
          ))}
        </div>

        {/* STEP 1 — Business Info */}
        {step === 1 && (
          <form className="surface" style={{ padding: 28 }} onSubmit={submitBiz} data-testid="step-1-form">
            <h2 className="h2" style={{ marginBottom: 4 }}>Business Information</h2>
            <div className="muted" style={{ fontSize: 13, marginBottom: 20 }}>
              This becomes your shop&apos;s record in our system.
            </div>

            <Row>
              <Field label="Legal business name *">
                <input className="input" required value={biz.shop_legal_name}
                  onChange={e => setBiz({...biz, shop_legal_name: e.target.value})}
                  data-testid="reg-legal-name" />
              </Field>
              <Field label="Display name *">
                <input className="input" required value={biz.shop_display_name}
                  onChange={e => setBiz({...biz, shop_display_name: e.target.value})}
                  data-testid="reg-display-name" placeholder="What we'll show on bookings" />
              </Field>
            </Row>
            <Field label="Primary contact full name *">
              <input className="input" required value={biz.contact_full_name}
                onChange={e => setBiz({...biz, contact_full_name: e.target.value})}
                data-testid="reg-contact-name" />
            </Field>
            <Row>
              <Field label="Email (your login) *">
                <input className="input" required type="email" value={biz.email}
                  onChange={e => setBiz({...biz, email: e.target.value})}
                  data-testid="reg-email" />
              </Field>
              <Field label="Phone *">
                <input className="input" required value={biz.contact_phone}
                  onChange={e => setBiz({...biz, contact_phone: e.target.value})}
                  placeholder="+14805551234" data-testid="reg-phone" />
              </Field>
            </Row>
            <Row>
              <Field label="Password (min 8) *">
                <input className="input" required type="password" value={biz.password}
                  onChange={e => setBiz({...biz, password: e.target.value})}
                  data-testid="reg-password" />
              </Field>
              <Field label="Confirm password *">
                <input className="input" required type="password" value={biz.confirm}
                  onChange={e => setBiz({...biz, confirm: e.target.value})}
                  data-testid="reg-confirm" />
              </Field>
            </Row>
            <Field label="Shop physical address *">
              <input className="input" required value={biz.shop_address}
                onChange={e => setBiz({...biz, shop_address: e.target.value})}
                placeholder="1234 W Bell Rd" data-testid="reg-address" />
            </Field>
            <Row>
              <Field label="City">
                <input className="input" value={biz.shop_city}
                  onChange={e => setBiz({...biz, shop_city: e.target.value})}
                  data-testid="reg-city" />
              </Field>
              <Field label="State">
                <input className="input" value={biz.shop_state}
                  onChange={e => setBiz({...biz, shop_state: e.target.value})}
                  data-testid="reg-state" />
              </Field>
              <Field label="ZIP">
                <input className="input" value={biz.shop_zip}
                  onChange={e => setBiz({...biz, shop_zip: e.target.value})}
                  data-testid="reg-zip" />
              </Field>
            </Row>

            {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }} data-testid="reg-error">{error}</div>}
            <button className="btn btn-primary" disabled={submitting} type="submit"
              style={{ width: "100%", padding: 12 }} data-testid="reg-step1-submit">
              {submitting ? "Creating account…" : "Continue to Terms →"}
            </button>
            <div className="muted" style={{ fontSize: 12, marginTop: 12, textAlign: "center" }}>
              Already registered? <a href="/portal/login" style={{ color: "var(--accent)" }}>Sign in</a>
            </div>
          </form>
        )}

        {/* STEP 2 — Terms */}
        {step === 2 && (
          <div className="surface" style={{ padding: 28 }} data-testid="step-2-form">
            <h2 className="h2" style={{ marginBottom: 4 }}>Terms & Agreement</h2>
            <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
              Version {terms.version} · Effective {terms.effective_date}. Scroll to the bottom to enable signing.
            </div>

            <div ref={termsScrollRef} onScroll={handleTermsScroll}
              className="elevated"
              style={{
                padding: 18, maxHeight: 360, overflow: "auto",
                fontSize: 13, lineHeight: 1.65, fontFamily: "var(--font-mono)",
                whiteSpace: "pre-wrap", marginBottom: 14,
              }} data-testid="terms-scroll">
              {terms.content}
            </div>

            <div className="muted" style={{ fontSize: 12, marginBottom: 16, color: scrolledToBottom ? "var(--green)" : "var(--yellow)" }}
                 data-testid="scroll-status">
              {scrolledToBottom ? "✓ You've read to the end. You may sign below." : "↓ Please scroll to the end of the document to continue."}
            </div>

            <Field label="Type your full legal name as your signature *">
              <input className="input" value={signature} disabled={!scrolledToBottom}
                onChange={e => setSignature(e.target.value)}
                style={{ fontFamily: "var(--font-display)", fontSize: 18 }}
                data-testid="reg-signature" />
            </Field>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 14, marginBottom: 16, opacity: scrolledToBottom ? 1 : 0.5 }}>
              <input type="checkbox" checked={agreed} disabled={!scrolledToBottom}
                onChange={e => setAgreed(e.target.checked)}
                style={{ marginTop: 3 }} data-testid="reg-agree" />
              <span>I am authorized to bind {biz.shop_display_name} to this Agreement and accept the
                card-on-file authorization described in §3.</span>
            </label>

            {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }} data-testid="terms-error">{error}</div>}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost" onClick={() => setStep(1)} data-testid="terms-back">← Back</button>
              <button className="btn btn-primary" onClick={submitTerms}
                disabled={!scrolledToBottom || !agreed || !signature.trim() || submitting}
                style={{ flex: 1, padding: 12 }} data-testid="reg-step2-submit">
                {submitting ? "Recording signature…" : "I Agree — Continue to Card Setup →"}
              </button>
            </div>
          </div>
        )}

        {/* STEP 3 — Card on File */}
        {step === 3 && (
          <div className="surface" style={{ padding: 28, textAlign: "center" }} data-testid="step-3-form">
            <h2 className="h2" style={{ marginBottom: 8 }}>Save Card on File</h2>
            <div className="muted" style={{ fontSize: 14, marginBottom: 20 }}>
              Final step. We&apos;ll redirect you to Stripe to securely save your card.
              No charge today — charges only occur after a completed calibration.
            </div>
            <div className="elevated" style={{ padding: 16, marginBottom: 18, fontSize: 13, textAlign: "left" }}>
              <ul style={{ paddingLeft: 18, margin: 0, lineHeight: 1.8 }}>
                <li>Card data is held by <b>Stripe</b>, never by The Calibration Crew.</li>
                <li>Bookings within 7 days will place a small pre-authorization hold; the actual charge occurs only when the calibration is completed.</li>
                <li>Bookings further out validate the card and charge upon completion.</li>
              </ul>
            </div>

            {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }} data-testid="card-error">{error}</div>}

            <button className="btn btn-primary" onClick={goToStripe}
              style={{ width: "100%", padding: 14 }} data-testid="reg-step3-stripe">
              Continue to Stripe →
            </button>
            <div className="muted" style={{ fontSize: 11, marginTop: 14 }}>
              Your account stays in <b>pending</b> status until the card is saved.
              You can also <a href="#" onClick={(e) => { e.preventDefault(); nav("/portal"); }}
                style={{ color: "var(--accent)" }}>finish this later</a> from your portal.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const Center = ({ children }) => (
  <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex",
                alignItems: "center", justifyContent: "center", padding: 16 }}>{children}</div>
);
const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>
);
const Row = ({ children }) => (
  <div style={{ display: "grid",
                gridTemplateColumns: `repeat(${typeof children?.length === "number" ? children.length : 2}, 1fr)`,
                gap: 12 }}>{children}</div>
);
