import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../lib/api";

const CAL_TYPES = [
  { value: "static",  label: "Static ADAS" },
  { value: "dynamic", label: "Dynamic ADAS" },
  { value: "dual",    label: "Dual ADAS" },
  { value: "triple",  label: "Triple / Subaru" },
  { value: "tesla",   label: "Tesla ADAS" },
];

const ADAS_SYSTEMS = [
  { value: "forward_camera", label: "Forward Camera" },
  { value: "surround_view",  label: "Surround View" },
  { value: "radar",          label: "Radar" },
  { value: "multi_camera",   label: "Multi-Camera" },
  { value: "tesla",          label: "Tesla" },
  { value: "other",          label: "Other" },
];

// Convert ISO datetime → "YYYY-MM-DDTHH:MM" local for the datetime-local input
function isoToLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Convert "YYYY-MM-DDTHH:MM" local → ISO with timezone
function localInputToIso(local) {
  if (!local) return null;
  const d = new Date(local);
  return d.toISOString();
}

export default function JobEditModal({ open, job, onClose, onSaved }) {
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !job) return;
    setForm({
      customer_last_name: job.customer_last_name || "",
      vehicle_year: job.vehicle_year || "",
      vehicle_make: job.vehicle_make || "",
      vehicle_model: job.vehicle_model || "",
      vehicle_trim: job.vehicle_trim || "",
      vehicle_vin: job.vehicle_vin || "",
      adas_system: job.adas_system || "forward_camera",
      calibration_type: job.calibration_type || "static",
      job_address: job.job_address || "",
      scheduled_start: isoToLocalInput(job.scheduled_start),
      notification_phone: job.notification_phone || "",
      notification_email: job.notification_email || "",
      price: job.price != null ? String(job.price) : "",
      notes: job.notes || "",
    });
    setError("");
  }, [open, job]);

  if (!open || !job) return null;

  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

  async function save() {
    setBusy(true); setError("");
    try {
      const payload = {
        customer_last_name: form.customer_last_name || null,
        vehicle_year: form.vehicle_year ? Number(form.vehicle_year) : null,
        vehicle_make: form.vehicle_make || null,
        vehicle_model: form.vehicle_model || null,
        vehicle_trim: form.vehicle_trim || null,
        vehicle_vin: form.vehicle_vin || null,
        adas_system: form.adas_system,
        calibration_type: form.calibration_type,
        job_address: form.job_address || null,
        scheduled_start: localInputToIso(form.scheduled_start),
        notification_phone: form.notification_phone || null,
        notification_email: form.notification_email || null,
        price: form.price !== "" ? Number(form.price) : null,
        notes: form.notes || null,
      };
      await api.patch(`/jobs/${job.id}`, payload);
      onSaved?.();
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return createPortal(
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 50,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }} data-testid="job-edit-modal">
      <div onClick={e => e.stopPropagation()} className="surface page-fade"
        style={{
          padding: 0, maxWidth: 640, width: "100%",
          maxHeight: "calc(100vh - 32px)", display: "flex", flexDirection: "column",
        }}>
        <div style={{ padding: "20px 24px 14px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
            <h2 className="h2" style={{ margin: 0 }}>Edit Job</h2>
            <span className={`badge badge-${job.zone}`}>{job.zone}</span>
          </div>
          <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
            {job.shop_name} · Booking #{job.id.slice(0, 8).toUpperCase()}
          </div>
        </div>

        <div style={{ padding: "16px 24px", overflowY: "auto", flex: 1 }}>
        <Section title="Customer & Vehicle">
          <Grid cols={2}>
            <Field label="Customer last name">
              <input className="input" value={form.customer_last_name}
                onChange={e => set("customer_last_name", e.target.value)}
                data-testid="edit-customer-last-name" />
            </Field>
            <Field label="VIN">
              <input className="input" value={form.vehicle_vin}
                onChange={e => set("vehicle_vin", e.target.value.toUpperCase())}
                placeholder="Optional" data-testid="edit-vin" />
            </Field>
            <Field label="Year">
              <input className="input" type="number" value={form.vehicle_year}
                onChange={e => set("vehicle_year", e.target.value)}
                data-testid="edit-year" />
            </Field>
            <Field label="Make">
              <input className="input" value={form.vehicle_make}
                onChange={e => set("vehicle_make", e.target.value)}
                data-testid="edit-make" />
            </Field>
            <Field label="Model">
              <input className="input" value={form.vehicle_model}
                onChange={e => set("vehicle_model", e.target.value)}
                data-testid="edit-model" />
            </Field>
            <Field label="Trim">
              <input className="input" value={form.vehicle_trim}
                onChange={e => set("vehicle_trim", e.target.value)}
                placeholder="Optional" data-testid="edit-trim" />
            </Field>
          </Grid>
        </Section>

        <Section title="Calibration">
          <Grid cols={2}>
            <Field label="ADAS system">
              <select className="input" value={form.adas_system}
                onChange={e => set("adas_system", e.target.value)}
                data-testid="edit-adas-system">
                {ADAS_SYSTEMS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
            <Field label="Calibration type (sets default price)">
              <select className="input" value={form.calibration_type}
                onChange={e => set("calibration_type", e.target.value)}
                data-testid="edit-calibration-type">
                {CAL_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
            <Field label="Price ($)">
              <input className="input" type="number" step="0.01" value={form.price}
                onChange={e => set("price", e.target.value)}
                data-testid="edit-price" />
            </Field>
            <Field label="Notes">
              <input className="input" value={form.notes}
                onChange={e => set("notes", e.target.value)}
                placeholder="Optional" data-testid="edit-notes" />
            </Field>
          </Grid>
        </Section>

        <Section title="Schedule & Location">
          <Field label="Job address (changing this re-geocodes + may change zone)">
            <input className="input" value={form.job_address}
              onChange={e => set("job_address", e.target.value)}
              data-testid="edit-job-address" />
          </Field>
          <Field label="Scheduled start (local time)">
            <input className="input" type="datetime-local" value={form.scheduled_start}
              onChange={e => set("scheduled_start", e.target.value)}
              data-testid="edit-scheduled-start" />
          </Field>
        </Section>

        <Section title="Notifications">
          <Grid cols={2}>
            <Field label="Phone">
              <input className="input" value={form.notification_phone}
                onChange={e => set("notification_phone", e.target.value)}
                placeholder="+1480..." data-testid="edit-phone" />
            </Field>
            <Field label="Email">
              <input className="input" type="email" value={form.notification_email}
                onChange={e => set("notification_email", e.target.value)}
                placeholder="customer@example.com" data-testid="edit-email" />
            </Field>
          </Grid>
        </Section>

        {error && (
          <div style={{ color: "var(--red)", fontSize: 13, marginTop: 10 }} data-testid="job-edit-error">
            {error}
          </div>
        )}
        </div>

        <div style={{
          display: "flex", gap: 8, justifyContent: "flex-end",
          padding: "14px 24px", borderTop: "1px solid var(--border)",
          background: "var(--bg-elevated)",
        }}>
          <button className="btn btn-ghost" onClick={onClose} data-testid="job-edit-cancel">Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={busy} data-testid="job-edit-save">
            {busy ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div className="muted" style={{
        fontSize: 11, fontWeight: 600, textTransform: "uppercase",
        letterSpacing: "0.12em", marginBottom: 8,
      }}>{title}</div>
      <div className="elevated" style={{ padding: 14 }}>
        {children}
      </div>
    </div>
  );
}

function Grid({ cols, children }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 12 }}>
      {children}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="label" style={{ marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}
