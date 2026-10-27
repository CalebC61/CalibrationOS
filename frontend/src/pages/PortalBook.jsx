import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { phoenixTodayStr } from "../lib/api";
import { portalApi, getPortalAuth } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";

const ADAS = [
  { v: "forward_camera", l: "Forward-Facing Camera", default: "static" },
  { v: "surround_view", l: "Surround View / 360°", default: "dual" },
  { v: "radar", l: "Radar System", default: "dynamic" },
  { v: "multi_camera", l: "Multi-Camera", default: "triple" },
  { v: "tesla", l: "Tesla", default: "tesla" },
];
const LABELS = {
  static: "Static ADAS Calibration", dynamic: "Dynamic ADAS Calibration",
  dual: "Dual ADAS Calibration", triple: "Triple Camera / Subaru", tesla: "Tesla ADAS",
};
const fmt = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

export default function PortalBook() {
  const auth = getPortalAuth();
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [shop, setShop] = useState(null);
  const [address, setAddress] = useState("");
  const [zoneInfo, setZoneInfo] = useState(null);
  const [date, setDate] = useState("");
  const [slots, setSlots] = useState([]);
  const [slotsMsg, setSlotsMsg] = useState("");
  const [chosen, setChosen] = useState(null);
  const [veh, setVeh] = useState({ customer_last_name: "", year: new Date().getFullYear(),
    make: "", model: "", trim: "", vin: "", adas_system: "forward_camera" });
  const [calType, setCalType] = useState("static");
  const [notifyPhone, setNotifyPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState(null);

  useEffect(() => {
    portalApi.get("/portal/me").then(r => {
      setShop(r.data.shop);
      setAddress(r.data.shop.address);
      setNotifyPhone(r.data.shop.contact_phone || "");
    });
  }, []);

  if (!auth?.has_payment_method) {
    return <PortalShell>
      <div className="surface" style={{ padding: 24, textAlign: "center", maxWidth: 500, margin: "40px auto" }}>
        <div className="h2" style={{ marginBottom: 8 }}>Card required to book</div>
        <div className="muted" style={{ marginBottom: 16 }}>Per Terms, a card must be on file before scheduling calibrations.</div>
        <button className="btn btn-primary" onClick={() => nav("/portal/settings")} data-testid="goto-add-card">Add Card →</button>
      </div>
    </PortalShell>;
  }
  if (!shop) return <PortalShell><div className="muted">Loading…</div></PortalShell>;

  async function geo() {
    const { data } = await portalApi.post("/geocode", { address });
    setZoneInfo(data);
  }
  async function loadSlots(d) {
    setSlots([]); setSlotsMsg("");
    const { data } = await portalApi.post("/public/availability", {
      booking_token: shop.booking_link_token, job_address: address, date: d,
    });
    setSlots(data.slots);
    if (data.slots.length === 0) setSlotsMsg(data.message || "No slots available.");
  }
  function pickAdas(v) {
    const opt = ADAS.find(o => o.v === v);
    setVeh({...veh, adas_system: v});
    if (opt) setCalType(opt.default);
  }
  function priceFor(t) {
    if (shop.pricing_tier === "custom" && shop[`custom_rate_${t}`] != null) return Number(shop[`custom_rate_${t}`]);
    return ({static: 125, dynamic: 125, dual: 175, triple: 185, tesla: 225})[t];
  }
  async function submit() {
    setSubmitting(true);
    try {
      const { data } = await portalApi.post("/portal/book", {
        booking_token: shop.booking_link_token, job_address: address,
        scheduled_start: chosen.start, customer_last_name: veh.customer_last_name,
        year: Number(veh.year), make: veh.make, model: veh.model,
        trim: veh.trim || null, vin: veh.vin || null,
        adas_system: veh.adas_system, calibration_type: calType,
        notification_phone: notifyPhone,
      });
      setConfirmation(data);
    } catch (e) { alert(e.response?.data?.detail || "Booking failed"); }
    finally { setSubmitting(false); }
  }

  if (confirmation) return <PortalShell>
    <div className="surface" style={{ padding: 30, maxWidth: 560, margin: "20px auto", textAlign: "center" }} data-testid="portal-confirm">
      <div style={{ fontSize: 48, color: "var(--green)" }}>✓</div>
      <div className="h2">Booking Confirmed</div>
      <div className="muted">Ref #{confirmation.booking_reference}</div>
      <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => nav("/portal/jobs")}>View My Jobs</button>
    </div>
  </PortalShell>;

  return (
    <PortalShell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Book a Calibration</h1>
      <div style={{ maxWidth: 640 }}>
        {step === 1 && (
          <Card title="Where is the vehicle?" sub="Defaults to your shop address. Override if at customer's location.">
            <input className="input" value={address} onChange={e => { setAddress(e.target.value); setZoneInfo(null); }}
              onBlur={geo} data-testid="b-addr" />
            {zoneInfo?.in_metro && <div style={{ marginTop: 10, fontSize: 14 }}>
              Service zone: <span className={`badge badge-${zoneInfo.zone}`}>{zoneInfo.zone === "west" ? "West Valley" : "East Valley"}</span>
            </div>}
            {zoneInfo && !zoneInfo.in_metro && <div style={{ color: "var(--red)", marginTop: 10, fontSize: 14 }}>Outside our service area.</div>}
            <Nav onNext={() => setStep(2)} nextDisabled={!zoneInfo?.in_metro} />
          </Card>
        )}
        {step === 2 && (
          <Card title="Pick a date">
            <input className="input" type="date" value={date}
              min={phoenixTodayStr()}
              max={phoenixTodayStr(new Date(Date.now() + 21 * 86400000))}
              onChange={e => { setDate(e.target.value); loadSlots(e.target.value); }} data-testid="b-date" />
            {slotsMsg && <div className="muted" style={{ marginTop: 10, fontSize: 14, color: "var(--yellow)" }}>{slotsMsg}</div>}
            {slots.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="label">Available times</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 8 }}>
                  {slots.map(s => (
                    <button key={s.start} type="button"
                      className={"btn " + (chosen?.start === s.start ? "btn-primary" : "btn-ghost")}
                      onClick={() => setChosen(s)} data-testid={`b-slot-${s.start}`}>{fmt(s.start)}</button>
                  ))}
                </div>
              </div>
            )}
            <Nav onBack={() => setStep(1)} onNext={() => setStep(3)} nextDisabled={!chosen} />
          </Card>
        )}
        {step === 3 && (
          <Card title="Vehicle">
            <F label="Customer last name *"><input className="input" value={veh.customer_last_name}
              onChange={e => setVeh({...veh, customer_last_name: e.target.value})} data-testid="b-ln" /></F>
            <R><F label="Year *"><input className="input" type="number" value={veh.year}
              onChange={e => setVeh({...veh, year: e.target.value})} /></F>
              <F label="Make *"><input className="input" value={veh.make}
                onChange={e => setVeh({...veh, make: e.target.value})} /></F></R>
            <R><F label="Model *"><input className="input" value={veh.model}
              onChange={e => setVeh({...veh, model: e.target.value})} /></F>
              <F label="Trim"><input className="input" value={veh.trim}
                onChange={e => setVeh({...veh, trim: e.target.value})} /></F></R>
            <F label="VIN"><input className="input" maxLength={17} value={veh.vin}
              onChange={e => setVeh({...veh, vin: e.target.value.toUpperCase()})} /></F>
            <F label="ADAS system *">
              <select className="input" value={veh.adas_system} onChange={e => pickAdas(e.target.value)}>
                {ADAS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </F>
            <Nav onBack={() => setStep(2)} onNext={() => setStep(4)}
              nextDisabled={!veh.customer_last_name || !veh.year || !veh.make || !veh.model} />
          </Card>
        )}
        {step === 4 && (
          <Card title="Calibration type & confirm">
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {Object.entries(LABELS).map(([k, l]) => (
                <button key={k} type="button"
                  className={"btn " + (calType === k ? "btn-primary" : "btn-ghost")}
                  onClick={() => setCalType(k)} style={{ justifyContent: "space-between", width: "100%" }}>
                  <span>{l}</span><span className="font-mono">${priceFor(k).toFixed(2)}</span>
                </button>
              ))}
            </div>
            <div className="elevated" style={{ padding: 14, fontSize: 14 }}>
              <Row k="When" v={`${new Date(chosen.start).toLocaleDateString()} · ${fmt(chosen.start)}`} />
              <Row k="Vehicle" v={`${veh.year} ${veh.make} ${veh.model}`} />
              <Row k="Customer" v={veh.customer_last_name} />
              <Row k="Total" v={`$${priceFor(calType).toFixed(2)}`} bold />
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Charge to card on file occurs on the same day as job completion.
              </div>
            </div>
            <Nav onBack={() => setStep(3)} onNext={submit}
              nextLabel={submitting ? "Booking…" : "Confirm Booking"} nextDisabled={submitting} />
          </Card>
        )}
      </div>
    </PortalShell>
  );
}

const Card = ({ title, sub, children }) => (
  <div className="surface page-fade" style={{ padding: 24, marginBottom: 16 }}>
    <h2 className="h2" style={{ marginBottom: sub ? 4 : 16 }}>{title}</h2>
    {sub && <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>{sub}</div>}
    {children}
  </div>
);
const F = ({ label, children }) => <div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>;
const R = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Row = ({ k, v, bold }) => (
  <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
    <span className="muted">{k}</span><span style={{ fontWeight: bold ? 700 : 500 }}>{v}</span>
  </div>
);
const Nav = ({ onBack, onNext, nextDisabled, nextLabel = "Continue →" }) => (
  <div style={{ marginTop: 20, display: "flex", justifyContent: "space-between" }}>
    {onBack ? <button className="btn btn-ghost" onClick={onBack}>← Back</button> : <span />}
    <button className="btn btn-primary" onClick={onNext} disabled={nextDisabled} data-testid="b-next">{nextLabel}</button>
  </div>
);
