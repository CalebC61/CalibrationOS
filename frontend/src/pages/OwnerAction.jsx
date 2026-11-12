import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, formatDate, formatTime } from "../lib/api";
import Brand from "../components/Brand";

export default function OwnerAction() {
  const { token } = useParams();
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get(`/public/owner-action/${token}`)
      .then(response => { if (!cancelled) setPreview(response.data); })
      .catch(e => {
        if (cancelled) return;
        const detail = e.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "This link is not valid.");
      });
    return () => { cancelled = true; };
  }, [token]);

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/public/owner-action/${token}`);
      setResult(data.message || "Done.");
      if (data.job) setPreview(current => ({ ...(current || {}), job: data.job }));
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "This link could not be used.");
    } finally {
      setBusy(false);
    }
  }

  const job = preview?.job;
  const approving = preview?.action === "approve";

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg-primary)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }}>
      <div className="surface" style={{ padding: 28, maxWidth: 520, width: "100%" }} data-testid="owner-action">
        <div style={{ marginBottom: 16 }}><Brand size={22} /></div>
        <h1 className="h2" style={{ marginBottom: 8 }}>
          {approving ? "Approve this job?" : preview ? "Decline this job?" : "Owner link"}
        </h1>
        {error && <div role="alert" style={{ color: "var(--red)", marginBottom: 12 }} data-testid="owner-action-error">{error}</div>}
        {!preview && !error && <div className="muted">Loading…</div>}
        {job && (
          <div style={{ fontSize: 14, marginBottom: 16 }}>
            <div style={{ fontWeight: 600 }}>{job.shop_name}</div>
            <div>{job.when ? `${formatDate(job.when)} · ${formatTime(job.when)} Phoenix` : ""}</div>
            <div className="muted">{job.vehicle}</div>
            <div>{job.address}</div>
            <div className="muted">
              {job.calibration}{job.price != null ? ` · $${Number(job.price).toFixed(2)}` : ""}
            </div>
          </div>
        )}
        {result && <div data-testid="owner-action-result" style={{ marginBottom: 12 }}>{result}</div>}
        {preview && !result && (
          <button type="button" className={approving ? "btn btn-primary" : "btn btn-danger"}
            onClick={confirm} disabled={busy} data-testid="owner-action-confirm">
            {busy ? "Working…" : (approving ? "Approve this job" : "Decline this job")}
          </button>
        )}
      </div>
    </div>
  );
}
