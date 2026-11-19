import { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { api, formatTime, formatDate, phoenixTodayStr, dateStr, getStoredAuth, isOnDayBoard, isPhoenixToday, jobStatusLabel } from "../lib/api";
import { dayBoardTotals, fresherJob, jobLooksPaid, mergeJobList } from "../lib/jobState";
import { useRefreshOnShow } from "../lib/refreshOnShow";
import Shell from "../components/Shell";
import RouteMap from "../components/RouteMap";
import RescheduleCancelModal from "../components/RescheduleCancelModal";
import TomorrowStrip from "../components/TomorrowStrip";
import JobEditModal from "../components/JobEditModal";
import WarrantyBadge from "../components/WarrantyBadge";

function boardDateFromSearch() {
  if (typeof window === "undefined") return "";
  const value = new URLSearchParams(window.location.search).get("date") || "";
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : "";
}

function boardJobFromSearch() {
  if (typeof window === "undefined") return "";
  const value = new URLSearchParams(window.location.search).get("job") || "";
  return /^[\w-]+$/.test(value) ? value : "";
}

function phoenixDayOf(iso) {
  if (!iso) return "";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return phoenixTodayStr(when);
}

const STATUS_FLOW = {
  booked: { next: "driving", label: "Start Driving" },
  driving: { next: "on_site", label: "I've Arrived" },
  on_site: { next: "complete", label: "Complete Job" },
};

export default function Dashboard() {
  const isOwner = getStoredAuth()?.role === "owner";
  const [date, setDate] = useState(() => boardDateFromSearch() || phoenixTodayStr());
  const [jobs, setJobs] = useState([]);
  const [techs, setTechs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState({ count: 0, alerts: [] });
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [rescheduleTarget, setRescheduleTarget] = useState(null); // { job, mode: 'reschedule' | 'cancel' }
  const [dragOver, setDragOver] = useState(null);
  const [refreshingMap, setRefreshingMap] = useState(false);
  const [refreshResult, setRefreshResult] = useState(null);
  const [refreshError, setRefreshError] = useState(null);
  const [editTarget, setEditTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [closedOpen, setClosedOpen] = useState(false);
  const [closedJobs, setClosedJobs] = useState([]);
  const [closedStatus, setClosedStatus] = useState("idle");
  const [closedError, setClosedError] = useState("");
  const [notice, setNotice] = useState("");
  const removedJobIds = useRef(new Set());
  const silencedAlertJobs = useRef(new Set());
  const loadGen = useRef(0);
  const followedPin = useRef(false);
  const scrolledJob = useRef("");

  const load = useCallback(async () => {
    const gen = ++loadGen.current;
    try {
      const [j, s, a] = await Promise.all([
        api.get(`/jobs?date_str=${date}`),
        api.get(`/dashboard/summary?date_str=${date}`),
        api.get(`/notifications/new-bookings`),
      ]);
      if (gen !== loadGen.current) return;
      let visible = (j.data || []).filter(job => !removedJobIds.current.has(job.id));
      const pin = boardJobFromSearch();
      if (pin && !removedJobIds.current.has(pin) && !visible.some(job => job.id === pin)) {
        try {
          const one = await api.get(`/jobs/${pin}`);
          if (gen !== loadGen.current) return;
          const extra = one.data;
          const jobDay = phoenixDayOf(extra?.scheduled_start);
          if (extra?.id && isOnDayBoard(extra) && jobDay) {
            if (jobDay !== date && !followedPin.current) {
              followedPin.current = true;
              setDate(jobDay);
              return;
            }
            if (jobDay === date) visible = [...visible, extra];
          }
        } catch {
          // The day list stands when the single job cannot be read.
        }
      }
      if (gen !== loadGen.current) return;
      const alertRows = (a.data?.alerts || []).filter(alert =>
        !removedJobIds.current.has(alert.job_id) && !silencedAlertJobs.current.has(alert.job_id)
      );
      setJobs(current => mergeJobList(current, visible)); setSummary(s.data); setAlerts({ count: alertRows.length, alerts: alertRows });
      try {
        const t = await api.get("/routing-techs");
        if (gen !== loadGen.current) return;
        setTechs(t.data || []);
      } catch { setTechs([]); }
    } catch (e) { console.error(e); }
  }, [date]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  useEffect(() => {
    const jobId = boardJobFromSearch();
    if (!jobId) return;
    const token = `${date}:${jobId}`;
    if (scrolledJob.current === token) return;
    const node = document.querySelector(`[data-testid="job-card-${jobId}"]`);
    if (!node) return;
    scrolledJob.current = token;
    if (typeof node.scrollIntoView === "function") node.scrollIntoView({ block: "center" });
  }, [jobs, date]);
  useRefreshOnShow(load);

  function showJob(job) {
    if (!job?.id) return;
    loadGen.current += 1;
    setJobs(current => current.map(item => item.id === job.id ? fresherJob(item, job) : item));
  }

  function report(err, fallback) {
    const detail = err?.response?.data?.detail;
    setNotice(typeof detail === "string" && detail ? detail : fallback);
  }

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
      report(err, "Could not change how this job is billed.");
    }
  }
  async function setOutside(jobId, enabled) {
    try {
      await api.post(`/jobs/${jobId}/outside-service-area`, { enabled });
      load();
    } catch (err) {
      report(err, "Could not update the trip fee.");
    }
  }
  async function chargeTripFee(jobId, reason) {
    try {
      await api.post(`/jobs/${jobId}/trip-fee`, { reason });
      load();
    } catch (err) {
      report(err, "Could not charge the trip fee.");
    }
  }
  async function retryXero(jobId) {
    try {
      const { data } = await api.post(`/jobs/${jobId}/retry-xero-draft`);
      showJob(data?.job);
      load();
    } catch (err) {
      report(err, "Could not retry the Xero draft.");
    }
  }
  async function chargeNow(jobId) {
    try {
      const { data } = await api.post(`/jobs/${jobId}/charge-card`);
      showJob(data?.job);
      load();
    } catch (err) {
      report(err, "The card was not charged.");
      load();
    }
  }
  async function setStatus(jobId, status) {
    try {
      await api.post(`/jobs/${jobId}/status`, { status });
      load();
    } catch (err) {
      report(err, "Could not update this job.");
    }
  }
  async function completeJob(jobId, body) {
    try {
      const { data } = await api.post(`/jobs/${jobId}/complete`, body);
      showJob(data?.job);
    } catch (err) {
      report(err, "Could not complete the job.");
      return;
    }
    load();
  }
  function silenceBookingAlert(jobId) {
    if (!jobId) return;
    silencedAlertJobs.current.add(jobId);
    setAlerts(current => {
      const next = (current.alerts || []).filter(alert => alert.job_id !== jobId);
      return { count: next.length, alerts: next };
    });
  }
  async function loadClosed() {
    setClosedStatus("loading");
    setClosedError("");
    try {
      const { data } = await api.get("/jobs?closed=true");
      if (!Array.isArray(data)) throw new Error("not a list");
      setClosedJobs(data.filter(row =>
        !removedJobIds.current.has(row.id)
        && (row.status === "cancelled" || row.status === "declined")
      ));
      setClosedStatus("ready");
    } catch {
      setClosedStatus("error");
      setClosedError("Couldn't load cancelled and declined jobs.");
    }
  }
  function toggleClosed() {
    if (closedOpen) {
      setClosedOpen(false);
      return;
    }
    setClosedOpen(true);
    loadClosed();
  }
  function finishScheduleChange() {
    if (rescheduleTarget?.mode === "cancel") silenceBookingAlert(rescheduleTarget.job?.id);
    load();
  }
  function askDelete(job) {
    setDeleteError("");
    setDeleteTarget(job);
  }
  async function confirmDelete() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await api.delete(`/jobs/${deleteTarget.id}`);
      const removed = deleteTarget;
      removedJobIds.current.add(removed.id);
      setJobs(current => current.filter(job => job.id !== removed.id));
      setClosedJobs(current => current.filter(job => job.id !== removed.id));
      setAlerts(current => {
        const next = (current.alerts || []).filter(alert => alert.job_id !== removed.id);
        return { count: next.length, alerts: next };
      });
      setSummary(current => {
        if (!current) return current;
        const remaining = jobs.filter(job => job.id !== removed.id);
        return { ...current, ...dayBoardTotals(remaining) };
      });
      setDeleteTarget(null);
    } catch (err) {
      setDeleteError(err.response?.data?.detail || "Could not delete this job.");
    } finally {
      setDeleting(false);
    }
  }
  async function decideApproval(jobId, approve) {
    try {
      await api.post(`/jobs/${jobId}/${approve ? "approve" : "decline"}`);
      if (!approve) silenceBookingAlert(jobId);
      load();
    } catch (e) {
      report(e, "Could not update that request.");
    }
  }
  const newJobIds = new Set(alerts.alerts.map(a => a.job_id));
  const dayJobs = jobs.filter(isOnDayBoard);
  const totals = dayBoardTotals(dayJobs);

  const routingTechs = techs.filter(t => t.role !== "contractor" && t.routes_jobs !== false && t.is_active !== false);
  const colorById = Object.fromEntries(routingTechs.map(t => [t.id, t.color || "#FF5F1F"]));
  const nameById = Object.fromEntries(routingTechs.map(t => [t.id, t.name]));
  const painted = dayJobs.map(j => ({
    ...j,
    technician_color: j.technician_color || colorById[j.technician_id] || "#FF5F1F",
    technician_name: j.technician_name || nameById[j.technician_id] || "",
  }));
  const focusId = boardJobFromSearch();
  const ownerPanelId = (routingTechs.find(t => t.role === "owner") || routingTechs[0])?.id;
  function jobsFor(tech) {
    return painted
      .filter(j => {
        const known = routingTechs.some(t => t.id === j.technician_id);
        if (known) return j.technician_id === tech.id;
        return tech.id === ownerPanelId;
      })
      .sort((a, b) => String(a.scheduled_start).localeCompare(String(b.scheduled_start)));
  }
  const panels = (routingTechs.length ? routingTechs : [{ id: "unassigned", name: "Today", role: "owner", color: "#FF5F1F", home_address: "" }])
    .map(tech => ({ tech, jobs: tech.id === "unassigned" ? painted.slice().sort((a, b) => String(a.scheduled_start).localeCompare(String(b.scheduled_start))) : jobsFor(tech) }));

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
      report(e, "Reorder failed");
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
                        <div className="font-mono" style={{ fontSize: 12, marginTop: 4 }} data-testid={`new-booking-time-${a.job_id}`}>{formatTime(a.scheduled_start)}</div>
                        {(a.status_label || a.status) && (
                          <div style={{ fontSize: 12, marginTop: 2 }} data-testid={`new-booking-status-${a.job_id}`}>
                            {a.status_label || jobStatusLabel(a.status)}
                          </div>
                        )}
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
          Shop emails are on hold — view held emails
        </Link>
      )}
      {notice && (
        <div role="alert" data-testid="board-notice" style={{
          display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12,
          marginBottom: 12, padding: "10px 12px", borderRadius: 10,
          background: "rgba(239, 68, 68, 0.12)", color: "#FCA5A5", fontSize: 14,
        }}>
          <span>{notice}</span>
          <button type="button" className="btn btn-ghost" onClick={() => setNotice("")}
            data-testid="board-notice-dismiss" style={{ padding: "4px 10px", fontSize: 13 }}>Dismiss</button>
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, flexWrap: "wrap", gap: 16 }}>
        <div>
          <h1 className="h1" style={{ margin: "4px 0" }}>
            {new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </h1>
          <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
            <button className="btn btn-ghost" onClick={() => shiftDate(-1)} data-testid="prev-day">← Prev</button>
            <button className="btn btn-ghost" onClick={() => setDate(phoenixTodayStr())} data-testid="today-btn">Today</button>
            <button className="btn btn-ghost" onClick={() => shiftDate(1)} data-testid="next-day">Next →</button>
            {isOwner && (
              <button type="button" className={closedOpen ? "btn btn-primary" : "btn btn-ghost"}
                aria-pressed={closedOpen} onClick={toggleClosed} data-testid="closed-jobs-toggle">
                Cancelled & declined
              </button>
            )}
          </div>
        </div>
        {summary && (
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            <Metric label="Jobs" value={totals.job_count} />
            <Metric label="Revenue" value={`$${Number(totals.revenue || 0).toFixed(0)}`} />
            <Metric label="Est. Miles" value={totals.estimated_miles} />
            <Metric label="Done By" value={totals.done_by ? formatTime(totals.done_by) : "—"} />
          </div>
        )}
      </div>

      {closedOpen ? (
        <ClosedJobs jobs={closedJobs} status={closedStatus} error={closedError}
          onRetry={loadClosed} onDelete={askDelete} />
      ) : (
      <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 16, marginBottom: 20 }}>
        {panels.map(({ tech, jobs: techJobs }) => (
          <ZonePanel key={tech.id}
            title={tech.name || "Technician"}
            subtitle={routingTechs.length <= 1 ? "Whole valley" : (tech.home_address || "Home base")}
            zone={tech.id} jobs={techJobs} onStatus={setStatus} onComplete={completeJob}
            onPayment={setPaymentMode} onCharge={chargeNow}
            onOutside={setOutside} onTripFee={chargeTripFee} onRetryXero={retryXero}
            accent={tech.color || "#FF5F1F"}
            newJobIds={newJobIds}
            onReschedule={(job, mode) => setRescheduleTarget({ job, mode })}
            onEdit={isOwner ? setEditTarget : null}
            onDelete={isOwner ? askDelete : null}
            onDecide={isOwner ? decideApproval : null}
            focusId={focusId}
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
      </>
      )}

      <JobEditModal open={!!editTarget} job={editTarget}
        onClose={() => setEditTarget(null)} onDone={load} />
      <DeleteJobDialog job={deleteTarget} busy={deleting} error={deleteError}
        onCancel={() => { if (!deleting) setDeleteTarget(null); }}
        onConfirm={confirmDelete} />
      <RescheduleCancelModal open={!!rescheduleTarget} job={rescheduleTarget?.job}
        mode={rescheduleTarget?.mode}
        onClose={() => setRescheduleTarget(null)} onDone={finishScheduleChange} />
      <TomorrowStrip baseDate={date} />
    </Shell>
  );
}

