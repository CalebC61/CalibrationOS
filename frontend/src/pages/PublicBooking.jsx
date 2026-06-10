import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, formatTime, formatDate, dateStr } from "../lib/api";

const ADAS_OPTIONS = [
  { v: "forward_camera", l: "Forward-Facing Camera (most common)", default: "static" },
  { v: "surround_view",  l: "Surround View / 360°",                default: "dual" },
  { v: "radar",          l: "Radar System",                         default: "dynamic" },
  { v: "multi_camera",   l: "Multi-Camera System",                  default: "triple" },
  { v: "tesla",          l: "Tesla",                                 default: "tesla" },
];

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
  const [vehicle, setVehicle] = useState({
    customer_last_name: "", year: new Date().getFullYear(), make: "", model: "",
    trim: "", vin: "", adas_system: "forward_camera",
  });
  const [calType, setCalType] = useState("static");
  const [notifyPhone, setNotifyPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState(null);

  useEffect(() => {
    api.get(`/public/shop/${token}`)
      .then(r => { setShop(r.data); setAddress(r.data.address); setNotifyPhone(r.data.contact_phone || ""); })
      .catch(e => setError(e.response?.data?.detail || "Booking link not active"));
  }, [token]);

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
        customer_last_name: vehicle.customer_last_name, year: Number(vehicle.year),
        make: vehicle.make, model: vehicle.model, trim: vehicle.trim || null,
        vin: vehicle.vin || null, adas_system: vehicle.adas_system,
        calibration_type: calType, notification_phone: notifyPhone,
      });
      setConfirmation(data);
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

  if (confirmation) {
    return <Center>
      <div className="surface" style={{ padding: 30, maxWidth: 540, textAlign: "center" }} data-testid="booking-confirmed">
        <div style={{ fontSize: 48, color: "var(--green)", marginBottom: 8 }}>✓</div>
        <div className="h2" style={{ marginBottom: 6 }}>Booking Confirmed</div>
        <div className="muted" style={{ marginBottom: 16 }}>Ref #{confirmation.booking_reference}</div>
        <div className="elevated" style={{ padding: 16, textAlign: "left", fontSize: 14 }}>
          <div>{formatDate(confirmation.scheduled_start)} · {formatTime(confirmation.scheduled_start)}</div>
          <div className="muted" style={{ marginTop: 6 }}>{vehicle.year} {vehicle.make} {vehicle.model}</div>
          <div className="muted">{CAL_LABELS[calType]} · ${confirmation.price.toFixed(2)}</div>
        </div>
        <div className="muted" style={{ fontSize: 13, marginTop: 16 }}>A confirmation SMS has been sent to {notifyPhone}.</div>
      </div>
    </Center>;
  }

  return (
    <div style={{ minHeight: "100vh", padding: "32px 16px", background: "var(--bg-primary)" }}>
      <div style={{ maxWidth: 640, margin: "0 auto" }}>
        <div className="font-display" style={{ fontSize: 28, fontWeight: 800, textAlign: "center", marginBottom: 4 }}>
          CALIBRATION<span style={{ color: "var(--accent)" }}>OS</span>
        </div>
        <div className="muted" style={{ textAlign: "center", marginBottom: 24, fontSize: 14 }}>
          Booking for <b style={{ color: "var(--text-primary)" }}>{shop.name}</b>
        </div>

        {/* Step indicator */}
        <Steps step={step} />

        {step === 1 && (
          <Step title="Where is the vehicle?" sub="If at your shop, confirm the address. If at the customer's location, enter that address.">
            <input className="input" value={address} onChange={e => { setAddress(e.target.value); setZoneInfo(null); }}
              onBlur={geocodeAddr} placeholder="123 Main St, Phoenix, AZ" data-testid="booking-address" />
            {zoneInfo && zoneInfo.in_metro && (
              <div style={{ marginTop: 10, fontSize: 14 }}>
                This job is in our <span className={`badge badge-${zoneInfo.zone}`}>{zoneInfo.zone === "west" ? "West Valley" : "East Valley"}</span> service area.
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
              min={dateStr(new Date())}
              max={dateStr(new Date(Date.now() + 21 * 86400000))}
              onChange={e => { setDate(e.target.value); loadSlots(e.target.value); }}
              data-testid="booking-date" />
            {slotsLoading && <div className="muted" style={{ marginTop: 12, fontSize: 14 }}>Calculating available times…</div>}
            {slotsMsg && <div style={{ marginTop: 12, color: "var(--yellow)", fontSize: 14 }}>{slotsMsg}</div>}
            {slots.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="label">Available times</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))", gap: 8 }}>
                  {slots.map(s => (
                    <button key={s.start} type="button"
                      className={"btn " + (chosenSlot?.start === s.start ? "btn-primary" : "btn-ghost")}
                      onClick={() => setChosenSlot(s)} data-testid={`slot-${s.start}`}>
                      {formatTime(s.start)}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <NavBtns onBack={() => setStep(1)} onNext={() => setStep(3)} nextDisabled={!chosenSlot} />
          </Step>
        )}

        {step === 3 && (
          <Step title="Vehicle information">
            <Field label="Customer last name *">
              <input className="input" value={vehicle.customer_last_name}
                onChange={e => setVehicle({...vehicle, customer_last_name: e.target.value})}
                data-testid="vehicle-lastname" />
            </Field>
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
            <div className="elevated" style={{ padding: 16, fontSize: 14, marginBottom: 16 }}>
              <SummaryRow k="When" v={`${formatDate(chosenSlot.start)} · ${formatTime(chosenSlot.start)}`} />
              <SummaryRow k="Address" v={address} />
              <SummaryRow k="Vehicle" v={`${vehicle.year} ${vehicle.make} ${vehicle.model}`} />
              <SummaryRow k="Customer" v={vehicle.customer_last_name} />
              <SummaryRow k="Service" v={CAL_LABELS[calType]} />
              <SummaryRow k="Price" v={`$${priceFor(calType).toFixed(2)}`} bold />
            </div>
            <Field label="Notification phone (we'll text status updates here)">
              <input className="input" value={notifyPhone} onChange={e => setNotifyPhone(e.target.value)} data-testid="notify-phone" />
            </Field>
            <NavBtns onBack={() => setStep(4)}
              onNext={submitBooking} nextLabel={submitting ? "Booking…" : "Confirm Booking"} nextDisabled={submitting}
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
const Steps = ({ step }) => (
  <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 20 }}>
    {[1,2,3,4,5].map(i => (
      <div key={i} style={{ height: 4, width: 36, borderRadius: 2,
        background: i <= step ? "var(--accent)" : "var(--bg-elevated)" }} />
    ))}
  </div>
);
