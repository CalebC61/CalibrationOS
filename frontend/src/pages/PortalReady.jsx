import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { portalApi } from "../lib/portalApi";

export default function PortalReady() {
  const [shop, setShop] = useState(null);
  useEffect(() => { portalApi.get("/portal/me").then(r => setShop(r.data.shop)); }, []);
  const link = shop ? `${window.location.origin}/book/${shop.booking_link_token}` : "";
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div className="surface" style={{ padding: 28, maxWidth: 520 }} data-testid="ready-screen">
        <h1 className="h1" style={{ marginBottom: 8 }}>You're all set</h1>
        <p className="muted" style={{ marginBottom: 16 }}>The agreement is signed and the card is saved. Book from the link below, or from the portal.</p>
        {link && <div className="font-mono" style={{ fontSize: 13, wordBreak: "break-all", marginBottom: 16 }} data-testid="ready-booking-link">{link}</div>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="btn btn-primary" to="/portal/book" data-testid="ready-book">Book a job</Link>
          <Link className="btn btn-ghost" to="/portal">Go to the portal</Link>
        </div>
      </div>
    </div>
  );
}
