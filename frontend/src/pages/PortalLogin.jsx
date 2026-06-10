import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { portalApi, setPortalAuth } from "../lib/portalApi";

export default function PortalLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const { data } = await portalApi.post("/portal/auth/login", { email, password });
      setPortalAuth(data);
      nav("/portal");
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed");
    } finally { setLoading(false); }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ width: "100%", maxWidth: 420 }} className="page-fade">
        <div className="font-display" style={{ fontSize: 30, fontWeight: 800, textAlign: "center" }}>
          CALIBRATION<span style={{ color: "var(--accent)" }}>OS</span>
        </div>
        <div className="muted" style={{ textAlign: "center", fontSize: 12, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: 24 }}>
          Shop Portal
        </div>
        <form onSubmit={submit} className="surface" style={{ padding: 28 }} data-testid="portal-login-form">
          <div style={{ marginBottom: 14 }}>
            <label className="label">Email</label>
            <input className="input" type="email" required value={email}
              onChange={e => setEmail(e.target.value)} data-testid="portal-login-email" />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label className="label">Password</label>
            <input className="input" type="password" required value={password}
              onChange={e => setPassword(e.target.value)} data-testid="portal-login-password" />
          </div>
          {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }} data-testid="portal-login-error">{error}</div>}
          <button className="btn btn-primary" style={{ width: "100%" }} disabled={loading} data-testid="portal-login-submit">
            {loading ? "Signing in…" : "Sign In"}
          </button>
          <div className="muted" style={{ fontSize: 12, marginTop: 16, textAlign: "center" }}>
            New here? Your invitation email contains a registration link.
          </div>
        </form>
      </div>
    </div>
  );
}
