import { useEffect, useState } from "react";
import { api } from "../lib/api";

const CAL_TYPES = [
  ["static", "Static ADAS Calibration"],
  ["dynamic", "Dynamic ADAS Calibration"],
  ["dual", "Dual ADAS Calibration"],
  ["triple", "Triple Camera / Subaru ADAS Calibration"],
  ["tesla", "Tesla ADAS Calibration"],
];

function phoenixDateAndTime(iso) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Phoenix",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (type) => parts.find((part) => part.type === type).value;
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    time: `${get("hour")}:${get("minute")}`,
  };
}

function phoenixInstant(day, hhmm) {
  const [year, month, date] = day.split("-").map(Number);
  const [hour, minute] = hhmm.split(":").map(Number);
  return new Date(Date.UTC(year, month - 1, date, hour + 7, minute)).toISOString();
}

const emptyForm = {
  job_address: "", customer_first_name: "", customer_last_name: "",
  notification_phone: "", notification_email: "",
  vehicle_year: "", vehicle_make: "", vehicle_model: "", vehicle_vin: "",
  calibration_type: "static", price: "", date: "", time: "", zone: "east", notes: "",
};

export default function JobEditModal({ open, job, onClose, onDone, token }) {
  const ownerFields = !token;
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || !job) return;
    const when = job.scheduled_start ? phoenixDateAndTime(job.scheduled_start) : { date: "", time: "" };
    setForm({
      job_address: job.job_address || "",
      customer_first_name: job.customer_first_name || "",
      customer_last_name: job.customer_last_name || "",
      notification_phone: job.notification_phone || "",
      notification_email: job.notification_email || "",
      vehicle_year: job.vehicle_year ?? "",
      vehicle_make: job.vehicle_make || "",
      vehicle_model: job.vehicle_model || "",
      vehicle_vin: job.vehicle_vin || "",
      calibration_type: job.calibration_type || "static",
      price: job.price ?? "",
      date: when.date,
      time: when.time,
      zone: job.zone || "east",
      notes: job.notes || "",
    });
    setError(null);
  }, [open, job]);

  if (!open || !job) return null;

  function set(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    if (!form.job_address.trim() || !form.customer_last_name.trim() || !form.vehicle_make.trim()
      || !form.vehicle_model.trim() || !form.date || !form.time) {
      setError("Address, customer last name, vehicle, and time are required.");
      return;
    }
    const payload = {
      job_address: form.job_address.trim(),
      customer_first_name: form.customer_first_name.trim() || null,
      customer_last_name: form.customer_last_name.trim(),
      notification_phone: form.notification_phone.trim() || null,
      notification_email: form.notification_email.trim() || null,
      vehicle_year: Number(form.vehicle_year),
      vehicle_make: form.vehicle_make.trim(),
      vehicle_model: form.vehicle_model.trim(),
      vehicle_vin: form.vehicle_vin.trim() || null,
      calibration_type: form.calibration_type,
      scheduled_start: phoenixInstant(form.date, form.time),
      notes: form.notes.trim() || null,
    };
    if (ownerFields) {
      payload.price = Number(form.price);
      payload.zone = form.zone;
    }
    setSaving(true);
    setError(null);
    try {
      const url = token
        ? `/public/bookings/${token}/${job.id}`
        : `/jobs/${job.id}`;
      await api.patch(url, payload);
      onDone?.();
      onClose();
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save these changes. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: 16,
    }} data-testid="job-edit-modal">
      <div onClick={(event) => event.stopPropagation()} className="surface page-fade" style={{
        padding: 24, maxWidth: 560, width: "100%", maxHeight: "90vh", overflow: "auto",
      }}>
        <h2 className="h2" style={{ marginBottom: 4 }}>Edit booking</h2>
        <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
          Saving updates this job only. It does not send a message.
        </div>
        <Field label="Address *">
          <input className="input" value={form.job_address} onChange={(e) => set("job_address", e.target.value)} data-testid="edit-address" />
        </Field>
        <Row>
          <Field label="First name">
            <input className="input" value={form.customer_first_name} onChange={(e) => set("customer_first_name", e.target.value)} data-testid="edit-first-name" />
          </Field>
          <Field label="Last name *">
            <input className="input" value={form.customer_last_name} onChange={(e) => set("customer_last_name", e.target.value)} data-testid="edit-last-name" />
          </Field>
        </Row>
        <Row>
          <Field label="Phone">
            <input className="input" value={form.notification_phone} onChange={(e) => set("notification_phone", e.target.value)} data-testid="edit-phone" />
          </Field>
          <Field label="Email">
            <input className="input" value={form.notification_email} onChange={(e) => set("notification_email", e.target.value)} data-testid="edit-email" />
          </Field>
        </Row>
        <Row>
          <Field label="Year *">
            <input className="input" type="number" value={form.vehicle_year} onChange={(e) => set("vehicle_year", e.target.value)} data-testid="edit-year" />
          </Field>
          <Field label="Make *">
            <input className="input" value={form.vehicle_make} onChange={(e) => set("vehicle_make", e.target.value)} data-testid="edit-make" />
          </Field>
        </Row>
        <Row>
          <Field label="Model *">
            <input className="input" value={form.vehicle_model} onChange={(e) => set("vehicle_model", e.target.value)} data-testid="edit-model" />
          </Field>
          <Field label="VIN">
            <input className="input" maxLength={17} value={form.vehicle_vin} onChange={(e) => set("vehicle_vin", e.target.value.toUpperCase())} data-testid="edit-vin" />
          </Field>
        </Row>
        <Field label="Service *">
          <select className="input" value={form.calibration_type} onChange={(e) => set("calibration_type", e.target.value)} data-testid="edit-service">
            {CAL_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
        <Row>
          <Field label="Date *">
            <input className="input" type="date" value={form.date} onChange={(e) => set("date", e.target.value)} data-testid="edit-date" />
          </Field>
          <Field label="Time (Phoenix) *">
            <input className="input" type="time" value={form.time} onChange={(e) => set("time", e.target.value)} data-testid="edit-time" />
          </Field>
        </Row>
        {ownerFields && (
          <Row>
            <Field label="Price *">
              <input className="input" type="number" min="0" step="0.01" value={form.price} onChange={(e) => set("price", e.target.value)} data-testid="edit-price" />
            </Field>
            <Field label="Zone *">
              <select className="input" value={form.zone} onChange={(e) => set("zone", e.target.value)} data-testid="edit-zone">
                <option value="west">West Valley</option>
                <option value="east">East Valley</option>
              </select>
            </Field>
          </Row>
        )}
        <Field label="Notes">
          <textarea className="input" rows={3} value={form.notes} onChange={(e) => set("notes", e.target.value)} data-testid="edit-notes" />
        </Field>
        {error && <div style={{ color: "var(--red)", fontSize: 13, marginBottom: 12 }} data-testid="edit-error">{error}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Close</button>
          <button type="button" className="btn btn-primary" onClick={save} disabled={saving} data-testid="edit-save">
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>
);
