import { useEffect, useState } from "react";
import { portalApi, setPortalAuth, getPortalAuth } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";
import { CardSetup, CHARGE_ACCEPTANCE_FALLBACK } from "../components/CardSetup";
import AgreementView from "../components/AgreementView";

export default function PortalSettings() {
  const [me, setMe] = useState(null);
  const [clientSecret, setClientSecret] = useState("");
  const [cardError, setCardError] = useState("");
  const [termsError, setTermsError] = useState("");
  const [needsAcceptance, setNeedsAcceptance] = useState(false);
  const [acceptance, setAcceptance] = useState(CHARGE_ACCEPTANCE_FALLBACK);
  const [accepting, setAccepting] = useState(false);
  const [agreement, setAgreement] = useState(null);
  const [cardNote, setCardNote] = useState("");

  function load() {
    return portalApi.get("/portal/me").then(r => {
      setMe(r.data);
      if (r.data.setup?.accepted) setNeedsAcceptance(false);
    });
  }
  useEffect(() => {
    load();
    portalApi.get("/public/agreement").then(r => {
      if (r.data.acceptance) setAcceptance(r.data.acceptance);
      setAgreement(r.data);
    }).catch(() => {});
  }, []);

  async function startCard() {
    setCardError("");
    try {
      const { data } = await portalApi.post("/portal/setup-intent");
      setClientSecret(data.client_secret);
    } catch (err) {
      setCardError(err.response?.data?.detail || "Could not start card setup.");
    }
  }

  function cardSaved(shopUser) {
    const auth = getPortalAuth();
    if (auth) setPortalAuth({ ...auth, has_payment_method: true });
    setClientSecret("");
    setMe(prev => prev ? { ...prev, shop_user: shopUser } : prev);
    const brand = shopUser.card_brand ? String(shopUser.card_brand) : "Card";
    const last4 = shopUser.card_last4 || "";
    setCardNote(`${brand} ending in ${last4} is now the card on file. New charges use this card.`);
    if (!shopUser.charge_authorization_accepted_at) setNeedsAcceptance(true);
    load();
  }

  async function accept() {
    setAccepting(true);
    setTermsError("");
    try {
      await portalApi.post("/portal/accept-charge", { accepted: true });
      setNeedsAcceptance(false);
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setTermsError(typeof detail === "string" ? detail : "Could not save that.");
    } finally {
      setAccepting(false);
    }
  }

  if (!me) return <PortalShell><div className="muted">Loading…</div></PortalShell>;
  const su = me.shop_user;
  const setup = me.setup || {};
  const showChargeTerms = !setup.accepted && !setup.suspended && !setup.charge_failed && (
    (setup.has_card && setup.signed) || needsAcceptance
  );

  return (
    <PortalShell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Account</h1>
      <div className="surface" style={{ padding: 20, marginBottom: 16, maxWidth: 560 }}>
        <Row k="Name" v={su.full_name} />
        <Row k="Email" v={su.email} />
        <Row k="Shop" v={su.shop_name} />
        <Row k="Address" v={me.shop?.address || "—"} testId="shop-address" />
        {me.shop?.zone && <Row k="Area" v={valleyName(me.shop.zone)} testId="shop-zone" />}
      </div>

      <div className="surface" style={{ padding: 20, marginBottom: 16, maxWidth: 560 }} data-testid="payment-method-section">
        <div className="h3" style={{ marginBottom: 12 }}>Payment method</div>
        {su.has_payment_method ? (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", padding: 12, background: "var(--bg-elevated)", borderRadius: 8 }}>
              <div>
                <div style={{ fontWeight: 600, textTransform: "uppercase" }}>{su.card_brand} •••• {su.card_last4}</div>
                <div className="muted" style={{ fontSize: 12 }}>Expires {String(su.card_exp_month).padStart(2,"0")}/{su.card_exp_year}</div>
              </div>
              <span className="badge badge-complete">Active</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>Charged when a job is completed, unless you asked to be invoiced. Jobs still waiting to be invoiced use this card too.</div>
            <button className="btn btn-ghost" style={{ marginTop: 12 }} onClick={startCard} data-testid="update-card-btn">Update card</button>
          </>
        ) : (
          <div>
            <div className="muted" style={{ marginBottom: 12 }}>No card on file yet.</div>
            <button className="btn btn-primary" onClick={startCard} data-testid="add-card-btn">Add card</button>
          </div>
        )}
        {cardNote && <p role="status" data-testid="card-updated" style={{ marginTop: 12, color: "var(--green)" }}>{cardNote}</p>}
        {cardError && <div style={{ color: "var(--red)", marginTop: 12 }}>{cardError}</div>}
        {clientSecret && (
          <div style={{ marginTop: 16 }} data-testid="card-setup">
            <CardSetup clientSecret={clientSecret} onSaved={cardSaved} />
            <button type="button" className="btn btn-ghost" style={{ marginTop: 12 }}
              onClick={() => { setClientSecret(""); setCardError(""); }}
              data-testid="cancel-card-update">
              Cancel
            </button>
          </div>
        )}
      </div>

      {showChargeTerms && (
        <div className="surface" style={{ padding: 20, marginBottom: 16, maxWidth: 640 }} data-testid="charge-terms">
          <h2 className="h2" style={{ fontSize: "1.35rem", marginBottom: 12 }}>Charge terms</h2>
          <p style={{ lineHeight: 1.55, margin: "0 0 16px" }}>{acceptance}</p>
          <button className="btn btn-primary" type="button" disabled={accepting} onClick={accept} data-testid="accept-charge-terms">
            {accepting ? "Saving…" : "I accept the charge terms"}
          </button>
          {termsError && <div style={{ color: "var(--red)", marginTop: 12 }}>{termsError}</div>}
        </div>
      )}

      <div className="surface" style={{ padding: 20, maxWidth: 640 }}>
        <h2 className="h2" style={{ fontSize: "1.35rem", marginBottom: 12 }}>Service agreement</h2>
        <AgreementView sections={agreement?.sections} paragraphs={agreement?.paragraphs} />
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
          {su.terms_signed_at ? (
            <>Signed by <b style={{ color: "var(--text-primary)" }}>{su.terms_signature}</b> on {new Date(su.terms_signed_at).toLocaleString()}.</>
          ) : "Not signed yet."}
          {su.charge_authorization_accepted_at && <div style={{ marginTop: 8 }}>Card charge accepted {new Date(su.charge_authorization_accepted_at).toLocaleString()}.</div>}
        </div>
      </div>
    </PortalShell>
  );
}

function valleyName(zone) {
  if (zone === "west") return "West Valley";
  if (zone === "east") return "East Valley";
  return zone;
}

const Row = ({ k, v, testId }) => (
  <div className="portal-kv">
    <span className="muted">{k}</span><span style={{ fontWeight: 500 }} data-testid={testId}>{v}</span>
  </div>
);
