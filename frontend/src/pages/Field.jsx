import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatTime, getStoredAuth, setStoredAuth, todayStr } from "../lib/api";
import RouteMap from "../components/RouteMap";

/**
 * Field PWA — technician/owner mobile field tool.
 *  Layout: route map → chronological job list with inline actions.
 *  Per-card actions: Start Driving (opens native maps), Send ETA, Complete & Charge.
 */
export default function Field() {
  const nav = useNavigate();
  const auth = getStoredAuth();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({}); // {jobId: 'eta'|'driving'|'complete'}
  const [flash, setFlash] = useState(null); // {kind, msg, jobId}
  const [completing, setCompleting] = useState(null); // {job}

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/jobs?date_str=${todayStr()}`);
      setJobs(data.filter(j => j.status !== "cancelled"));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 30000); // refresh every 30s
    return () => clearInterval(t);
  }, [load]);

  function logout() { setStoredAuth(null); nav("/login"); }

  function showFlash(kind, msg) {
    setFlash({ kind, msg });
    setTimeout(() => setFlash(null), 3500);
  }

  function openNavigation(address) {
    const ua = navigator.userAgent || "";
    const isIOS = /iPhone|iPad|iPod/.test(ua);
    const url = isIOS
      ? `maps://?daddr=${encodeURIComponent(address)}`
      : `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address)}`;
    window.open(url, "_blank", "noopener");
  }

  async function startDriving(job) {
    setBusy(b => ({ ...b, [job.id]: "driving" }));
    try {
      if (job.status === "booked") {
        await api.post(`/jobs/${job.id}/status`, { status: "driving" });
      }
      openNavigation(job.job_address);
      // Refresh in the background
      load();
    } catch (e) {
      showFlash("error", e.response?.data?.detail || "Could not update status");
    } finally {
      setBusy(b => { const c = { ...b }; delete c[job.id]; return c; });
    }
  }

  async function sendEta(job) {
    setBusy(b => ({ ...b, [job.id]: "eta" }));
    try {
      const { data } = await api.post(`/field/jobs/${job.id}/send-eta`);
      showFlash("success", `ETA sent — ~${data.eta_minutes} min`);
      load();
    } catch (e) {
      showFlash("error", e.response?.data?.detail || "Could not send ETA");
    } finally {
      setBusy(b => { const c = { ...b }; delete c[job.id]; return c; });
    }
  }

  async function submitCompletion(job, result, notes) {
    setBusy(b => ({ ...b, [job.id]: "complete" }));
    try {
      // Mark on_site first if it's still driving/booked (backend requires the flow)
      if (job.status !== "on_site" && job.status !== "complete") {
        await api.post(`/jobs/${job.id}/status`, { status: "on_site" });
      }
      const { data } = await api.post(`/jobs/${job.id}/complete`, { result, notes: notes || null });
      const ok = data.charge?.succeeded;
      if (ok) showFlash("success", `Complete · charged $${(data.charge.amount_cents/100).toFixed(2)} · Xero ${data.invoice?.invoice_id || ""}`);
      else if (data.charge?.error) showFlash("warning", `Complete — but charge needs review: ${data.charge.error}`);
      else showFlash("success", `Complete · invoice ${data.invoice?.invoice_id || ""} created`);
      setCompleting(null);
      load();
    } catch (e) {
      showFlash("error", e.response?.data?.detail || "Could not complete");
    } finally {
      setBusy(b => { const c = { ...b }; delete c[job.id]; return c; });
    }
  }

  // Sort: active (driving / on_site) first, then booked chronologically, then complete at bottom
  const sorted = [...jobs].sort((a, b) => {
    const rank = (j) => j.status === "complete" ? 2 : (j.status === "driving" || j.status === "on_site") ? 0 : 1;
    const r = rank(a) - rank(b);
    if (r !== 0) return r;
    return new Date(a.scheduled_start) - new Date(b.scheduled_start);
  });

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", paddingBottom: 24 }} data-testid="field-pwa">
      <Header name={auth?.name} onLogout={logout} onOwnerHome={auth?.role === "owner" ? () => nav("/dashboard") : null} />

      {flash && (
        <div data-testid="field-flash" style={{
          margin: "10px 12px 0", padding: "10px 12px", borderRadius: 8,
          background: flash.kind === "success" ? "rgba(16,185,129,0.15)" :
                     flash.kind === "warning" ? "rgba(245,158,11,0.15)" :
                                                "rgba(239,68,68,0.15)",
          border: `1px solid ${
            flash.kind === "success" ? "rgba(16,185,129,0.4)" :
            flash.kind === "warning" ? "rgba(245,158,11,0.4)" :
                                       "rgba(239,68,68,0.4)"}`,
          color: flash.kind === "success" ? "var(--green)" :
                 flash.kind === "warning" ? "var(--yellow)" : "var(--red)",
          fontSize: 13, fontWeight: 600,
        }}>{flash.msg}</div>
      )}

      <div style={{ padding: 12, paddingBottom: 4 }}>
        <div className="muted" style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 2 }}>Today&apos;s Route</div>
        <h1 className="h1" style={{ fontSize: 22, marginBottom: 10 }}>
          {new Date().toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} · {jobs.length} jobs
        </h1>
      </div>

      {jobs.length > 0 && (
        <div style={{ padding: "0 12px", marginBottom: 12 }}>
          <RouteMap jobs={jobs} height={260} />
        </div>
      )}

      <div style={{ padding: "0 12px", display: "flex", flexDirection: "column", gap: 10 }}>
        {loading && <div className="muted">Loading…</div>}
        {!loading && jobs.length === 0 && (
          <div className="surface muted" style={{ padding: 24, textAlign: "center" }}>No jobs today.</div>
        )}
        {sorted.map((j, idx) => (
          <FieldJobCard key={j.id} job={j} stopNumber={idx + 1}
            busyKind={busy[j.id]}
            onDrive={() => startDriving(j)}
            onEta={() => sendEta(j)}
            onComplete={() => setCompleting({ job: j })} />
        ))}
      </div>

      {completing && (
        <CompleteSheet job={completing.job}
          onCancel={() => setCompleting(null)}
          onSubmit={(result, notes) => submitCompletion(completing.job, result, notes)}
          busy={busy[completing.job.id] === "complete"} />
      )}
    </div>
  );
}

