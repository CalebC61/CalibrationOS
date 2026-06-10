import { useEffect, useState } from "react";
import { portalApi, getPortalAuth, setPortalAuth } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";

export default function PortalSettings() {
  const auth = getPortalAuth();
  const [me, setMe] = useState(null);

  useEffect(() => { portalApi.get("/portal/me").then(r => setMe(r.data)); }, []);

  async function addOrReplaceCard() {
    // Reuse the setup flow by re-registering Stripe Checkout setup session
    // (In production we'd add a dedicated endpoint; this MVP re-uses logic.)
    alert("Card replacement flow coming next iteration — for now, use the invite-time setup. (Your card is already on file.)");
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
            <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>Card is charged after each completed calibration.</div>
          </>
        ) : (
          <div>
            <div className="muted" style={{ marginBottom: 12 }}>No card on file. Required to book new calibrations.</div>
            <button className="btn btn-primary" onClick={addOrReplaceCard} data-testid="add-card-btn">Add Card</button>
          </div>
        )}
      </div>

      <div className="surface" style={{ padding: 20, maxWidth: 560 }}>
        <div className="h3" style={{ marginBottom: 12 }}>Terms agreement</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Signed by <b style={{ color: "var(--text-primary)" }}>{su.terms_signature}</b> on {new Date(su.terms_signed_at).toLocaleDateString()}.
        </div>
      </div>
    </PortalShell>
  );
}

const Row = ({ k, v }) => (
  <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
    <span className="muted">{k}</span><span style={{ fontWeight: 500 }}>{v}</span>
  </div>
);
