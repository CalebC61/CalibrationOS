import { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { portalApi, setPortalAuth, getPortalAuth } from "../lib/portalApi";

export default function PortalSetupReturn() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [status, setStatus] = useState("processing");
  const [details, setDetails] = useState(null);

  useEffect(() => {
    if (params.get("cancelled")) { setStatus("cancelled"); return; }
    const session = params.get("session_id");
    if (!session) { setStatus("missing"); return; }
    portalApi.get(`/portal/stripe-setup-status?session_id=${session}`)
      .then(r => {
        if (r.data.status === "complete") {
          const su = r.data.shop_user;
          setPortalAuth({
            token: getPortalAuth()?.token, full_name: su.full_name,
            shop_name: su.shop_name, shop_user_id: su.id, shop_id: su.shop_id,
            has_payment_method: true,
          });
          setDetails({ brand: su.card_brand, last4: su.card_last4 });
          setStatus("complete");
        } else {
          setStatus("incomplete");
        }
      })
      .catch(() => setStatus("error"));
  }, [params]);

  return (
    <Center>
      <div className="surface" style={{ padding: 30, maxWidth: 480, textAlign: "center" }} data-testid="setup-return">
        {status === "processing" && <div className="muted">Confirming card setup…</div>}
        {status === "complete" && (
          <>
            <div style={{ fontSize: 48, color: "var(--green)", marginBottom: 8 }}>✓</div>
            <div className="h2" style={{ marginBottom: 6 }}>Card on file</div>
            {details && <div className="muted" style={{ marginBottom: 20 }}>
              {details.brand?.toUpperCase()} ending in {details.last4}
            </div>}
            <Link to="/portal" className="btn btn-primary" style={{ width: "100%" }} data-testid="enter-portal">Enter Portal →</Link>
          </>
        )}
        {status === "cancelled" && (
          <>
            <div className="h2" style={{ marginBottom: 6 }}>Card setup cancelled</div>
            <div className="muted" style={{ marginBottom: 20 }}>You can add a card from Settings anytime.</div>
            <Link to="/portal" className="btn btn-ghost" style={{ width: "100%" }}>Continue to Portal</Link>
          </>
        )}
        {status === "error" && <div style={{ color: "var(--red)" }}>Could not verify card setup. Try again from Settings.</div>}
        {status === "missing" && <div className="muted">Invalid return URL.</div>}
      </div>
    </Center>
  );
}

const Center = ({ children }) => (
  <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>{children}</div>
);
