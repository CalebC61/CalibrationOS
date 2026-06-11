import { useEffect, useState, useCallback } from "react";
import { api, formatTime, todayStr, dateStr } from "../lib/api";
import Shell from "../components/Shell";
import DispatchModal from "../components/DispatchModal";
import RouteMap from "../components/RouteMap";
import RescheduleCancelModal from "../components/RescheduleCancelModal";
import JobEditModal from "../components/JobEditModal";
import TomorrowStrip from "../components/TomorrowStrip";

const STATUS_FLOW = {
  booked: { next: "driving", label: "Start Driving" },
  driving: { next: "on_site", label: "I've Arrived" },
  on_site: { next: "complete", label: "Complete Job" },
};

export default function Dashboard() {
  const [date, setDate] = useState(todayStr());
  const [jobs, setJobs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState({ count: 0, alerts: [] });
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [offers, setOffers] = useState([]);
  const [dispatchTarget, setDispatchTarget] = useState(null);
  const [rescheduleTarget, setRescheduleTarget] = useState(null); // { job, mode: 'reschedule' | 'cancel' }
  const [editTarget, setEditTarget] = useState(null);
  const [dragOver, setDragOver] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [reorderPending, setReorderPending] = useState(false);

  const load = useCallback(async () => {
    if (dragging || reorderPending) return;  // don't clobber optimistic state mid-drag
    try {
      const [j, s, a, o] = await Promise.all([
        api.get(`/jobs?date_str=${date}`),
        api.get(`/dashboard/summary?date_str=${date}`),
        api.get(`/notifications/new-bookings`),
        api.get(`/contractor-offers`),
      ]);
      setJobs(j.data); setSummary(s.data); setAlerts(a.data); setOffers(o.data);
    } catch (e) { console.error(e); }
  }, [date, dragging, reorderPending]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  async function markSeen() {
    await api.post("/notifications/mark-seen");
    setAlerts({ count: 0, alerts: [] });
    setAlertsOpen(false);
  }
  async function setStatus(jobId, status) {
    if (status === "complete") {
      const ok = window.confirm("Complete this job? This will generate a draft Xero invoice (mocked).");
      if (!ok) return;
      await api.post(`/jobs/${jobId}/complete`, { result: "pass", notes: null });
    } else {
      await api.post(`/jobs/${jobId}/status`, { status });
    }
    load();
  }
  async function manualRespond(offerId, accept) {
    await api.post(`/contractor-offers/${offerId}/respond`, { accept });
    load();
  }

  const newJobIds = new Set(alerts.alerts.map(a => a.job_id));
  const offerByJob = Object.fromEntries(offers.filter(o => o.status === "pending").map(o => [o.job_id, o]));

  const west = jobs.filter(j => j.zone === "west").sort((a,b) => a.scheduled_start.localeCompare(b.scheduled_start));
  const east = jobs.filter(j => j.zone === "east").sort((a,b) => a.scheduled_start.localeCompare(b.scheduled_start));

  function shiftDate(days) {
    const d = new Date(date + "T00:00:00");
    d.setDate(d.getDate() + days);
    setDate(dateStr(d));
  }

  async function handleDrop(zone, draggedId, targetIdx) {
    const zoneJobs = zone === "west" ? west : east;
    const dragged = zoneJobs.find(j => j.id === draggedId);
    if (!dragged) return;
    const currentIdx = zoneJobs.findIndex(j => j.id === draggedId);
    if (currentIdx === targetIdx) { setDragOver(null); return; }

    // Build the new ordering
    const reordered = zoneJobs.filter(j => j.id !== draggedId);
    reordered.splice(targetIdx, 0, dragged);
    const orderedIds = reordered.map(j => j.id);

    // OPTIMISTIC UPDATE: shuffle scheduled_start times within the zone so the visual order
    // matches immediately. Real backend recompute happens server-side via Distance Matrix.
    const optimistic = jobs.map(j => {
      if (j.zone !== zone) return j;
      const newPos = orderedIds.indexOf(j.id);
      if (newPos < 0) return j;
      // Take the existing start times in original order, reassign by new position
      const originalStarts = zoneJobs.map(x => x.scheduled_start);
      const originalEnds = zoneJobs.map(x => x.scheduled_end);
      return {
        ...j,
        scheduled_start: originalStarts[newPos],
        scheduled_end: originalEnds[newPos],
        sequence_order: newPos + 1,
        _reordering: true,
      };
    });
    setJobs(optimistic);
    setDragOver(null);
    setReorderPending(true);

    try {
      const { data } = await api.post("/jobs/reorder", { zone, date, ordered_job_ids: orderedIds });
      // Replace the just-updated jobs with the backend-authoritative values (real drive times)
      if (data && data.jobs) {
        setJobs(prev => prev.map(j => {
          const upd = data.jobs.find(u => u.id === j.id);
          if (!upd) return { ...j, _reordering: false };
          return {
            ...j,
            scheduled_start: upd.scheduled_start,
            scheduled_end: upd.scheduled_end,
            drive_time_minutes: upd.drive_time_minutes,
            sequence_order: upd.sequence_order,
            _reordering: false,
          };
        }));
      }
    } catch (e) {
      alert(e.response?.data?.detail || "Reorder failed — reverting");
      // Revert: trigger a fresh load
      setReorderPending(false);
      load();
      return;
    }
    setReorderPending(false);
  }

  return (
    <Shell>
      {alerts.count > 0 && (
        <div className="page-fade" style={{ marginBottom: 16, position: "relative" }} data-testid="new-bookings-banner">
          <button onClick={() => setAlertsOpen(o => !o)} data-testid="new-bookings-pill"
            style={{ display: "inline-flex", alignItems: "center", gap: 10,
              background: "var(--accent-dim)", color: "var(--accent)",
              border: "1px solid var(--border-active)", borderRadius: 999,
              padding: "8px 16px", fontWeight: 600, fontSize: 14, cursor: "pointer" }}>
            <span className="pulse-dot" style={{ width: 8, height: 8, borderRadius: 999, background: "var(--accent)" }} />
            <span data-testid="new-bookings-count">{alerts.count}</span> new booking{alerts.count === 1 ? "" : "s"} since you last looked
            <span style={{ opacity: 0.7, fontSize: 12 }}>{alertsOpen ? "▲" : "▼"}</span>
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

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20, flexWrap: "wrap", gap: 16 }}>
        <div>
          <div className="muted" style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase" }}>Dispatch board</div>
          <h1 className="h1" style={{ margin: "4px 0" }}>
            {new Date(date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </h1>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <button className="btn btn-ghost" onClick={() => shiftDate(-1)} data-testid="prev-day">← Prev</button>
            <button className="btn btn-ghost" onClick={() => setDate(todayStr())} data-testid="today-btn">Today</button>
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

      {jobs.length > 0 && (
        <section style={{ marginBottom: 24 }}>
          <div className="h3" style={{ marginBottom: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Route Map</span>
            <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>Numbered by sequence · Orange = West · Blue = East</span>
          </div>
          <RouteMap jobs={[...west, ...east]} />
        </section>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 16, marginBottom: 20 }}>
        <ZonePanel title="West Valley" subtitle="8:00 AM – 2:00 PM" zone="west" jobs={west} onStatus={setStatus}
          headerClass="zone-header-west" newJobIds={newJobIds} offerByJob={offerByJob}
          onDispatch={setDispatchTarget} onRespond={manualRespond}
          onReschedule={(job, mode) => setRescheduleTarget({ job, mode })}
          onEdit={setEditTarget}
          dragOver={dragOver} setDragOver={setDragOver} onDrop={handleDrop}
          dragging={dragging} setDragging={setDragging} />
        <ZonePanel title="East Valley" subtitle="2:30 PM – 7:00 PM" zone="east" jobs={east} onStatus={setStatus}
          headerClass="zone-header-east" newJobIds={newJobIds} offerByJob={offerByJob}
          onDispatch={setDispatchTarget} onRespond={manualRespond}
          onReschedule={(job, mode) => setRescheduleTarget({ job, mode })}
          onEdit={setEditTarget}
          dragOver={dragOver} setDragOver={setDragOver} onDrop={handleDrop}
          dragging={dragging} setDragging={setDragging} />
      </div>

      <DispatchModal open={!!dispatchTarget} job={dispatchTarget}
        onClose={() => setDispatchTarget(null)} onDone={load} />
      <RescheduleCancelModal open={!!rescheduleTarget} job={rescheduleTarget?.job}
        mode={rescheduleTarget?.mode}
        onClose={() => setRescheduleTarget(null)} onDone={load} />
      <JobEditModal open={!!editTarget} job={editTarget}
        onClose={() => setEditTarget(null)} onSaved={load} />
      <TomorrowStrip baseDate={date} />
    </Shell>
  );
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

function ZonePanel({ title, subtitle, zone, jobs, onStatus, headerClass, newJobIds, offerByJob,
                    onDispatch, onRespond, onReschedule, onEdit, dragOver, setDragOver, onDrop, dragging, setDragging }) {
  return (
    <section data-testid={`zone-panel-${zone}`}>
      <div className={`zone-header ${headerClass}`}>
        <span>{title}</span>
        <span style={{ fontSize: 12, opacity: 0.8 }}>{subtitle} · {jobs.length} jobs</span>
      </div>
      {jobs.length === 0 && (
        <div className="surface muted" style={{ padding: 20, textAlign: "center" }}>No jobs in this zone yet.</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {jobs.map((j, idx) => (
          <JobCard key={j.id} job={j} index={idx + 1} onStatus={onStatus}
            isNew={newJobIds?.has(j.id)} offer={offerByJob?.[j.id]}
            onDispatch={onDispatch} onRespond={onRespond} onReschedule={onReschedule}
            onEdit={onEdit}
            zone={zone} dropIndex={idx}
            isDragOver={dragOver?.zone === zone && dragOver?.idx === idx}
            onDragOver={(e) => { e.preventDefault(); setDragOver({ zone, idx }); }}
            onDragLeave={() => setDragOver(null)}
            onDragStartHandler={(e) => {
              e.dataTransfer.setData("text/plain", j.id);
              e.dataTransfer.effectAllowed = "move";
              setDragging(true);
            }}
            onDragEndHandler={() => { setDragging(false); setDragOver(null); }}
            onHandleDrop={(e) => {
              e.preventDefault();
              const draggedId = e.dataTransfer.getData("text/plain");
              setDragging(false);
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

function JobCard({ job, index, onStatus, isNew, offer, onDispatch, onRespond, onReschedule, onEdit,
                   zone, dropIndex, isDragOver, onDragOver, onDragLeave, onHandleDrop,
                   onDragStartHandler, onDragEndHandler }) {
  const flow = STATUS_FLOW[job.status];
  const isLocked = job.status === "complete" || job.status === "cancelled";
  const openEdit = () => { if (!isLocked && onEdit) onEdit(job); };
  return (
    <div
      className={"card-job" + (isNew ? " card-job-new" : "") + (isDragOver ? " card-job-dropzone" : "") + (job.is_at_risk ? " card-job-at-risk" : "") + (job._reordering ? " card-job-reordering" : "")}
      draggable={!isLocked}
      onDragStart={onDragStartHandler || ((e) => e.dataTransfer.setData("text/plain", job.id))}
      onDragEnd={onDragEndHandler}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onHandleDrop}
      data-testid={`job-card-${job.id}`}
    >
      <div
        onClick={openEdit}
        style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12,
                 cursor: isLocked ? "default" : "pointer" }}
        title={isLocked ? "" : "Click to edit"}
        data-testid={`job-card-body-${job.id}`}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
            <span className="drag-handle font-mono" style={{
              background: "var(--bg-elevated)", padding: "2px 10px", borderRadius: 6,
              fontSize: 12, fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 4,
              cursor: isLocked ? "default" : "grab",
            }} title={isLocked ? "Locked" : "Drag to reorder"}>
              {!isLocked && <span style={{ color: "var(--text-muted)", fontSize: 11 }}>⋮⋮</span>}
              #{index}
            </span>
            <span className={`badge badge-${job.status}`}>{job.status.replace(/_/g, " ")}</span>
            {isNew && <span className="badge" style={{ background: "var(--accent-dim)", color: "var(--accent)", border: "1px solid var(--border-active)" }} data-testid="badge-new">NEW</span>}
            {job.invoice_status === "draft" && <span className="badge badge-draft">Invoice: Draft</span>}
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
            onClick={(e) => e.stopPropagation()}
            style={{ display: "inline-block", marginTop: 6, fontSize: 13, color: "var(--accent)" }}>
            {job.job_address} →
          </a>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="font-display" style={{ fontSize: 18, fontWeight: 700 }}>{formatTime(job.scheduled_start)}</div>
          <div className="muted" style={{ fontSize: 12 }}>{job.drive_time_minutes} min drive</div>
          <div className="font-mono" style={{ fontSize: 13, marginTop: 4 }}>${job.price.toFixed(2)}</div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
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
