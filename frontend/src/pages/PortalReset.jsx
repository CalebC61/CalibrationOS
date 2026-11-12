import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { portalApi } from "../lib/portalApi";

export default function PortalReset() {
  const { token } = useParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    setBusy(true);
    try {
      await portalApi.post("/portal/auth/reset-password", { token, password });
      setDone(true);
    } catch (err) {
      setError(err.response?.data?.detail || "This reset link is not valid.");
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <form className="surface" style={{ padding: 28, width: "100%", maxWidth: 420 }} onSubmit={submit} data-testid="reset-form">
        <h1 className="h2" style={{ marginBottom: 12 }}>Choose a new password</h1>
        {done ? (
          <p>Password updated. <Link to="/portal/login">Sign in</Link></p>
        ) : (
          <>
            <label className="label">New password</label>
            <input className="input" type="password" required value={password} onChange={e => setPassword(e.target.value)} data-testid="reset-password" />
            {error && <div style={{ color: "var(--red)", marginTop: 12 }}>{error}</div>}
            <button className="btn btn-primary" style={{ width: "100%", marginTop: 16 }} disabled={busy}>Save password</button>
          </>
        )}
      </form>
    </div>
  );
}
