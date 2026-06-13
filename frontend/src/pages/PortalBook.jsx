import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { portalApi, getPortalAuth, setPortalAuth } from "../lib/portalApi";
import PortalShell from "../components/PortalShell";

const ADAS = [
  { v: "forward_camera", l: "Forward-Facing Camera", default: "static" },
  { v: "surround_view", l: "Surround View / 360°", default: "dual" },
  { v: "radar", l: "Radar System", default: "dynamic" },
  { v: "multi_camera", l: "Multi-Camera", default: "triple" },
  { v: "tesla", l: "Tesla", default: "tesla" },
];
const CAL_LABELS = {
  static: "Static ADAS Calibration", dynamic: "Dynamic ADAS Calibration",
  dual: "Dual ADAS Calibration", triple: "Triple Camera / Subaru", tesla: "Tesla ADAS",
};
const STANDARD_PRICES = { static: 125, dynamic: 125, dual: 175, triple: 185, tesla: 225 };

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
  const [veh, setVeh] = useState({
    customer_name: "", year: new Date().getFullYear(),
    make: "", model: "", trim: "", vin: "", adas_system: "forward_camera",
  });
  const [calType, setCalType] = useState("static");
  const [jobType, setJobType] = useState("cash");
  const [approvedAmount, setApprovedAmount] = useState("");
  const [notifyPhone, setNotifyPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [dontShowAgain, setDontShowAgain] = useState(false);

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
    if (data.slots.length === 0) setSlotsMsg(data.message || "No slots available — try the next day.");
  }
  function pickAdas(v) {
    const opt = ADAS.find(o => o.v === v);
    setVeh({...veh, adas_system: v});
    if (opt) setCalType(opt.default);
  }
  function flatFee(t) {
    if (shop.pricing_tier === "custom" && shop[`custom_rate_${t}`] != null) return Number(shop[`custom_rate_${t}`]);
    return STANDARD_PRICES[t];
  }

  function onConfirm() {
    if (auth.auth_popup_dismissed) {
      void submit();
    } else {
      setShowAuthModal(true);
    }
  }

  async function submit() {
    setSubmitting(true);
    setShowAuthModal(false);
    try {
      // Persist dismissal preference if checked
      if (dontShowAgain && !auth.auth_popup_dismissed) {
        try {
          await portalApi.post("/portal/dismiss-auth-popup");
          setPortalAuth({ ...auth, auth_popup_dismissed: true });
        } catch (e) { /* non-blocking */ }
      }
      // Split customer_name → last name (legacy field) but keep full string in notes-ish path
      const customer_last_name = veh.customer_name.trim().split(/\s+/).slice(-1)[0] || veh.customer_name.trim();
      const { data } = await portalApi.post("/portal/book", {
        booking_token: shop.booking_link_token, job_address: address,
        scheduled_start: chosen.start,
        customer_last_name,
        year: Number(veh.year), make: veh.make, model: veh.model,
        trim: veh.trim || null, vin: veh.vin || null,
        adas_system: veh.adas_system, calibration_type: calType,
        notification_phone: notifyPhone,
        job_type: jobType,
        insurance_approved_amount: jobType === "insurance" ? Number(approvedAmount) : null,
      });
      setConfirmation(data);
    } catch (e) {
      alert(e.response?.data?.detail || "Booking failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (confirmation) return <PortalShell>
    <div className="surface" style={{ padding: 30, maxWidth: 560, margin: "20px auto", textAlign: "center" }} data-testid="portal-confirm">
      <div style={{ fontSize: 48, color: "var(--green)" }}>✓</div>
      <div className="h2">Booking Confirmed</div>
      <div className="muted" style={{ marginBottom: 16 }}>Ref #{confirmation.booking_reference || confirmation.job_id?.slice(0, 8).toUpperCase()}</div>
      <div className="elevated" style={{ padding: 16, textAlign: "left", marginBottom: 16, fontSize: 14 }}>
        <Row k="When" v={`${new Date(chosen.start).toLocaleDateString()} · ${fmt(chosen.start)}`} />
        <Row k="Vehicle" v={`${veh.year} ${veh.make} ${veh.model}`} />
        <Row k="Customer" v={veh.customer_name} />
        <Row k="Calibration" v={CAL_LABELS[calType]} />
        <Row k="Job type" v={jobType === "cash" ? "Cash Job" : `Insurance ($${Number(approvedAmount).toFixed(2)} approved)`} />
        <Row k="Card charge on completion" v={`$${flatFee(calType).toFixed(2)}`} bold />
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
        <button className="btn btn-ghost" onClick={() => window.location.reload()} data-testid="book-another">Book Another</button>
        <button className="btn btn-primary" onClick={() => nav("/portal/jobs")} data-testid="goto-jobs">View My Jobs</button>
      </div>
    </div>
  </PortalShell>;

  return (
    <PortalShell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Book a Calibration</h1>
      <div style={{ maxWidth: 640 }}>

        {step === 1 && (
          <Card title="Customer & Vehicle" sub="Who's the customer and what are we calibrating?">
            <F label="Customer name *">
              <input className="input" value={veh.customer_name}
                onChange={e => setVeh({...veh, customer_name: e.target.value})}
                placeholder="John Doe" data-testid="b-customer" />
            </F>
            <R3>
              <F label="Year *"><input className="input" type="number" value={veh.year}
                onChange={e => setVeh({...veh, year: e.target.value})} data-testid="b-year" /></F>
              <F label="Make *"><input className="input" value={veh.make}
                onChange={e => setVeh({...veh, make: e.target.value})} data-testid="b-make" /></F>
              <F label="Model *"><input className="input" value={veh.model}
                onChange={e => setVeh({...veh, model: e.target.value})} data-testid="b-model" /></F>
            </R3>
            <F label="VIN (17 characters)">
              <input className="input" maxLength={17} value={veh.vin}
                onChange={e => setVeh({...veh, vin: e.target.value.toUpperCase()})}
                placeholder="Optional but recommended" data-testid="b-vin" />
              {veh.vin && veh.vin.length !== 17 && (
                <div className="muted" style={{ fontSize: 12, color: "var(--yellow)", marginTop: 4 }}>
                  VIN should be exactly 17 characters (currently {veh.vin.length}).
                </div>
              )}
            </F>
            <F label="ADAS system *">
              <select className="input" value={veh.adas_system} onChange={e => pickAdas(e.target.value)}
                data-testid="b-adas">
                {ADAS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </F>
            <Nav onNext={() => setStep(2)}
              nextDisabled={!veh.customer_name.trim() || !veh.year || !veh.make || !veh.model} />
          </Card>
        )}

        {step === 2 && (
          <Card title="Calibration Type" sub="Sets the flat calibration fee charged on completion.">
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {Object.entries(CAL_LABELS).map(([k, l]) => (
                <button key={k} type="button"
                  className={"btn " + (calType === k ? "btn-primary" : "btn-ghost")}
                  onClick={() => setCalType(k)}
                  style={{ justifyContent: "space-between", width: "100%" }}
                  data-testid={`b-cal-${k}`}>
                  <span>{l}</span><span className="font-mono">${flatFee(k).toFixed(2)}</span>
                </button>
              ))}
            </div>
            {shop.pricing_tier === "custom" && (
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                Your shop has a negotiated rate card — prices above reflect your rates.
              </div>
            )}
            <Nav onBack={() => setStep(1)} onNext={() => setStep(3)} />
          </Card>
        )}

        {step === 3 && (
          <Card title="Service Address" sub="Where should we meet the vehicle?">
            <input className="input" value={address}
              onChange={e => { setAddress(e.target.value); setZoneInfo(null); }}
              onBlur={geo} data-testid="b-addr" />
            {zoneInfo?.in_metro && (
              <div style={{ marginTop: 10, fontSize: 14 }}>
                Service zone: <span className={`badge badge-${zoneInfo.zone}`}>
                  {zoneInfo.zone === "west" ? "West Valley · 8 AM–2 PM" : "East Valley · 2:30–7 PM"}
                </span>
              </div>
            )}
            {zoneInfo && !zoneInfo.in_metro && (
              <div style={{ color: "var(--red)", marginTop: 10, fontSize: 14 }}>
                Outside our service area.
              </div>
            )}
            <Nav onBack={() => setStep(2)} onNext={() => setStep(4)} nextDisabled={!zoneInfo?.in_metro} />
          </Card>
        )}

        {step === 4 && (
          <Card title="Job Type *" sub="Required — drives the accounting record.">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <button type="button"
                onClick={() => setJobType("cash")}
                className={"btn " + (jobType === "cash" ? "btn-primary" : "btn-ghost")}
                style={{ justifyContent: "flex-start", width: "100%", padding: 14 }}
                data-testid="b-job-cash">
                <div style={{ textAlign: "left" }}>
                  <div style={{ fontWeight: 700 }}>Cash Job</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                    Vehicle owner pays you directly. No insurance carrier involved.
                  </div>
                </div>
              </button>
              <button type="button"
                onClick={() => setJobType("insurance")}
                className={"btn " + (jobType === "insurance" ? "btn-primary" : "btn-ghost")}
                style={{ justifyContent: "flex-start", width: "100%", padding: 14 }}
                data-testid="b-job-insurance">
                <div style={{ textAlign: "left" }}>
                  <div style={{ fontWeight: 700 }}>Insurance Job</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                    Insurance approves a calibration amount. We invoice you for our flat fee; you keep the spread.
                  </div>
                </div>
              </button>
            </div>

            {jobType === "insurance" && (
              <div style={{ marginTop: 16 }}>
                <F label="Approved calibration amount * ($)">
                  <input className="input" type="number" step="0.01" min="0"
                    value={approvedAmount}
                    onChange={e => setApprovedAmount(e.target.value)}
                    placeholder="e.g. 300.00" data-testid="b-approved-amount" />
                </F>
                <div className="muted" style={{ fontSize: 12 }}>
                  We&apos;ll charge your card the flat fee (${flatFee(calType).toFixed(2)});
                  the rest from the carrier is yours.
                </div>
              </div>
            )}
            <Nav onBack={() => setStep(3)} onNext={() => setStep(5)}
              nextDisabled={jobType === "insurance" && (!approvedAmount || Number(approvedAmount) <= 0)} />
          </Card>
        )}

        {step === 5 && (
          <Card title="Pick a slot" sub={`Slots are zone-locked to ${zoneInfo?.zone === "west" ? "West Valley (8 AM–2 PM)" : "East Valley (2:30–7 PM)"}.`}>
            <input className="input" type="date" value={date}
              min={new Date().toISOString().slice(0,10)}
              max={new Date(Date.now() + 21*86400000).toISOString().slice(0,10)}
              onChange={e => { setDate(e.target.value); loadSlots(e.target.value); }}
              data-testid="b-date" />
            {slotsMsg && <div className="muted" style={{ marginTop: 10, fontSize: 14, color: "var(--yellow)" }}>{slotsMsg}</div>}
            {slots.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="label">Available times</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 8 }}>
                  {slots.map(s => (
                    <button key={s.start} type="button"
                      className={"btn " + (chosen?.start === s.start ? "btn-primary" : "btn-ghost")}
                      onClick={() => setChosen(s)} data-testid={`b-slot-${s.start}`}>
                      {fmt(s.start)}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <Nav onBack={() => setStep(4)} onNext={() => setStep(6)} nextDisabled={!chosen} />
          </Card>
        )}

        {step === 6 && (
          <Card title="Confirm">
            <div className="elevated" style={{ padding: 16, fontSize: 14 }}>
              <Row k="When" v={`${new Date(chosen.start).toLocaleDateString()} · ${fmt(chosen.start)}`} />
              <Row k="Customer" v={veh.customer_name} />
              <Row k="Vehicle" v={`${veh.year} ${veh.make} ${veh.model}${veh.trim ? ` ${veh.trim}` : ""}`} />
              {veh.vin && <Row k="VIN" v={veh.vin} />}
              <Row k="Service address" v={address} />
              <Row k="Calibration" v={`${CAL_LABELS[calType]} · $${flatFee(calType).toFixed(2)}`} />
              <Row k="Job type" v={jobType === "cash" ? "Cash" : `Insurance · approved $${Number(approvedAmount).toFixed(2)}`} />
              <Row k="Card charge on completion" v={`$${flatFee(calType).toFixed(2)}`} bold />
            </div>
            <Nav onBack={() => setStep(5)}
              onNext={onConfirm}
              nextLabel={submitting ? "Booking…" : "Confirm Booking →"}
              nextDisabled={submitting} />
          </Card>
        )}
      </div>

      {showAuthModal && (
        <AuthorizationModal
          onAccept={submit}
          onCancel={() => { setShowAuthModal(false); setSubmitting(false); }}
          dontShowAgain={dontShowAgain}
          setDontShowAgain={setDontShowAgain}
        />
      )}
    </PortalShell>
  );
}

function AuthorizationModal({ onAccept, onCancel, dontShowAgain, setDontShowAgain }) {
  return (
    <div onClick={onCancel} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 60,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }} data-testid="auth-popup">
      <div onClick={e => e.stopPropagation()} className="surface page-fade"
        style={{ padding: 28, maxWidth: 480, width: "100%" }}>
        <div style={{ fontSize: 28, marginBottom: 6 }}>🔐</div>
        <h2 className="h2" style={{ marginBottom: 10 }}>Authorize Charge</h2>
        <div style={{ fontSize: 15, lineHeight: 1.6, marginBottom: 16 }}>
          By scheduling this job, you authorize The Calibration Crew to charge your
          card on file for work completed, per the Terms you signed at registration.
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, marginBottom: 18 }}>
          <input type="checkbox" checked={dontShowAgain}
            onChange={e => setDontShowAgain(e.target.checked)}
            data-testid="auth-dont-show" />
          Don&apos;t show this again
        </label>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onCancel} data-testid="auth-cancel">Cancel</button>
          <button className="btn btn-primary" onClick={onAccept} data-testid="auth-accept">Accept & Book</button>
        </div>
      </div>
    </div>
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
const R3 = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>{children}</div>;
const Row = ({ k, v, bold }) => (
  <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
    <span className="muted">{k}</span><span style={{ fontWeight: bold ? 700 : 500, textAlign: "right", maxWidth: "65%" }}>{v}</span>
  </div>
);
const Nav = ({ onBack, onNext, nextDisabled, nextLabel = "Continue →" }) => (
  <div style={{ marginTop: 20, display: "flex", justifyContent: "space-between" }}>
    {onBack ? <button className="btn btn-ghost" onClick={onBack} data-testid="b-back">← Back</button> : <span />}
    <button className="btn btn-primary" onClick={onNext} disabled={nextDisabled} data-testid="b-next">{nextLabel}</button>
  </div>
);
