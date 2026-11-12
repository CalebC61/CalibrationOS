import { useState } from "react";
import { Link } from "react-router-dom";
import { portalApi } from "../lib/portalApi";

export default function PortalForgot() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const { data } = await portalApi.post("/portal/auth/forgot-password", { email });
      setMessage(data.message);
    } catch {
      setMessage("Could not send a reset link. Try again in a minute.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <form className="surface" style={{ padding: 28, width: "100%", maxWidth: 420 }} onSubmit={submit} data-testid="forgot-form">
        <h1 className="h2" style={{ marginBottom: 8 }}>Reset your password</h1>
        <p className="muted" style={{ marginBottom: 16 }}>We'll email a one-time link to the address on the account.</p>
        <label className="label">Email</label>
        <input className="input" type="email" required value={email} onChange={e => setEmail(e.target.value)} data-testid="forgot-email" />
        <button className="btn btn-primary" style={{ width: "100%", marginTop: 16 }} disabled={busy}>
          {busy ? "Sending…" : "Email me a link"}
        </button>
        {message && <p style={{ marginTop: 12 }} data-testid="forgot-message">{message}</p>}
        <p style={{ marginTop: 16 }}><Link to="/portal/login">Back to login</Link></p>
      </form>
    </div>
  );
}
