import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, formatTime, formatDate, getStoredAuth, jobStatusLabel, phoenixTodayStr } from "../lib/api";
import Brand from "../components/Brand";
import JobEditModal from "../components/JobEditModal";

const ADAS_OPTIONS = [
  { v: "forward_camera", l: "Forward-Facing Camera (most common)", default: "static" },
  { v: "surround_view",  l: "Surround View / 360°",                default: "dual" },
  { v: "radar",          l: "Radar System",                         default: "dynamic" },
  { v: "multi_camera",   l: "Multi-Camera System",                  default: "triple" },
  { v: "tesla",          l: "Tesla",                                 default: "tesla" },
];

// Phoenix is UTC−7 all year. 08:00 local is 15:00 UTC; hours past 23 roll the UTC date.
function phoenixInstant(day, hhmm) {
  const [y, m, d] = day.split("-").map(Number);
  const [hh, mm] = hhmm.split(":").map(Number);
  return new Date(Date.UTC(y, m - 1, d, hh + 7, mm)).toISOString();
}

const CAL_LABELS = {
  static: "Static ADAS Calibration", dynamic: "Dynamic ADAS Calibration",
  dual: "Dual ADAS Calibration", triple: "Triple Camera / Subaru ADAS Calibration",
  tesla: "Tesla ADAS Calibration",
};

