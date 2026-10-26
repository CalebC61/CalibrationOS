import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, setStoredAuth } from "../lib/api";
import Brand from "../components/Brand";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const nav = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      setStoredAuth(data);
      nav(data.role === "owner" ? "/dashboard" : "/field");
    } catch (e) {
      setErr(e.response?.data?.detail || "Login failed");
    } finally { setLoading(false); }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ background: "var(--bg-primary)" }}>
      <div className="w-full max-w-md page-fade">
        <div className="mb-8 text-center">
          <Brand size={32} />
          <div className="muted" style={{ marginTop: 12, fontSize: 14 }}>
            Mobile ADAS calibration for Phoenix Valley glass shops
          </div>
        </div>
        <form onSubmit={submit} className="surface" style={{ padding: 28 }} data-testid="login-form">
          <div style={{ marginBottom: 18 }}>
            <label className="label">Email</label>
            <input className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)}
              required data-testid="login-email" />
          </div>
          <div style={{ marginBottom: 18 }}>
            <label className="label">Password</label>
            <input className="input" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}
              required data-testid="login-password" />
          </div>
          {err && <div style={{ color: "var(--red)", fontSize: 14, marginBottom: 14 }} data-testid="login-error">{err}</div>}
          <button className="btn btn-primary" style={{ width: "100%" }} disabled={loading} data-testid="login-submit">
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