function closedText(value) {
  const text = value === null || value === undefined ? "" : String(value).trim();
  return text || "—";
}

function closedCustomer(job) {
  return closedText([job.customer_first_name, job.customer_last_name].filter(Boolean).join(" "));
}

function closedVehicle(job) {
  return closedText([job.vehicle_year, job.vehicle_make, job.vehicle_model].filter(part => part !== null && part !== undefined && String(part).trim() !== "").join(" "));
}

function closedStatusLabel(status) {
  if (status === "cancelled") return "Cancelled";
  if (status === "declined") return "Declined";
  return jobStatusLabel(status);
}

function ClosedJobs({ jobs, status, error, onRetry, onDelete }) {
  return (
    <section aria-labelledby="closed-jobs-title" data-testid="closed-jobs" style={{ marginBottom: 20 }}>
      <h2 id="closed-jobs-title" className="h3" style={{ margin: "0 0 4px" }}>Cancelled & declined</h2>
      <p className="muted" style={{ fontSize: 14, margin: "0 0 12px" }}>
        Jobs taken off the day board. The date is when the job was scheduled.
      </p>
      {status === "loading" && jobs.length === 0 && (
        <div className="muted" style={{ fontSize: 14 }} data-testid="closed-jobs-loading">Loading cancelled and declined jobs.</div>
      )}
      {status === "error" && (
        <div className="surface" style={{ padding: 16 }} role="alert">
          <div style={{ color: "var(--red)", fontSize: 14, marginBottom: 10 }}>{error}</div>
          <button type="button" className="btn btn-ghost" onClick={onRetry} data-testid="closed-jobs-retry">Try again</button>
        </div>
      )}
      {status === "ready" && jobs.length === 0 && (
        <div className="surface muted" style={{ padding: 16 }} data-testid="closed-jobs-empty">No cancelled or declined jobs.</div>
      )}
      {jobs.length > 0 && (
        <div className="surface closed-board">
          <div className="closed-head">
            <span>Date</span>
            <span>Shop</span>
            <span>Vehicle</span>
            <span>Customer</span>
            <span>Status</span>
            <span>Reason</span>
            <span />
          </div>
          {jobs.map(row => (
            <div key={row.id} className="closed-row" data-testid={`closed-job-${row.id}`}>
              <div>
                <span className="closed-k">Date</span>
                <span>{row.scheduled_start ? formatDate(row.scheduled_start) : "—"}</span>
              </div>
              <div>
                <span className="closed-k">Shop</span>
                <span>{closedText(row.shop_name)}</span>
              </div>
              <div>
                <span className="closed-k">Vehicle</span>
                <span>{closedVehicle(row)}</span>
              </div>
              <div>
                <span className="closed-k">Customer</span>
                <span>{closedCustomer(row)}</span>
              </div>
              <div>
                <span className="closed-k">Status</span>
                <span className={`badge badge-${row.status}`}>{closedStatusLabel(row.status)}</span>
                <WarrantyBadge job={row} />
              </div>
              <div>
                <span className="closed-k">Reason</span>
                <span data-testid={`closed-reason-${row.id}`}>{closedText(row.cancellation_reason)}</span>
              </div>
              <div className="closed-action">
                <button type="button" className="btn btn-danger" onClick={() => onDelete(row)}
                  data-testid={`job-delete-${row.id}`}
                  style={{ color: "#FCA5A5", borderColor: "rgba(252, 165, 165, 0.45)" }}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function jobTitle(job) {
  const vehicle = [job.vehicle_year, job.vehicle_make, job.vehicle_model]
    .filter(part => part !== null && part !== undefined && String(part).trim() !== "")
    .join(" ");
  return vehicle || job.calibration_label || "This job";
}

function jobDeleteWarnings(job) {
  const lines = [];
  const xero = job.xero_invoice_number || job.xero_invoice_id;
  if (xero) {
    lines.push(`This job has Xero draft ${xero}; deleting the job does not delete it in Xero`);
  }
  const stripeId = job.stripe_invoice_id
    || (String(job.invoice_id || "").startsWith("in_") ? job.invoice_id : "");
  if (stripeId) {
    lines.push(`This job has Stripe invoice ${stripeId}; deleting the job does not delete it in Stripe`);
  }
  const late = job.stripe_late_fee_invoice_id;
  if (late && late !== stripeId) {
    lines.push(`This job has Stripe invoice ${late}; deleting the job does not delete it in Stripe`);
  }
  return lines;
}

function DeleteJobDialog({ job, busy, error, onCancel, onConfirm }) {
  if (!job) return null;
  const warnings = jobDeleteWarnings(job);
  return (
    <div
      onClick={onCancel}
      onKeyDown={(e) => { if (e.key === "Escape") onCancel(); }}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 50,
        display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
      }}
      data-testid="job-delete-dialog"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="job-delete-title"
        onClick={(e) => e.stopPropagation()}
        className="surface page-fade"
        style={{ padding: 24, maxWidth: 480, width: "100%" }}
      >
        <h2 id="job-delete-title" className="h2" style={{ marginBottom: 12 }}>
          Are you sure you want to delete this job?
        </h2>
        <div className="elevated" style={{ padding: 12, marginBottom: 16, fontSize: 14 }}>
          <div data-testid="job-delete-name" style={{ fontWeight: 600 }}>{jobTitle(job)}</div>
          <div data-testid="job-delete-shop">{job.shop_name}</div>
          <div data-testid="job-delete-date" className="muted">
            {job.scheduled_start ? formatDate(job.scheduled_start) : "—"}
          </div>
        </div>
        {warnings.map(line => (
          <p key={line} data-testid="job-delete-warning" style={{ color: "#FCA5A5", fontSize: 14, lineHeight: 1.45, margin: "0 0 10px" }}>
            {line}
          </p>
        ))}
        {error && (
          <div role="alert" style={{ color: "#FCA5A5", fontSize: 14, marginBottom: 12 }}>{error}</div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button type="button" className="btn btn-ghost" onClick={onCancel} autoFocus disabled={busy}
            data-testid="job-delete-cancel">Cancel</button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={busy}
            data-testid="job-delete-confirm"
            style={{ color: "#FCA5A5", borderColor: "rgba(252, 165, 165, 0.45)" }}>
            {busy ? "Deleting…" : "Yes, delete"}
          </button>
        </div>
      </div>
    </div>
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

function ZonePanel({ title, subtitle, zone, jobs, onStatus, onComplete, onPayment, onCharge, onOutside, onTripFee, onRetryXero, accent, newJobIds,
                    onReschedule, onEdit, onDelete, onDecide, focusId, dragOver, setDragOver, onDrop }) {
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
          <JobCard key={j.id} job={j} index={idx + 1} onStatus={onStatus} onComplete={onComplete}
            onPayment={onPayment} onCharge={onCharge}
            onOutside={onOutside} onTripFee={onTripFee} onRetryXero={onRetryXero}
            isNew={newJobIds?.has(j.id)}
            onReschedule={onReschedule} onEdit={onEdit}
            onDelete={onDelete} onDecide={onDecide}
            focused={focusId === j.id}
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

function jobIsPaid(job) {
  return jobLooksPaid(job);
}

function paidAmount(job) {
  const amount = job?.charged_amount != null && job.charged_amount !== ""
    ? Number(job.charged_amount)
    : Number(job?.price || 0) + Number(job?.late_fee || 0);
  return Number.isFinite(amount) ? amount.toFixed(2) : "0.00";
}

function JobCard({ job, index, onStatus, onComplete, onPayment, onCharge, onOutside, onTripFee, onRetryXero, isNew, onReschedule, onEdit, onDelete, onDecide, focused,
                   zone, dropIndex, isDragOver, onDragOver, onDragLeave, onHandleDrop }) {
  const flow = STATUS_FLOW[job.status];
  const travelStep = flow && (flow.next === "driving" || flow.next === "on_site");
  const travelToday = isPhoenixToday(job.scheduled_start);
  const [completeOpen, setCompleteOpen] = useState(false);
  const isLocked = job.status === "complete" || job.status === "cancelled" || job.status === "declined" || job.status === "requested";
  const showTravelWait = Boolean(flow && travelStep && !travelToday);
  const showFlow = Boolean(flow && !showTravelWait);
  const showApprove = Boolean(onDecide && job.status === "requested");
  const showDecline = showApprove;
  const showTrip = !job.warranty_eligible && !job.invoice_id && !job.charged_at && job.payment_status !== "paid" && job.status !== "cancelled" && job.status !== "declined";
  const showInvoice = !job.warranty_eligible && job.payment_mode !== "invoice_hold" && !jobIsPaid(job);
  const showCharge = !job.warranty_eligible && job.status === "complete" && !jobIsPaid(job);
  const showXeroDraft = job.status === "complete" && job.xero_draft_status === "draft" && (job.xero_invoice_number || job.xero_invoice_id);
  const showXeroAttention = job.status === "complete" && job.xero_draft_status === "needs_attention";
  const showSchedule = job.status === "booked";
  const hasMore = Boolean(
    onEdit || onDelete || showDecline || showTrip || showInvoice || showCharge
    || showXeroDraft || showXeroAttention || showSchedule
  );
  return (
    <div
      className={"card-job" + (isNew ? " card-job-new" : "") + (isDragOver ? " card-job-dropzone" : "") + (job.is_at_risk ? " card-job-at-risk" : "") + (focused ? " card-job-focus" : "")}
      aria-current={focused ? "true" : undefined}
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
            <WarrantyBadge job={job} />
            {isNew && <span className="badge" style={{ background: "var(--accent)", color: "#0a0a0a", border: "1px solid var(--accent)" }} data-testid="badge-new">NEW</span>}
            {job.outside_service_area && !job.calibration_not_performed && <span className="badge badge-draft">Outside area +$30</span>}
            {job.calibration_not_performed && <span className="badge badge-draft">Trip fee only</span>}
            {job.payment_mode === "invoice_hold" && !jobIsPaid(job) && <span className="badge badge-draft">Invoice — hold charge</span>}
            {jobIsPaid(job) && (
              <span className="badge badge-complete" data-testid={`job-paid-${job.id}`}>
                Paid ${paidAmount(job)}{job.charged_at ? ` · ${formatTime(job.charged_at)}` : ""}
              </span>
            )}
            {job.payment_status === "payment_failed" && !jobIsPaid(job) && <span className="badge" style={{ background: "rgba(239,68,68,0.15)", color: "var(--red)" }}>Payment failed</span>}
            {job.late_fee ? <span className="badge badge-draft">Late fee ${job.late_fee}</span> : null}
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
      {job.warranty_skip_reason && (
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }} data-testid={`warranty-reason-${job.id}`}>
          {job.warranty_skip_reason}
        </div>
      )}
      <div className="job-next">
        {showApprove && (
          <button className="btn btn-primary" type="button" onClick={() => onDecide(job.id, true)}
            data-testid={`job-approve-${job.id}`}>Approve</button>
        )}
        {showTravelWait && (
          <>
            <button className="btn btn-primary" type="button" disabled
              data-testid={`job-action-${job.id}`}
              style={{ opacity: 0.45 }}>{flow.label}</button>
            <span className="muted" style={{ fontSize: 13, alignSelf: "center" }}
              data-testid={`job-travel-wait-${job.id}`}>Available on the day of the job</span>
          </>
        )}
        {showFlow && (
          <button className="btn btn-primary" type="button" onClick={() => {
            if (flow.next === "complete") setCompleteOpen(true);
            else onStatus(job.id, flow.next);
          }} data-testid={`job-action-${job.id}`}>{flow.label}</button>
        )}
        <Link to={`/field?job=${encodeURIComponent(job.id)}`} className="job-phone"
          data-testid={`job-phone-${job.id}`}>Open on the phone</Link>
      </div>
      {completeOpen && flow?.next === "complete" && (
        <CompleteFields job={job} onSubmit={onComplete} />
      )}
      {hasMore && (
        <details className="job-more" data-testid={`job-more-${job.id}`}>
          <summary className="btn btn-ghost">More</summary>
          <div className="job-more-body">
            {onEdit && (
              <button className="btn btn-ghost" type="button" onClick={() => onEdit(job)}
                data-testid={`job-edit-${job.id}`}>Edit</button>
            )}
            {onDelete && (
              <button type="button" className="btn btn-danger" onClick={() => onDelete(job)}
                data-testid={`job-delete-${job.id}`}
                style={{ color: "#FCA5A5", borderColor: "rgba(252, 165, 165, 0.45)" }}>Delete</button>
            )}
            {showDecline && (
              <button className="btn btn-ghost" type="button" onClick={() => onDecide(job.id, false)}
                data-testid={`job-decline-${job.id}`}>Decline</button>
            )}
            {showSchedule && (
              <>
                <button className="btn btn-ghost" type="button" onClick={() => onReschedule(job, "reschedule")}
                  data-testid={`job-reschedule-${job.id}`}>Reschedule</button>
                <button className="btn btn-ghost" type="button" onClick={() => onReschedule(job, "cancel")}
                  data-testid={`job-cancel-${job.id}`}>Cancel</button>
              </>
            )}
            {showTrip && <TripFeeControls job={job} onOutside={onOutside} onTripFee={onTripFee} />}
            {showInvoice && (
              <button className="btn btn-ghost" type="button" onClick={() => onPayment(job.id, "invoice_hold")}>Invoice this job</button>
            )}
            {showCharge && (
              <button className="btn btn-primary" type="button" onClick={() => onCharge(job.id)} data-testid={`job-charge-${job.id}`}>Charge card now</button>
            )}
            {showXeroAttention && job.xero_attention_reason && (
              <div className="muted" style={{ fontSize: 13, flexBasis: "100%" }} data-testid={`xero-reason-${job.id}`}>
                {job.xero_attention_reason}
              </div>
            )}
            {showXeroDraft && (
              <span className="badge badge-draft" data-testid={`xero-draft-${job.id}`}>
                {job.xero_invoice_url ? (
                  <a href={job.xero_invoice_url} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>
                    Xero draft {job.xero_invoice_number || job.xero_invoice_id}
                  </a>
                ) : `Xero draft ${job.xero_invoice_number || job.xero_invoice_id}`}
              </span>
            )}
            {showXeroAttention && (
              <>
                <span className="badge badge-draft" data-testid={`xero-attention-${job.id}`}>Xero needs attention</span>
                <button className="btn btn-ghost" type="button" onClick={() => onRetryXero(job.id)}
                  data-testid={`xero-retry-${job.id}`}>Retry Xero draft</button>
              </>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

const CAL_TYPES = [
  ["static", "Static"],
  ["dynamic", "Dynamic"],
  ["dual", "Dual"],
  ["triple", "Triple / Subaru"],
  ["tesla", "Tesla"],
];

function isPdfDoc(doc) {
  if (!doc) return false;
  const name = (doc.file_name || "").toLowerCase();
  const type = (doc.content_type || "").toLowerCase();
  return name.endsWith(".pdf") || type.includes("pdf");
}

function canCompleteDraft(doc, calType, popChoice, popAmount) {
  const amount = Number(String(popAmount || "").replace(/[$,]/g, ""));
  const popReady = popChoice === "none" || (popChoice === "amount" && amount > 0);
  return Boolean(isPdfDoc(doc) && calType && popReady);
}

function CompleteFields({ job, onSubmit }) {
  const [calType, setCalType] = useState(job.calibration_type || "");
  const [popChoice, setPopChoice] = useState("");
  const [popAmount, setPopAmount] = useState("");
  const [uploadedDoc, setUploadedDoc] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const ready = canCompleteDraft(uploadedDoc, calType, popChoice, popAmount);

  useEffect(() => {
    let cancel = false;
    api.get(`/jobs/${job.id}/documents`).then(({ data }) => {
      if (cancel) return;
      const pdf = [...(data || [])].reverse().find(isPdfDoc);
      if (pdf) setUploadedDoc(pdf);
    }).catch(() => {});
    return () => { cancel = true; };
  }, [job.id]);

  async function upload(file) {
    if (!file) return;
    setUploading(true);
    setUploadError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(`/jobs/${job.id}/upload-document`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadedDoc(data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setUploadError(typeof detail === "string" && detail ? detail : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function submit() {
    if (!ready || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(job.id, {
        result: "pass",
        notes: null,
        calibration_type: calType,
        pop: popChoice === "none" ? "none" : String(popAmount).trim(),
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }} data-testid={`complete-form-${job.id}`}>
      <label className="label" htmlFor={`dash-cal-${job.id}`}>Calibration type *</label>
      <select id={`dash-cal-${job.id}`} className="input" value={calType} onChange={e => setCalType(e.target.value)}
        data-testid={`dash-cal-type-${job.id}`}>
        <option value="">Choose</option>
        {CAL_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <div style={{ marginTop: 14 }}>
        <div className="label" id={`dash-pop-label-${job.id}`}>POP approved by insurance *</div>
        <div style={{ display: "flex", gap: 8 }} role="group" aria-labelledby={`dash-pop-label-${job.id}`}>
          <button type="button" className={"btn " + (popChoice === "none" ? "btn-primary" : "btn-ghost")}
            style={{ flex: 1 }} onClick={() => setPopChoice("none")} data-testid={`dash-pop-none-${job.id}`}>None</button>
          <button type="button" className={"btn " + (popChoice === "amount" ? "btn-primary" : "btn-ghost")}
            style={{ flex: 1 }} onClick={() => setPopChoice("amount")} data-testid={`dash-pop-amount-${job.id}`}>Dollar amount</button>
        </div>
        {popChoice === "amount" && (
          <input id={`dash-pop-${job.id}`} className="input" style={{ marginTop: 8 }} inputMode="decimal"
            aria-label="POP dollar amount" value={popAmount} placeholder="450.00"
            onChange={e => setPopAmount(e.target.value)} data-testid={`dash-pop-value-${job.id}`} />
        )}
      </div>
      <div style={{ marginTop: 14 }}>
        <div className="label">Signed post-scan PDF *</div>
        {!uploadedDoc ? (
          <label className="btn btn-ghost" style={{ width: "100%", padding: 12, cursor: "pointer", justifyContent: "center" }}>
            {uploading ? "Uploading…" : "Upload PDF"}
            <input type="file" accept="application/pdf,.pdf" style={{ display: "none" }} disabled={uploading}
              onChange={(e) => { if (e.target.files[0]) upload(e.target.files[0]); }}
              data-testid={`doc-upload-${job.id}`} />
          </label>
        ) : (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }} data-testid="doc-uploaded">
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{uploadedDoc.file_name}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                {uploadedDoc.size_bytes ? `${(uploadedDoc.size_bytes / 1024).toFixed(1)} KB` : "PDF"}
              </div>
            </div>
            <button type="button" className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
              onClick={() => setUploadedDoc(null)} data-testid={`doc-remove-${job.id}`}>Replace</button>
          </div>
        )}
        {uploadError && (
          <div role="alert" data-testid={`doc-upload-error-${job.id}`} style={{ color: "#FCA5A5", fontSize: 13, marginTop: 8 }}>{uploadError}</div>
        )}
      </div>
      {!ready && (
        <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>
          Add the signed post-scan PDF, the calibration type, and POP (or None) before completing.
        </div>
      )}
      <button type="button" className="btn btn-primary" style={{ marginTop: 12, opacity: ready && !submitting ? 1 : 0.55 }}
        disabled={!ready || submitting} onClick={submit} data-testid={`dash-complete-${job.id}`}>
        {submitting ? "Submitting…" : "Complete job"}
      </button>
    </div>
  );
}
