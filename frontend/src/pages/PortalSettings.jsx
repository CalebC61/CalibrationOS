import { useEffect, useState } from "react";
import { portalApi, setPortalAuth, getPortalAuth } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";
import { CardSetup, ChargeAcceptance, CHARGE_ACCEPTANCE_FALLBACK } from "../components/CardSetup";

export default function PortalSettings() {
  const [me, setMe] = useState(null);
  const [clientSecret, setClientSecret] = useState("");
  const [cardError, setCardError] = useState("");
  const [needsAcceptance, setNeedsAcceptance] = useState(false);
  const [acceptance, setAcceptance] = useState(CHARGE_ACCEPTANCE_FALLBACK);
  const [accepting, setAccepting] = useState(false);

  function load() { return portalApi.get("/portal/me").then(r => setMe(r.data)); }
  useEffect(() => { load(); portalApi.get("/public/agreement").then(r => setAcceptance(r.data.acceptance)).catch(() => {}); }, []);

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
    if (!shopUser.charge_authorization_accepted_at) setNeedsAcceptance(true);
    else load();
  }

  async function accept() {
    setAccepting(true);
    try {
      await portalApi.post("/portal/accept-charge", { accepted: true });
      setNeedsAcceptance(false);
      load();
    } catch (err) {
      setCardError(err.response?.data?.detail || "Could not save that.");
    } finally {
      setAccepting(false);
    }
  }

  if (!me) return <PortalShell><div className="muted">Loading…</div></PortalShell>;
  const su = me.shop_user;

  return (
    <PortalShell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Settings</h1>
      <div className="surface" style={{ padding: 20, marginBottom: 16, maxWidth: 560 }}>
        <div className="h3" style={{ marginBottom: 12 }}>Account</div>
        <Row k="Name" v={su.full_name} />
        <Row k="Email" v={su.email} />
        <Row k="Shop" v={su.shop_name} />
      </div>

      <div className="surface" style={{ padding: 20, marginBottom: 16, maxWidth: 560 }} data-testid="payment-method-section">
        <div className="h3" style={{ marginBottom: 12 }}>Payment method</div>
        {su.stripe_payment_method_id ? (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: 12, background: "var(--bg-elevated)", borderRadius: 8 }}>
              <div>
                <div style={{ fontWeight: 600, textTransform: "uppercase" }}>{su.card_brand} •••• {su.card_last4}</div>
                <div className="muted" style={{ fontSize: 12 }}>Expires {String(su.card_exp_month).padStart(2,"0")}/{su.card_exp_year}</div>
              </div>
              <span className="badge badge-complete">Active</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>Charged when a job is completed, unless you asked to be invoiced.</div>
            <button className="btn btn-ghost" style={{ marginTop: 12 }} onClick={startCard} data-testid="add-card-btn">Replace card</button>
          </>
        ) : (
          <div>
            <div className="muted" style={{ marginBottom: 12 }}>No card on file yet.</div>
            <button className="btn btn-primary" onClick={startCard} data-testid="add-card-btn">Add card</button>
          </div>
        )}
        {cardError && <div style={{ color: "var(--red)", marginTop: 12 }}>{cardError}</div>}
        {clientSecret && (
          <div style={{ marginTop: 16 }} data-testid="card-setup">
            <CardSetup clientSecret={clientSecret} onSaved={cardSaved} />
          </div>
        )}
      </div>

      <div className="surface" style={{ padding: 20, maxWidth: 560 }}>
        <div className="h3" style={{ marginBottom: 12 }}>Terms agreement</div>
        <div className="muted" style={{ fontSize: 13 }}>
          {su.terms_signed_at ? (
            <>Signed by <b style={{ color: "var(--text-primary)" }}>{su.terms_signature}</b> on {new Date(su.terms_signed_at).toLocaleString()}.</>
          ) : "Not signed yet."}
          {su.charge_authorization_accepted_at && <div style={{ marginTop: 8 }}>Card charge accepted {new Date(su.charge_authorization_accepted_at).toLocaleString()}.</div>}
        </div>
      </div>
      {needsAcceptance && <ChargeAcceptance text={acceptance} busy={accepting} onAccept={accept} />}
    </PortalShell>
  );
}

const Row = ({ k, v }) => (
  <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
    <span className="muted">{k}</span><span style={{ fontWeight: 500 }}>{v}</span>
  </div>
);
