import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatTime, formatDate, getStoredAuth, setStoredAuth, todayStr } from "../lib/api";

/** Mobile-optimized PWA technician field view. Works on phone or desktop. */
export default function Field() {
  const nav = useNavigate();
  const auth = getStoredAuth();
  const [jobs, setJobs] = useState([]);
  const [active, setActive] = useState(null);
  const [completing, setCompleting] = useState(false);
  const [result, setResult] = useState("pass");
  const [notes, setNotes] = useState("");
  const [docName, setDocName] = useState("");
  const [loading, setLoading] = useState(true);

  const [offers, setOffers] = useState([]);

  const load = useCallback(async () => {
    try {
      const [j, o] = await Promise.all([
        api.get(`/jobs?date_str=${todayStr()}`),
        api.get(`/contractor-offers`),
      ]);
      setJobs(j.data);
      setOffers(o.data.filter(x => x.status === "pending"));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  function logout() { setStoredAuth(null); nav("/login"); }

  const [uploadedDoc, setUploadedDoc] = useState(null);
  const [uploading, setUploading] = useState(false);

  async function respondOffer(offerId, accept) {
    await api.post(`/contractor-offers/${offerId}/respond`, { accept });
    load();
  }

  async function uploadDoc(jobId, file) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(`/jobs/${jobId}/upload-document`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadedDoc(data);
    } catch (e) {
      alert(e.response?.data?.detail || "Upload failed");
    } finally { setUploading(false); }
  }

  async function setStatus(jobId, status) {
    await api.post(`/jobs/${jobId}/status`, { status });
    load();
  }
  async function complete(jobId) {
    setCompleting(true);
    try {
      await api.post(`/jobs/${jobId}/complete`, { result, notes: notes || null });
      setActive(null); setResult("pass"); setNotes(""); setDocName(""); setUploadedDoc(null);
      load();
    } finally { setCompleting(false); }
  }

  if (active) {
    const j = jobs.find(x => x.id === active);
    if (!j) { setActive(null); return null; }
    return (
      <Phone>
        <Header name={auth?.name} onLogout={logout} back={() => setActive(null)} />
        <div className="surface page-fade" style={{ padding: 18, margin: 12 }} data-testid="job-detail">
          <div className="muted" style={{ fontSize: 12 }}>{formatTime(j.scheduled_start)}</div>
          <div className="h2" style={{ marginTop: 4 }}>{j.shop_name}</div>
          <div className="muted" style={{ fontSize: 14, marginTop: 4 }}>
            {j.vehicle_year} {j.vehicle_make} {j.vehicle_model}
          </div>
          <a className="btn btn-ghost" style={{ marginTop: 12, width: "100%" }}
            href={`https://maps.google.com/?q=${encodeURIComponent(j.job_address)}`} target="_blank" rel="noreferrer">
            📍 {j.job_address}
          </a>
          {j.notification_phone && <a className="btn btn-ghost" style={{ marginTop: 8, width: "100%" }} href={`tel:${j.notification_phone}`}>📞 Call shop</a>}
          <div style={{ marginTop: 16, fontSize: 14, padding: 10, background: "var(--bg-elevated)", borderRadius: 8 }}>
            <div><b>Service:</b> {j.calibration_label}</div>
            <div><b>Price:</b> ${j.price.toFixed(2)}</div>
            <div><b>Status:</b> <span className={`badge badge-${j.status}`}>{j.status.replace(/_/g, " ")}</span></div>
          </div>

          {j.status === "booked" && (
            <button className="btn btn-primary" style={{ width: "100%", marginTop: 16, padding: 14 }}
              onClick={() => setStatus(j.id, "driving")} data-testid="action-start-driving">Start Driving</button>
          )}
          {j.status === "driving" && (
            <button className="btn btn-primary" style={{ width: "100%", marginTop: 16, padding: 14 }}
              onClick={() => setStatus(j.id, "on_site")} data-testid="action-arrived">I&apos;ve Arrived</button>
          )}
          {j.status === "on_site" && (
            <div style={{ marginTop: 16 }}>
              <div className="label">Result *</div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className={"btn " + (result === "pass" ? "btn-primary" : "btn-ghost")} onClick={() => setResult("pass")}
                  style={{ flex: 1 }} data-testid="result-pass">PASS</button>
                <button className={"btn " + (result === "fail" ? "btn-primary" : "btn-ghost")} onClick={() => setResult("fail")}
                  style={{ flex: 1 }} data-testid="result-fail">FAIL</button>
              </div>
              <div style={{ marginTop: 14 }}>
                <div className="label">Notes (optional)</div>
                <textarea className="input" rows={3} value={notes} onChange={e => setNotes(e.target.value)} />
              </div>
              <div style={{ marginTop: 14 }}>
                <div className="label">Calibration documentation (PDF or photo)</div>
                {!uploadedDoc ? (
                  <label className="btn btn-ghost" style={{ width: "100%", padding: 14, cursor: "pointer", justifyContent: "center" }}>
                    {uploading ? "Uploading…" : "📷 Take photo / 📄 Upload PDF"}
                    <input type="file" accept="image/*,application/pdf" capture="environment"
                      style={{ display: "none" }} disabled={uploading}
                      onChange={(e) => { if (e.target.files[0]) uploadDoc(j.id, e.target.files[0]); }}
                      data-testid="doc-upload" />
                  </label>
                ) : (
                  <div className="elevated" style={{ padding: 12 }} data-testid="doc-uploaded">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>✓ {uploadedDoc.file_name}</div>
                        <div className="muted" style={{ fontSize: 12 }}>{(uploadedDoc.size_bytes / 1024).toFixed(1)} KB · {uploadedDoc.content_type}</div>
                      </div>
                      <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                        onClick={() => setUploadedDoc(null)} data-testid="doc-remove">Replace</button>
                    </div>
                  </div>
                )}
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  Will be renamed and attached to the invoice automatically.
                </div>
              </div>
              <button className="btn btn-primary" style={{ width: "100%", marginTop: 16, padding: 14 }}
                disabled={completing} onClick={() => complete(j.id)} data-testid="action-complete">
                {completing ? "Submitting…" : "Submit Completion"}
              </button>
            </div>
          )}
          {j.status === "complete" && (
            <div className="elevated" style={{ marginTop: 16, padding: 14, textAlign: "center" }} data-testid="job-complete-confirmation">
              <div style={{ fontSize: 36, color: "var(--green)" }}>✓</div>
              <div className="h3" style={{ marginTop: 4 }}>Job Complete</div>
              <div className="muted" style={{ fontSize: 13 }}>Invoice {j.invoice_id} created — Maddy notified.</div>
            </div>
          )}
        </div>
      </Phone>
    );
  }

  return (
    <Phone>
      <Header name={auth?.name} onLogout={logout} />
      <div style={{ padding: 12 }}>
        <div className="muted" style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 4 }}>Today</div>
        <h1 className="h1" style={{ marginBottom: 12, fontSize: 28 }}>
          {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
        </h1>
        {loading && <div className="muted">Loading…</div>}

        {offers.length > 0 && (
          <div style={{ marginBottom: 16 }} data-testid="pending-offers">
            <div className="label" style={{ color: "var(--accent-ink)" }}>Pending offers ({offers.length})</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {offers.map(o => (
                <div key={o.id} className="card-job-new card-job" data-testid={`offer-${o.id}`}>
                  <div className="h3">{o.shop_name}</div>
                  <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{o.vehicle}</div>
                  <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                    {formatTime(o.scheduled_start)} · ${o.price.toFixed(2)}
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{o.job_address}</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <button className="btn btn-primary" style={{ flex: 1 }}
                      onClick={() => respondOffer(o.id, true)} data-testid={`accept-${o.id}`}>Accept</button>
                    <button className="btn btn-ghost" style={{ flex: 1, borderColor: "rgba(239,68,68,0.4)", color: "var(--red)" }}
                      onClick={() => respondOffer(o.id, false)} data-testid={`decline-${o.id}`}>Decline</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!loading && jobs.length === 0 && offers.length === 0 && (
          <div className="surface muted" style={{ padding: 24, textAlign: "center" }}>No jobs today.</div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {jobs.map((j, idx) => (
            <button key={j.id} className="card-job" style={{ textAlign: "left", width: "100%", cursor: "pointer", background: "var(--bg-surface)" }}
              onClick={() => setActive(j.id)} data-testid={`field-job-${j.id}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div className="font-mono" style={{ fontSize: 12, padding: "2px 8px", background: "var(--bg-elevated)", borderRadius: 6 }}>
                  #{idx + 1}
                </div>
                <div className="font-display" style={{ fontSize: 18, fontWeight: 700 }}>{formatTime(j.scheduled_start)}</div>
              </div>
              <div className="h3" style={{ marginTop: 6 }}>{j.shop_name}</div>
              <div className="muted" style={{ fontSize: 13 }}>{j.vehicle_year} {j.vehicle_make} {j.vehicle_model}</div>
              <div style={{ marginTop: 8 }}><span className={`badge badge-${j.status}`}>{j.status.replace(/_/g, " ")}</span></div>
            </button>
          ))}
        </div>
      </div>
    </Phone>
  );
}

function Phone({ children }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", maxWidth: 480, margin: "0 auto" }}>
      {children}
    </div>
  );
}

function Header({ name, onLogout, back }) {
  return (
    <header style={{
      display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px",
      borderBottom: "1px solid var(--border)", position: "sticky", top: 0, background: "var(--bg-primary)", zIndex: 10,
    }}>
      {back ? (
        <button className="btn btn-ghost" onClick={back} data-testid="field-back">← Back</button>
      ) : (
        <span className="brand-mark" style={{ fontSize: 18 }}>
          <span className="brand-word">CAL</span>
          <span className="brand-suffix">OS</span>
        </span>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span className="muted" style={{ fontSize: 12 }}>{name}</span>
        <button className="btn btn-ghost" onClick={onLogout} data-testid="field-logout">Out</button>
      </div>
    </header>
  );
}