// ---------- Card ----------

function FieldJobCard({ job, stopNumber, busyKind, onDrive, onEta, onComplete }) {
  const isComplete = job.status === "complete";
  const isCancelled = job.status === "cancelled";
  const driveOrOnSite = job.status === "driving" || job.status === "on_site";
  const customer = job.customer_last_name || "Customer";
  const vehicle = [job.vehicle_year, job.vehicle_make, job.vehicle_model].filter(Boolean).join(" ");
  const jobType = job.job_type || "cash";
  const lastEtaMin = job.last_eta_minutes;

  return (
    <div className={"card-job" + (isComplete ? " card-job-complete" : "")}
         style={{
           background: isComplete ? "rgba(16,185,129,0.08)" : "var(--bg-surface)",
           borderColor: isComplete ? "rgba(16,185,129,0.4)" : driveOrOnSite ? "var(--accent)" : "var(--border)",
           borderWidth: 1, borderStyle: "solid",
         }}
         data-testid={`field-card-${job.id}`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="font-mono" style={{
            background: isComplete ? "rgba(16,185,129,0.25)" : "var(--bg-elevated)",
            color: isComplete ? "var(--green)" : "var(--text)",
            fontSize: 12, fontWeight: 700, padding: "3px 9px", borderRadius: 6,
          }}>#{stopNumber}</span>
          <span className="font-display" style={{ fontSize: 16, fontWeight: 700 }}>{formatTime(job.scheduled_start)}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
          <StatusBadge status={job.status} />
          <span style={{
            fontSize: 10, padding: "2px 6px", borderRadius: 4, fontWeight: 700, letterSpacing: "0.08em",
            background: jobType === "insurance" ? "rgba(59,130,246,0.2)" : "rgba(148,163,184,0.18)",
            color: jobType === "insurance" ? "#60a5fa" : "var(--text-muted)",
          }}>{jobType === "insurance" ? `INS · $${(job.insurance_approved_amount || 0).toFixed(0)}` : "CASH"}</span>
        </div>
      </div>

      <div className="h3" style={{ marginTop: 8 }}>{job.shop_name}</div>
      <div style={{ fontSize: 13, marginTop: 2 }}>
        <span style={{ fontWeight: 600 }}>{customer}</span>
        <span className="muted"> · {vehicle || "—"}</span>
      </div>
      {job.vehicle_vin && (
        <div className="font-mono muted" style={{ fontSize: 11, marginTop: 2 }}>
          VIN: {job.vehicle_vin}
        </div>
      )}
      <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>📍 {job.job_address}</div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        {job.calibration_label} · <span className="font-mono">${job.price.toFixed(2)}</span>
        {typeof job.drive_time_minutes === "number" && <span> · drive ~{job.drive_time_minutes} min</span>}
      </div>
      {lastEtaMin != null && job.last_eta_sent_at && !isComplete && (
        <div style={{ fontSize: 11, color: "var(--accent)", marginTop: 4 }}>
          ✓ ETA sent ({lastEtaMin} min) · {new Date(job.last_eta_sent_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
        </div>
      )}
      {isComplete && job.charge_status === "succeeded" && (
        <div style={{ fontSize: 12, color: "var(--green)", marginTop: 6, fontWeight: 600 }}>
          ✓ Charged · {job.charge_card_brand?.toUpperCase()} ****{job.charge_card_last4}
        </div>
      )}

      {!isComplete && !isCancelled && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginTop: 12 }}>
          <button className="btn btn-ghost" onClick={onDrive} disabled={!!busyKind}
            style={{ padding: 10, fontSize: 13 }} data-testid={`drive-${job.id}`}>
            {busyKind === "driving" ? "…" : "🚗 Drive"}
          </button>
          <button className="btn btn-ghost" onClick={onEta} disabled={!!busyKind}
            style={{ padding: 10, fontSize: 13 }} data-testid={`eta-${job.id}`}>
            {busyKind === "eta" ? "…" : "📱 ETA"}
          </button>
          <button className="btn btn-primary" onClick={onComplete} disabled={!!busyKind}
            style={{ padding: 10, fontSize: 13 }} data-testid={`complete-${job.id}`}>
            {busyKind === "complete" ? "…" : "✓ Done"}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------- Status badge ----------
function StatusBadge({ status }) {
  const map = {
    booked:    { c: "var(--text-muted)", bg: "rgba(148,163,184,0.18)", bd: "var(--border)",            label: "BOOKED" },
    driving:   { c: "var(--accent)",     bg: "rgba(249,115,22,0.18)",  bd: "rgba(249,115,22,0.4)",     label: "DRIVING" },
    on_site:   { c: "#60a5fa",           bg: "rgba(59,130,246,0.18)",  bd: "rgba(59,130,246,0.4)",     label: "ON SITE" },
    complete:  { c: "var(--green)",      bg: "rgba(16,185,129,0.18)",  bd: "rgba(16,185,129,0.4)",     label: "COMPLETE" },
    cancelled: { c: "var(--red)",        bg: "rgba(239,68,68,0.18)",   bd: "rgba(239,68,68,0.4)",      label: "CANCELLED" },
  };
  const s = map[status] || map.booked;
  return <span style={{
    background: s.bg, color: s.c, border: `1px solid ${s.bd}`,
    padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
  }}>{s.label}</span>;
}

// ---------- Complete sheet (slide-up) ----------
function CompleteSheet({ job, onCancel, onSubmit, busy }) {
  const [result, setResult] = useState("pass");
  const [notes, setNotes] = useState("");
  return (
    <div onClick={onCancel} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 60,
      display: "flex", alignItems: "flex-end", justifyContent: "center",
    }} data-testid="complete-sheet">
      <div onClick={e => e.stopPropagation()} className="surface page-fade"
        style={{ width: "100%", maxWidth: 480, padding: 20, borderRadius: "16px 16px 0 0" }}>
        <div className="muted" style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 4 }}>
          Complete & Charge
        </div>
        <div className="h2" style={{ marginBottom: 14 }}>
          {job.shop_name}
        </div>
        <div className="elevated" style={{ padding: 12, fontSize: 13, marginBottom: 14 }}>
          <div><b>{job.customer_last_name}</b> · {job.vehicle_year} {job.vehicle_make} {job.vehicle_model}</div>
          <div className="muted" style={{ marginTop: 2 }}>{job.calibration_label}</div>
          <div style={{ marginTop: 6, fontWeight: 700, fontSize: 16 }}>
            Charge <span className="font-mono">${job.price.toFixed(2)}</span>
          </div>
        </div>

        <div className="label">Result</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          <button className={"btn " + (result === "pass" ? "btn-primary" : "btn-ghost")}
            onClick={() => setResult("pass")} style={{ flex: 1, padding: 12 }} data-testid="complete-pass">
            PASS
          </button>
          <button className={"btn " + (result === "fail" ? "btn-primary" : "btn-ghost")}
            onClick={() => setResult("fail")} style={{ flex: 1, padding: 12 }} data-testid="complete-fail">
            FAIL
          </button>
        </div>

        <div className="label">Notes (optional)</div>
        <textarea className="input" rows={2} value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Anything to flag?" data-testid="complete-notes" />

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button className="btn btn-ghost" onClick={onCancel} disabled={busy}
            style={{ flex: 1, padding: 12 }} data-testid="complete-cancel">
            Cancel
          </button>
          <button className="btn btn-primary" onClick={() => onSubmit(result, notes)} disabled={busy}
            style={{ flex: 2, padding: 12 }} data-testid="complete-submit">
            {busy ? "Working…" : `✓ Complete & Charge $${job.price.toFixed(2)}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- Header ----------
function Header({ name, onLogout, onOwnerHome }) {
  return (
    <header style={{
      display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px",
      borderBottom: "1px solid var(--border)", position: "sticky", top: 0,
      background: "var(--bg-primary)", zIndex: 20,
    }}>
      <span className="brand-mark" style={{ fontSize: 18 }}>
        <span className="brand-word">CAL</span>
        <span className="brand-suffix">OS</span>
        <span className="muted" style={{ fontSize: 11, marginLeft: 8, letterSpacing: "0.16em" }}>FIELD</span>
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {onOwnerHome && (
          <button className="btn btn-ghost" onClick={onOwnerHome} style={{ padding: "4px 8px", fontSize: 11 }} data-testid="field-back-to-admin">
            ← Admin
          </button>
        )}
        <span className="muted" style={{ fontSize: 12 }}>{name}</span>
        <button className="btn btn-ghost" onClick={onLogout} style={{ padding: "4px 8px", fontSize: 11 }} data-testid="field-logout">
          Out
        </button>
      </div>
    </header>
  );
}