export default function PublicBooking() {
  const { token } = useParams();
  const [shop, setShop] = useState(null);
  const [error, setError] = useState(null);
  const [step, setStep] = useState(1);

  const [address, setAddress] = useState("");
  const [zoneInfo, setZoneInfo] = useState(null);
  const [date, setDate] = useState("");
  const [slots, setSlots] = useState([]);
  const [slotsMsg, setSlotsMsg] = useState("");
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [chosenSlot, setChosenSlot] = useState(null);
  const [customTime, setCustomTime] = useState("");
  const isOwner = getStoredAuth()?.role === "owner";
  const [vehicle, setVehicle] = useState({
    customer_first_name: "", customer_last_name: "", year: new Date().getFullYear(), make: "", model: "",
    trim: "", vin: "", adas_system: "forward_camera", notes: "",
  });
  const [calType, setCalType] = useState("static");
  const [notifyPhone, setNotifyPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [invoiceInstead, setInvoiceInstead] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const [bookings, setBookings] = useState([]);
  const [editingBooking, setEditingBooking] = useState(null);

  const loadBookings = useCallback(async () => {
    try {
      const { data } = await api.get(`/public/bookings/${token}`);
      setBookings(data);
    } catch {
      setBookings([]);
    }
  }, [token]);

  useEffect(() => {
    api.get(`/public/shop/${token}`)
      .then(r => { setShop(r.data); setAddress(r.data.address); setNotifyPhone(r.data.contact_phone || ""); })
      .catch(e => setError(e.response?.data?.detail || "Booking link not active"));
    loadBookings();
  }, [token, loadBookings]);
  async function geocodeAddr() {
    if (!address) return;
    const { data } = await api.post("/geocode", { address });
    setZoneInfo(data);
  }

  async function loadSlots(d) {
    setSlotsLoading(true); setSlots([]); setSlotsMsg("");
    try {
      const { data } = await api.post("/public/availability", {
        booking_token: token, job_address: address, date: d,
      });
      setSlots(data.slots);
      if (data.slots.length === 0) setSlotsMsg(data.message || "No availability for this date.");
    } finally { setSlotsLoading(false); }
  }

  function pickAdas(v) {
    const opt = ADAS_OPTIONS.find(o => o.v === v);
    setVehicle({ ...vehicle, adas_system: v });
    if (opt) setCalType(opt.default);
  }

  function priceFor(type) {
    if (!shop) return 0;
    if (shop.pricing_tier === "custom" && shop[`custom_rate_${type}`] != null) return Number(shop[`custom_rate_${type}`]);
    const std = { static: 125, dynamic: 125, dual: 175, triple: 185, tesla: 225 };
    return std[type];
  }

  async function submitBooking() {
    setSubmitting(true);
    try {
      const { data } = await api.post("/public/book", {
        booking_token: token, job_address: address, scheduled_start: chosenSlot.start,
        customer_last_name: vehicle.customer_last_name,
        customer_first_name: vehicle.customer_first_name.trim() || null,
        notes: vehicle.notes.trim() || null,
        year: Number(vehicle.year),
        make: vehicle.make, model: vehicle.model, trim: vehicle.trim || null,
        vin: vehicle.vin || null, adas_system: vehicle.adas_system,
        calibration_type: calType, notification_phone: notifyPhone,
        invoice_instead: invoiceInstead,
      });
      setConfirmation(data);
      loadBookings();
    } catch (e) {
      alert(e.response?.data?.detail || "Booking failed");
    } finally { setSubmitting(false); }
  }

  if (error) {
    return <Center><div className="surface" style={{ padding: 30, maxWidth: 460, textAlign: "center" }}>
      <div className="h2" style={{ marginBottom: 10 }}>Link Not Active</div>
      <div className="muted">{error}</div>
    </div></Center>;
  }
  if (!shop) return <Center><div className="muted">Loading…</div></Center>;
  if (shop.booking_open === false) {
    return <Center><div className="surface" style={{ padding: 30, maxWidth: 480, textAlign: "center" }} data-testid="booking-closed">
      <div className="h2" style={{ marginBottom: 8 }}>Booking isn't open yet</div>
      <div className="muted">{shop.booking_message}</div>
    </div></Center>;
  }

  if (confirmation) {
    const pending = confirmation.requires_approval || confirmation.status === "requested";
    const appointmentDay = new Date(confirmation.scheduled_start).toLocaleDateString("en-CA", { timeZone: "America/Phoenix" });
    const texted = !pending && appointmentDay !== phoenixTodayStr();
    return <Center>
      <div className="surface" style={{ padding: 30, maxWidth: 540, textAlign: "center" }} data-testid="booking-confirmed">
        {!pending && <div style={{ fontSize: 48, color: "var(--green)", marginBottom: 8 }}>✓</div>}
        <div className="h2" style={{ marginBottom: 6 }}>{pending ? "Pending owner approval" : "Booking Confirmed"}</div>
        <div className="muted" style={{ marginBottom: 16 }}>Ref #{confirmation.booking_reference}</div>
        <div className="elevated" style={{ padding: 16, textAlign: "left", fontSize: 14 }}>
          <div>{formatDate(confirmation.scheduled_start)} · {formatTime(confirmation.scheduled_start)}</div>
          <div className="muted" style={{ marginTop: 6 }}>{vehicle.year} {vehicle.make} {vehicle.model}</div>
          <div className="muted">{CAL_LABELS[calType]} · ${confirmation.price.toFixed(2)}</div>
          {pending && (
            <div style={{ marginTop: 8 }} data-testid="booking-pending-note">
              This time is held until the owner approves it.
            </div>
          )}
        </div>
        {texted && (
          <div className="muted" style={{ fontSize: 13, marginTop: 16 }}>A confirmation SMS has been sent to {notifyPhone}.</div>
        )}
      </div>
    </Center>;
  }

  return (
    <div style={{ minHeight: "100vh", padding: "32px 16px", background: "var(--bg-primary)" }}>
      <div style={{ maxWidth: 640, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 4 }}>
          <Brand size={26} />
        </div>
        <div className="muted" style={{ textAlign: "center", marginBottom: 24, fontSize: 14 }}>
          Booking for <b style={{ color: "var(--text-primary)" }}>{shop.name}</b>
        </div>

        <ShopBookings
          bookings={bookings}
          onEdit={setEditingBooking}
          onCancel={async (id) => {
            if (!window.confirm("Cancel this booking? This does not send a message.")) return;
            try {
              await api.post(`/public/bookings/${token}/${id}/cancel`);
              loadBookings();
            } catch (e) {
              const detail = e.response?.data?.detail;
              alert(typeof detail === "string" ? detail : "Could not cancel this booking. Try again.");
            }
          }}
        />
        <JobEditModal open={!!editingBooking} job={editingBooking} token={token}
          onClose={() => setEditingBooking(null)} onDone={loadBookings} />

        {/* Step indicator */}
        <Steps step={step} />

        {step === 1 && (
          <Step title="Where is the vehicle?" sub="If at your shop, confirm the address. If at the customer's location, enter that address.">
            <input className="input" value={address} onChange={e => { setAddress(e.target.value); setZoneInfo(null); }}
              onBlur={geocodeAddr} placeholder="123 Main St, Phoenix, AZ" data-testid="booking-address" />
            {zoneInfo && zoneInfo.in_metro && (
              <div style={{ marginTop: 10, fontSize: 14 }}>
                This address is in our Phoenix service area.
              </div>
            )}
            {zoneInfo && !zoneInfo.in_metro && (
              <div style={{ marginTop: 10, color: "var(--red)", fontSize: 14 }}>
                This address is outside our current service area.
              </div>
            )}
            <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-primary" disabled={!zoneInfo?.in_metro} onClick={() => setStep(2)} data-testid="address-next">Continue →</button>
            </div>
          </Step>
        )}

        {step === 2 && (
          <Step title="Pick a date">
            <input className="input" type="date" value={date}
              min={phoenixTodayStr()}
              max={phoenixTodayStr(new Date(Date.now() + 21 * 86400000))}
              onChange={e => {
                const next = e.target.value;
                setDate(next);
                loadSlots(next);
                if (isOwner && customTime && next) setChosenSlot({ start: phoenixInstant(next, customTime) });
                else setChosenSlot(null);
              }}
              data-testid="booking-date" />
            {slotsLoading && <div className="muted" style={{ marginTop: 12, fontSize: 14 }}>Calculating available times…</div>}
            {slotsMsg && !chosenSlot && <div style={{ marginTop: 12, color: "var(--yellow)", fontSize: 14 }}>{slotsMsg}</div>}
            {slots.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="label">Available times</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))", gap: 8 }}>
                  {slots.map(s => (
                    <button key={s.start} type="button"
                      className={"btn " + (chosenSlot?.start === s.start ? "btn-primary" : "btn-ghost")}
                      onClick={() => { setCustomTime(""); setChosenSlot(s); }} data-testid={`slot-${s.start}`}
                      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, minHeight: 44 }}>
                      <span>{formatTime(s.start)}</span>
                      {s.requires_approval && (
                        <span style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.2 }}>Pending approval</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {isOwner && date && (
              <div style={{ marginTop: 16 }}>
                <label className="label" htmlFor="owner-time">Set a time</label>
                <input id="owner-time" className="input" type="time" value={customTime}
                  onChange={e => {
                    const value = e.target.value;
                    setCustomTime(value);
                    if (value) setChosenSlot({ start: phoenixInstant(date, value) });
                  }}
                  data-testid="owner-custom-time" />
              </div>
            )}
            <NavBtns onBack={() => setStep(1)} onNext={() => setStep(3)} nextDisabled={!chosenSlot} />
          </Step>
        )}

        {step === 3 && (
          <Step title="Vehicle information">
            <Row>
              <Field label="Customer first name">
                <input className="input" value={vehicle.customer_first_name}
                  onChange={e => setVehicle({...vehicle, customer_first_name: e.target.value})}
                  data-testid="vehicle-firstname" />
              </Field>
              <Field label="Customer last name *">
                <input className="input" value={vehicle.customer_last_name}
                  onChange={e => setVehicle({...vehicle, customer_last_name: e.target.value})}
                  data-testid="vehicle-lastname" />
              </Field>
            </Row>
            <Row>
              <Field label="Year *"><input className="input" type="number" min="2010" max="2027"
                value={vehicle.year} onChange={e => setVehicle({...vehicle, year: e.target.value})} data-testid="vehicle-year" /></Field>
              <Field label="Make *"><input className="input" value={vehicle.make}
                onChange={e => setVehicle({...vehicle, make: e.target.value})} data-testid="vehicle-make" /></Field>
            </Row>
            <Row>
              <Field label="Model *"><input className="input" value={vehicle.model}
                onChange={e => setVehicle({...vehicle, model: e.target.value})} data-testid="vehicle-model" /></Field>
              <Field label="Trim"><input className="input" value={vehicle.trim}
                onChange={e => setVehicle({...vehicle, trim: e.target.value})} /></Field>
            </Row>
            <Field label="VIN (17 chars, optional but recommended)">
              <input className="input" value={vehicle.vin} maxLength={17}
                onChange={e => setVehicle({...vehicle, vin: e.target.value.toUpperCase()})} data-testid="vehicle-vin" />
            </Field>
            <Field label="ADAS system type *">
              <select className="input" value={vehicle.adas_system}
                onChange={e => pickAdas(e.target.value)} data-testid="vehicle-adas">
                {ADAS_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </Field>
            <NavBtns onBack={() => setStep(2)} onNext={() => setStep(4)}
              nextDisabled={!vehicle.customer_last_name || !vehicle.year || !vehicle.make || !vehicle.model} />
          </Step>
        )}

        {step === 4 && (
          <Step title="Calibration type & price">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {Object.entries(CAL_LABELS).map(([k, label]) => (
                <button key={k} type="button"
                  className={"btn " + (calType === k ? "btn-primary" : "btn-ghost")}
                  onClick={() => setCalType(k)} style={{ justifyContent: "space-between", width: "100%" }}
                  data-testid={`cal-type-${k}`}>
                  <span>{label}</span>
                  <span className="font-mono">${priceFor(k).toFixed(2)}</span>
                </button>
              ))}
            </div>
            <NavBtns onBack={() => setStep(3)} onNext={() => setStep(5)} />
          </Step>
        )}

        {step === 5 && (
          <Step title="Review & confirm">
            {chosenSlot.requires_approval && (
              <div style={{ fontSize: 14, marginBottom: 12 }} data-testid="review-pending-note">
                Pending owner approval. This time is held until the owner approves it.
              </div>
            )}
            <div className="elevated" style={{ padding: 16, fontSize: 14, marginBottom: 16 }}>
              <SummaryRow k="When" v={`${formatDate(chosenSlot.start)} · ${formatTime(chosenSlot.start)}`} />
              <SummaryRow k="Address" v={address} />
              <SummaryRow k="Vehicle" v={`${vehicle.year} ${vehicle.make} ${vehicle.model}`} />
              <SummaryRow k="Customer" v={[vehicle.customer_first_name, vehicle.customer_last_name].filter(s => s.trim()).join(" ")} />
              <SummaryRow k="Service" v={CAL_LABELS[calType]} />
              <SummaryRow k="Price" v={`$${priceFor(calType).toFixed(2)}`} bold />
            </div>
            <Field label="Notes (optional)">
              <textarea className="input" rows={3} value={vehicle.notes}
                onChange={e => setVehicle({...vehicle, notes: e.target.value})}
                data-testid="booking-notes" />
            </Field>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 14 }}>
              <input type="checkbox" checked={invoiceInstead} onChange={e => setInvoiceInstead(e.target.checked)} data-testid="invoice-instead" />
              <span>Please invoice me instead</span>
            </label>
            <Field label="Notification phone (we'll text status updates here)">
              <input className="input" value={notifyPhone} onChange={e => setNotifyPhone(e.target.value)} data-testid="notify-phone" />
            </Field>
            <NavBtns onBack={() => setStep(4)}
              onNext={submitBooking}
              nextLabel={submitting ? "Booking…" : (chosenSlot.requires_approval ? "Request this time" : "Confirm Booking")}
              nextDisabled={submitting}
              dataTestId="confirm-booking" />
          </Step>
        )}
      </div>
    </div>
  );
}

