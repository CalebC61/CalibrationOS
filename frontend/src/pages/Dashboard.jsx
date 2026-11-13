import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, formatTime, phoenixTodayStr, dateStr, getStoredAuth, isOnDayBoard, jobStatusLabel } from "../lib/api";
import Shell from "../components/Shell";
import DispatchModal from "../components/DispatchModal";
import RouteMap from "../components/RouteMap";
import RescheduleCancelModal from "../components/RescheduleCancelModal";
import TomorrowStrip from "../components/TomorrowStrip";
import JobEditModal from "../components/JobEditModal";

const STATUS_FLOW = {
  booked: { next: "driving", label: "Start Driving" },
  driving: { next: "on_site", label: "I've Arrived" },
  on_site: { next: "complete", label: "Complete Job" },
};

export default function Dashboard() {
  const isOwner = getStoredAuth()?.role === "owner";
  const [date, setDate] = useState(() => phoenixTodayStr());
  const [jobs, setJobs] = useState([]);
  const [techs, setTechs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState({ count: 0, alerts: [] });
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [offers, setOffers] = useState([]);
  const [dispatchTarget, setDispatchTarget] = useState(null);
  const [rescheduleTarget, setRescheduleTarget] = useState(null); // { job, mode: 'reschedule' | 'cancel' }
  const [dragOver, setDragOver] = useState(null);
  const [refreshingMap, setRefreshingMap] = useState(false);
  const [refreshResult, setRefreshResult] = useState(null);
  const [refreshError, setRefreshError] = useState(null);
  const [editTarget, setEditTarget] = useState(null);

  const load = useCallback(async () => {
    try {
      const [j, s, a, o] = await Promise.all([
        api.get(`/jobs?date_str=${date}`),
        api.get(`/dashboard/summary?date_str=${date}`),
        api.get(`/notifications/new-bookings`),
        api.get(`/contractor-offers`),
      ]);
      setJobs(j.data); setSummary(s.data); setAlerts(a.data); setOffers(o.data);
      try {
        const t = await api.get("/routing-techs");
        setTechs(t.data || []);
      } catch { setTechs([]); }
    } catch (e) { console.error(e); }
  }, [date]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  async function markSeen() {
    await api.post("/notifications/mark-seen");
    setAlerts({ count: 0, alerts: [] });
    setAlertsOpen(false);
  }
  async function setPaymentMode(jobId, mode) {
    try {
      await api.post(`/jobs/${jobId}/payment-mode`, { mode });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not change how this job is billed.");
    }
  }
  async function setOutside(jobId, enabled) {
    try {
      await api.post(`/jobs/${jobId}/outside-service-area`, { enabled });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not update the trip fee.");
    }
  }
  async function chargeTripFee(jobId, reason) {
    try {
      await api.post(`/jobs/${jobId}/trip-fee`, { reason });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Could not charge the trip fee.");
    }
  }
  async function chargeNow(jobId) {
    try {
      await api.post(`/jobs/${jobId}/charge-card`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "The card was not charged.");
      load();
    }
  }
  async function setStatus(jobId, status) {
    if (status === "complete") {
      const ok = window.confirm("Mark this job complete? Charge-on-completion jobs are charged once. Invoice jobs are billed and not charged until you say so. A second click will not create another invoice.");
      if (!ok) return;
      try {
        await api.post(`/jobs/${jobId}/complete`, { result: "pass", notes: null });
      } catch (err) {
        alert(err.response?.data?.detail || "Could not complete the job.");
      }
    } else {
      await api.post(`/jobs/${jobId}/status`, { status });
    }
    load();
  }
  async function decideApproval(jobId, approve) {
    try {
      await api.post(`/jobs/${jobId}/${approve ? "approve" : "decline"}`);
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Could not update that request.");
    }
  }
  async function manualRespond(offerId, accept) {
    await api.post(`/contractor-offers/${offerId}/respond`, { accept });
    load();
  }

  const newJobIds = new Set(alerts.alerts.map(a => a.job_id));
  const offerByJob = Object.fromEntries(offers.filter(o => o.status === "pending").map(o => [o.job_id, o]));
  const dayJobs = jobs.filter(isOnDayBoard);

  const routingTechs = techs.filter(t => t.role !== "contractor" && t.routes_jobs !== false && t.is_active !== false);
  const colorById = Object.fromEntries(routingTechs.map(t => [t.id, t.color || "#FF5F1F"]));
  const nameById = Object.fromEntries(routingTechs.map(t => [t.id, t.name]));
  const painted = dayJobs.map(j => ({
    ...j,
    technician_color: j.technician_color || colorById[j.technician_id] || "#FF5F1F",
    technician_name: j.technician_name || nameById[j.technician_id] || "",
  }));
  function jobsFor(tech) {
    return painted
      .filter(j => j.technician_id === tech.id || (!j.technician_id && tech.role === "owner"))
      .sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start));
  }
  const panels = (routingTechs.length ? routingTechs : [{ id: "unassigned", name: "Today", role: "owner", color: "#FF5F1F", home_address: "" }])
    .map(tech => ({ tech, jobs: tech.id === "unassigned" ? painted.slice().sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start)) : jobsFor(tech) }));

  function shiftDate(days) {
    const d = new Date(date + "T00:00:00");
    d.setDate(d.getDate() + days);
    setDate(dateStr(d));
  }

  async function refreshLocations() {
    const ok = window.confirm("Refresh map locations? This only updates coordinates and sends no messages.");
    if (!ok) return;
    setRefreshingMap(true);
    setRefreshError(null);
    try {
      const { data } = await api.post("/admin/regeocode");
      setRefreshResult(data);
      await load();
    } catch (e) {
      setRefreshResult(null);
      const detail = e.response?.data?.detail;
      setRefreshError(typeof detail === "string" ? detail : "Could not refresh locations. Try again.");
    } finally {
      setRefreshingMap(false);
    }
  }

  async function handleDrop(techId, draggedId, targetIdx) {
    const panel = panels.find(p => p.tech.id === techId);
    const ids = (panel?.jobs || []).map(j => j.id).filter(id => id !== draggedId);
    ids.splice(targetIdx, 0, draggedId);
    try {
      await api.post("/jobs/reorder", { technician_id: techId, date, ordered_job_ids: ids });
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Reorder failed");
    }
    setDragOver(null);
  }

  return (
    <Shell>
      {alerts.count > 0 && (
        <div className="page-fade" style={{ marginBottom: 16, position: "relative" }} data-testid="new-bookings-banner">
          <button onClick={() => setAlertsOpen(o => !o)} data-testid="new-bookings-pill"
            style={{ display: "inline-flex", alignItems: "center", gap: 10,
              background: "var(--accent)", color: "#0a0a0a",
              border: "1px solid var(--accent)", borderRadius: 999,
              padding: "8px 16px", fontWeight: 600, fontSize: 14, cursor: "pointer" }}>
            <span className="pulse-dot" style={{ width: 8, height: 8, borderRadius: 999, background: "#0a0a0a" }} />
            <span data-testid="new-bookings-count">{alerts.count}</span> new booking{alerts.count === 1 ? "" : "s"} since you last looked
            <span style={{ fontSize: 12 }}>{alertsOpen ? "▲" : "▼"}</span>
          </button>
          {alertsOpen && (
            <div className="surface page-fade" style={{
              position: "absolute", top: "calc(100% + 8px)", left: 0, zIndex: 30,
              minWidth: 360, maxWidth: 480, padding: 12, boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
            }} data-testid="new-bookings-panel">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div className="h3">New bookings</div>
                <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                  onClick={markSeen} data-testid="mark-bookings-seen">Mark all seen</button>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 320, overflowY: "auto" }}>
                {alerts.alerts.map(a => (
                  <div key={a.id} className="elevated" style={{ padding: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>{a.shop_name}</div>
                        <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{a.vehicle}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <span className={`badge badge-${a.zone}`}>{a.zone}</span>
                        <div className="font-mono" style={{ fontSize: 12, marginTop: 4 }}>{formatTime(a.scheduled_start)}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {summary && summary.shop_emails_enabled === false && (
        <Link to="/email-preview" data-testid="shop-emails-off" style={{
          display: "inline-block", marginBottom: 12, padding: "4px 10px", borderRadius: 999,
          background: "rgba(245, 158, 11, 0.16)", color: "var(--yellow)",
          fontSize: 13, fontWeight: 600, textDecoration: "none",
        }}>
          Shop emails: OFF (testing)
        </Link>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, flexWrap: "wrap", gap: 16 }}>
        <div>
          <h1 className="h1" style={{ margin: "4px 0" }}>
            {new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </h1>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <button className="btn btn-ghost" onClick={() => shiftDate(-1)} data-testid="prev-day">← Prev</button>
            <button className="btn btn-ghost" onClick={() => setDate(phoenixTodayStr())} data-testid="today-btn">Today</button>
            <button className="btn btn-ghost" onClick={() => shiftDate(1)} data-testid="next-day">Next →</button>
          </div>
        </div>
        {summary && (
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            <Metric label="Jobs" value={summary.job_count} />
            <Metric label="Revenue" value={`$${summary.revenue.toFixed(0)}`} />
            <Metric label="Est. Miles" value={summary.estimated_miles} />
            <Metric label="Done By" value={summary.done_by ? formatTime(summary.done_by) : "—"} />
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 16, marginBottom: 20 }}>
        {panels.map(({ tech, jobs: techJobs }) => (
          <ZonePanel key={tech.id}
            title={tech.name || "Technician"}
            subtitle={routingTechs.length <= 1 ? "Whole valley" : (tech.home_address || "Home base")}
            zone={tech.id} jobs={techJobs} onStatus={setStatus}
            onPayment={setPaymentMode} onCharge={chargeNow}
            onOutside={setOutside} onTripFee={chargeTripFee}
            accent={tech.color || "#FF5F1F"}
            newJobIds={newJobIds} offerByJob={offerByJob}
            onDispatch={setDispatchTarget} onRespond={manualRespond}
            onReschedule={(job, mode) => setRescheduleTarget({ job, mode })}
            onEdit={isOwner ? setEditTarget : null}
            onDecide={isOwner ? decideApproval : null}
            dragOver={dragOver} setDragOver={setDragOver} onDrop={handleDrop} />
        ))}
      </div>

      <section>
        <div className="h3" style={{ marginBottom: 10, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span>Route Map</span>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            {routingTechs.length > 0 && (
              <span className="muted" style={{ fontSize: 12, fontWeight: 400, display: "flex", gap: 10, flexWrap: "wrap" }}>
                {routingTechs.map(t => (
                  <span key={t.id} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 99, background: t.color || "#FF5F1F" }} />
                    {t.name}
                  </span>
                ))}
              </span>
            )}
            {isOwner && (
            <button type="button" className="btn btn-ghost" onClick={refreshLocations} disabled={refreshingMap}
              data-testid="refresh-map-locations"
              style={{ padding: "6px 12px", fontSize: 13, opacity: refreshingMap ? 0.6 : 1 }}>
              {refreshingMap ? "Refreshing…" : "Refresh map locations"}
            </button>
            )}
          </div>
        </div>
        {refreshResult && (
          <div className="muted" style={{ fontSize: 13, marginBottom: 10 }} data-testid="regeocode-result">
            {refreshResult.shops && <div>Shops: {countLine(refreshResult.shops)}</div>}
            <div>Jobs: {countLine(refreshResult.jobs)}</div>
          </div>
        )}
        {refreshError && (
          <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 10 }} data-testid="regeocode-error">{refreshError}</div>
        )}
        {dayJobs.length > 0 ? (
          <RouteMap jobs={painted} />
        ) : (
          <div className="surface muted" style={{ padding: 16, textAlign: "center" }}>No jobs on this day.</div>
        )}
      </section>

      <DispatchModal open={!!dispatchTarget} job={dispatchTarget}
        onClose={() => setDispatchTarget(null)} onDone={load} />
      <JobEditModal open={!!editTarget} job={editTarget}
        onClose={() => setEditTarget(null)} onDone={load} />
      <RescheduleCancelModal open={!!rescheduleTarget} job={rescheduleTarget?.job}
        mode={rescheduleTarget?.mode}
        onClose={() => setRescheduleTarget(null)} onDone={load} />
      <TomorrowStrip baseDate={date} />
    </Shell>
  );
}

function countLine(group) {
  const n = (k) => Number(group?.[k] || 0);
  return `${n("updated")} updated, ${n("failed")} failed, ${n("skipped")} skipped`;
}

function Metric({ label, value, highlight }) {
  return (
    <div className="surface" style={{
      padding: "10px 16px", minWidth: 100,
      borderColor: highlight === "red" ? "var(--red)" : "var(--border)",
      boxShadow: highlight === "red" ? "0 0 18px rgba(239,68,68,0.18)" : undefined,
    }}>
      <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</div>
      <div className="font-display" style={{ fontSize: 22, fontWeight: 700, color: highlight === "red" ? "var(--red)" : undefined }}>{value}</div>
    </div>
  );
}

function ZonePanel({ title, subtitle, zone, jobs, onStatus, onPayment, onCharge, onOutside, onTripFee, accent, newJobIds, offerByJob,
                    onDispatch, onRespond, onReschedule, onEdit, onDecide, dragOver, setDragOver, onDrop }) {
  return (
    <section data-testid={`zone-panel-${zone}`}>
      <div className="zone-header">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: 99, background: accent }} />
          {title}
        </span>
        <span style={{ fontSize: 12 }}>{subtitle} · {jobs.length} jobs</span>
      </div>
      {jobs.length === 0 && (
        <div className="surface muted" style={{ padding: 20, textAlign: "center" }}>No jobs for this technician yet.</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {jobs.map((j, idx) => (
          <JobCard key={j.id} job={j} index={idx + 1} onStatus={onStatus}
            onPayment={onPayment} onCharge={onCharge}
            onOutside={onOutside} onTripFee={onTripFee}
            isNew={newJobIds?.has(j.id)} offer={offerByJob?.[j.id]}
            onDispatch={onDispatch} onRespond={onRespond} onReschedule={onReschedule} onEdit={onEdit}
            onDecide={onDecide}
            zone={zone} dropIndex={idx}
            isDragOver={dragOver?.zone === zone && dragOver?.idx === idx}
            onDragOver={(e) => { e.preventDefault(); setDragOver({ zone, idx }); }}
            onDragLeave={() => setDragOver(null)}
            onHandleDrop={(e) => {
              e.preventDefault();
              const draggedId = e.dataTransfer.getData("text/plain");
              if (draggedId) onDrop(zone, draggedId, idx);
            }}
          />
        ))}
      </div>
    </section>
  );
}

function OfferCountdown({ expiresAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const ms = new Date(expiresAt).getTime() - now;
  if (ms <= 0) return <span className="muted">expired</span>;
  const min = Math.floor(ms / 60000);
  const sec = Math.floor((ms % 60000) / 1000);
  return <span className="font-mono">{min}:{String(sec).padStart(2, "0")}</span>;
}

function TripFeeControls({ job, onOutside, onTripFee }) {
  const [reason, setReason] = useState("bad_install");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <button className="btn btn-ghost" type="button" disabled={busy}
        onClick={() => onOutside(job.id, !job.outside_service_area)}
        data-testid={`job-outside-${job.id}`}>
        {job.outside_service_area ? "Remove outside-area $30" : "Outside service area, +$30"}
      </button>
      <label className="muted" style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
        Couldn't calibrate
        <select className="input" value={reason} onChange={e => setReason(e.target.value)}
          style={{ width: "auto", padding: "6px 8px" }} data-testid={`job-trip-reason-${job.id}`}>
          <option value="bad_install">Bad install</option>
          <option value="customer_vehicle">Customer or vehicle</option>
        </select>
      </label>
      <button className="btn btn-ghost" type="button" disabled={busy}
        onClick={async () => { setBusy(true); try { await onTripFee(job.id, reason); } finally { setBusy(false); } }}
        data-testid={`job-trip-fee-${job.id}`}>
        Couldn't calibrate, charge $30 trip fee
      </button>
    </>
  );
}

function JobCard({ job, index, onStatus, onPayment, onCharge, onOutside, onTripFee, isNew, offer, onDispatch, onRespond, onReschedule, onEdit, onDecide,
                   zone, dropIndex, isDragOver, onDragOver, onDragLeave, onHandleDrop }) {
  const flow = STATUS_FLOW[job.status];
  const isLocked = job.status === "complete" || job.status === "cancelled" || job.status === "declined" || job.status === "requested";
  return (
    <div
      className={"card-job" + (isNew ? " card-job-new" : "") + (isDragOver ? " card-job-dropzone" : "") + (job.is_at_risk ? " card-job-at-risk" : "")}
      draggable={!isLocked}
      onDragStart={(e) => e.dataTransfer.setData("text/plain", job.id)}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onHandleDrop}
      data-testid={`job-card-${job.id}`}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
            <span className="font-mono" style={{
              background: "var(--bg-elevated)", padding: "2px 8px", borderRadius: 6,
              fontSize: 12, fontWeight: 600,
            }}>#{index}</span>
            <span className={`badge badge-${job.status}`}>{jobStatusLabel(job.status)}</span>
            {isNew && <span className="badge" style={{ background: "var(--accent)", color: "#0a0a0a", border: "1px solid var(--accent)" }} data-testid="badge-new">NEW</span>}
            {job.outside_service_area && !job.calibration_not_performed && <span className="badge badge-draft">Outside area +$30</span>}
            {job.calibration_not_performed && <span className="badge badge-draft">Trip fee only</span>}
            {job.payment_mode === "invoice_hold" && <span className="badge badge-draft">Invoice — hold charge</span>}
            {job.payment_status === "payment_failed" && <span className="badge" style={{ background: "rgba(239,68,68,0.15)", color: "var(--red)" }}>Payment failed</span>}
            {job.late_fee ? <span className="badge badge-draft">Late fee ${job.late_fee}</span> : null}
            {offer && (
              <span className="badge badge-dispatched_to_contractor" data-testid={`offer-countdown-${job.id}`}>
                {offer.contractor_name} · <OfferCountdown expiresAt={offer.expires_at} />
              </span>
            )}
            {job.is_at_risk && (
              <span className="badge" style={{ background: "rgba(239,68,68,0.15)", color: "var(--red)", border: "1px solid rgba(239,68,68,0.3)" }}
                title={job.risk_reason} data-testid={`badge-at-risk-${job.id}`}>
                ⚠ AT RISK
              </span>
            )}
          </div>
          <div className="h3" style={{ marginTop: 4 }}>{job.shop_name}</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            {job.vehicle_year} {job.vehicle_make} {job.vehicle_model} · {job.calibration_label}
          </div>
          <a href={`https://maps.google.com/?q=${encodeURIComponent(job.job_address)}`} target="_blank" rel="noreferrer"
            style={{ display: "inline-block", marginTop: 6, fontSize: 13, color: "var(--accent-ink)" }}>
            {job.job_address} →
          </a>
          {(job.customer_first_name || job.notes) && (
            <div style={{ marginTop: 8, fontSize: 13 }}>
              {job.customer_first_name && (
                <div>{[job.customer_first_name, job.customer_last_name].filter(Boolean).join(" ")}</div>
              )}
              {job.notes && (
                <div style={{ whiteSpace: "pre-wrap", marginTop: job.customer_first_name ? 4 : 0 }}
                  data-testid={`job-notes-${job.id}`}>
                  <span className="muted">Notes: </span>{job.notes}
                </div>
              )}
            </div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="font-display" style={{ fontSize: 18, fontWeight: 700 }}>{formatTime(job.scheduled_start)}</div>
          <div className="muted" style={{ fontSize: 12 }}>{job.drive_time_minutes} min drive</div>
          {job.status === "requested" && job.extra_drive_minutes != null && (
            <div className="muted" style={{ fontSize: 12, marginTop: 4, maxWidth: 180 }}>
              About {job.extra_drive_minutes} min extra driving. Day ends about {job.later_finish_minutes} min later.
            </div>
          )}
          <div className="font-mono" style={{ fontSize: 13, marginTop: 4 }}>${job.price.toFixed(2)}</div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        {onEdit && (
          <button className="btn btn-ghost" onClick={() => onEdit(job)}
            data-testid={`job-edit-${job.id}`}>Edit</button>
        )}
        {onDecide && job.status === "requested" && (
          <>
            <button className="btn btn-primary" onClick={() => onDecide(job.id, true)}
              data-testid={`job-approve-${job.id}`}>Approve</button>
            <button className="btn btn-ghost" onClick={() => onDecide(job.id, false)}
              data-testid={`job-decline-${job.id}`}>Decline</button>
          </>
        )}
        {!job.invoice_id && !job.charged_at && job.payment_status !== "paid" && job.status !== "cancelled" && job.status !== "declined" && (
          <TripFeeControls job={job} onOutside={onOutside} onTripFee={onTripFee} />
        )}
        {job.payment_mode !== "invoice_hold" && !job.charged_at && job.payment_status !== "paid" && (
          <button className="btn btn-ghost" onClick={() => onPayment(job.id, "invoice_hold")}>Invoice this job</button>
        )}
        {job.status === "complete" && job.payment_status !== "paid" && !job.charged_at && (
          <button className="btn btn-primary" onClick={() => onCharge(job.id)}>Charge card now</button>
        )}
        {flow && (
          <button className="btn btn-primary" onClick={() => onStatus(job.id, flow.next)}
            data-testid={`job-action-${job.id}`}>{flow.label}</button>
        )}
        {job.status === "booked" && (
          <>
            <button className="btn btn-ghost" onClick={() => onDispatch(job)}
              data-testid={`job-dispatch-${job.id}`}>Dispatch to Contractor</button>
            <button className="btn btn-ghost" onClick={() => onReschedule(job, "reschedule")}
              data-testid={`job-reschedule-${job.id}`}>Reschedule</button>
            <button className="btn btn-ghost" onClick={() => onReschedule(job, "cancel")}
              data-testid={`job-cancel-${job.id}`}>Cancel</button>
          </>
        )}
        {offer && (
          <>
            <button className="btn btn-ghost" style={{ borderColor: "rgba(16,185,129,0.4)", color: "var(--green)" }}
              onClick={() => onRespond(offer.id, true)} data-testid={`offer-accept-${offer.id}`}>Mark Accepted</button>
            <button className="btn btn-ghost" style={{ borderColor: "rgba(239,68,68,0.4)", color: "var(--red)" }}
              onClick={() => onRespond(offer.id, false)} data-testid={`offer-decline-${offer.id}`}>Mark Declined</button>
          </>
        )}
      </div>
    </div>
  );
}
