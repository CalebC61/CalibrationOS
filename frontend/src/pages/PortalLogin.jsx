import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { portalApi, setPortalAuth } from "../lib/portalApi";
import Brand from "../components/Brand";

export default function PortalLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const promptRegister = sp.get("register") === "1";

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
      <div style={{ width: "100%", maxWidth: 460 }} className="page-fade">
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <Brand size={28} tag="Shop Portal" />
        </div>

        {promptRegister && (
          <div className="elevated" style={{
            padding: 16, marginBottom: 16, borderLeft: "3px solid var(--accent)",
            background: "rgba(249,115,22,0.08)",
          }} data-testid="register-banner">
            <div style={{ fontWeight: 700, marginBottom: 4 }}>New to The Calibration Crew?</div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
              Bookings are now made through the shop portal. Register once and book all your calibrations from one place.
            </div>
            <Link to="/portal/register" className="btn btn-primary" style={{ display: "inline-block" }} data-testid="register-cta">
              Register your shop →
            </Link>
          </div>
        )}

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
            {promptRegister ? (
              <>Have an account? Just sign in above.</>
            ) : (
              <>New here? <Link to="/portal/register" style={{ color: "var(--accent)" }}>Register your shop</Link></>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