const Center = ({ children }) => (
  <div style={{ minHeight: "100vh", background: "var(--bg-primary)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
    {children}
  </div>
);
const Step = ({ title, sub, children }) => (
  <div className="surface page-fade" style={{ padding: 24 }}>
    <div className="h2" style={{ marginBottom: sub ? 4 : 16 }}>{title}</div>
    {sub && <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>{sub}</div>}
    {children}
  </div>
);
const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (<div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>);
const SummaryRow = ({ k, v, bold }) => (
  <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
    <span className="muted">{k}</span><span style={{ fontWeight: bold ? 700 : 500 }}>{v}</span>
  </div>
);
const NavBtns = ({ onBack, onNext, nextDisabled, nextLabel = "Continue →", dataTestId }) => (
  <div style={{ marginTop: 20, display: "flex", justifyContent: "space-between" }}>
    <button className="btn btn-ghost" onClick={onBack}>← Back</button>
    <button className="btn btn-primary" onClick={onNext} disabled={nextDisabled} data-testid={dataTestId || "step-next"}>{nextLabel}</button>
  </div>
);
function ShopBookings({ bookings, onEdit, onCancel }) {
  return (
    <section style={{ marginBottom: 24 }} data-testid="your-bookings">
      <h2 className="h3" style={{ marginBottom: 10 }}>Your bookings</h2>
      {bookings.length === 0 ? (
        <div className="surface muted" style={{ padding: 16, textAlign: "center" }}>No upcoming bookings.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {bookings.map((job) => (
            <div key={job.id} className="surface" style={{ padding: 14 }} data-testid={`booking-${job.id}`}>
              <div style={{ fontWeight: 600 }}>
                {job.vehicle_year} {job.vehicle_make} {job.vehicle_model}
              </div>
              <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                {[job.customer_first_name, job.customer_last_name].filter(Boolean).join(" ")}
                {" · "}{formatDate(job.scheduled_start)} · {formatTime(job.scheduled_start)}
              </div>
              <div style={{ fontSize: 13, marginTop: 4 }}>{job.job_address}</div>
              <div style={{ marginTop: 8 }}>
                <span className={`badge badge-${job.status}`} data-testid={`booking-status-${job.id}`}>
                  {jobStatusLabel(job.status)}
                </span>
              </div>
              {job.notes && (
                <div style={{ fontSize: 13, marginTop: 6, whiteSpace: "pre-wrap" }}>{job.notes}</div>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button type="button" className="btn btn-ghost" onClick={() => onEdit(job)}
                  data-testid={`booking-edit-${job.id}`}>Edit</button>
                <button type="button" className="btn btn-ghost" onClick={() => onCancel(job.id)}
                  data-testid={`booking-cancel-${job.id}`}>Cancel booking</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

const Steps = ({ step }) => (
  <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 20 }}>
    {[1,2,3,4,5].map(i => (
      <div key={i} style={{ height: 4, width: 36, borderRadius: 2,
        background: i <= step ? "var(--accent)" : "var(--bg-elevated)" }} />
    ))}
  </div>
);
