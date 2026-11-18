import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { phoenixTodayStr } from "../lib/api";
import { portalApi } from "../lib/portalApi";
import AddressField from "../components/AddressField";
import { redoIsFree, warrantyOptionLabel, WARRANTY_BILLED, WARRANTY_FREE } from "../lib/warranty";
import WarrantyChargeNotice from "../components/WarrantyChargeNotice";
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
const normAddr = (value) => (value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
const sameAddress = (left, right) => Boolean(normAddr(left)) && normAddr(left) === normAddr(right);

export default function PortalBook() {
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [shop, setShop] = useState(null);
  const [address, setAddress] = useState("");
  const [zoneInfo, setZoneInfo] = useState(null);
  const [date, setDate] = useState("");
  const [slots, setSlots] = useState([]);
  const [slotsMsg, setSlotsMsg] = useState("");
  const [slotsError, setSlotsError] = useState(false);
  const [addressError, setAddressError] = useState("");
  const [chosen, setChosen] = useState(null);
  const [veh, setVeh] = useState({ customer_first_name: "", customer_last_name: "", notes: "",
    year: new Date().getFullYear(),
    make: "", model: "", trim: "", vin: "", adas_system: "forward_camera" });
  const [calType, setCalType] = useState("static");
  const [notifyPhone, setNotifyPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [setup, setSetup] = useState(null);
  const [invoiceInstead, setInvoiceInstead] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const [bookError, setBookError] = useState("");
  const [pastJobs, setPastJobs] = useState([]);
  const [redoChecked, setRedoChecked] = useState(false);
  const [redoOf, setRedoOf] = useState("");
  const [chargeNotice, setChargeNotice] = useState(false);

  useEffect(() => {
    portalApi.get("/portal/me").then(r => {
      setShop(r.data.shop);
      setSetup(r.data.setup);
      setAddress(r.data.shop.address || "");
      setZoneInfo({ in_metro: true, reused: true });
      setNotifyPhone(r.data.shop.contact_phone || "");
    });
    portalApi.get("/portal/warranty-jobs").then(r => {
      setPastJobs(Array.isArray(r.data) ? r.data : []);
    }).catch(() => setPastJobs([]));
  }, []);

  useEffect(() => {
    if (!shop || !address.trim()) return undefined;
    if (sameAddress(address, shop.address) || sameAddress(address, shop.formatted_address)) return undefined;
    let cancelled = false;
    const handle = setTimeout(() => {
      portalApi.post("/geocode", { address }).then(({ data }) => {
        if (cancelled) return;
        setZoneInfo(data);
        setAddressError("");
      }).catch((e) => {
        if (cancelled) return;
        setZoneInfo(null);
        const detail = e.response?.data?.detail;
        setAddressError(typeof detail === "string" ? detail : "We couldn't find that address, please check it");
      });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [address, shop]);

  if (!shop || !setup) return <PortalShell><div className="muted">Loading…</div></PortalShell>;
  if (setup.allowed === false) {
    return <PortalShell>
      <div className="surface" style={{ padding: 24, textAlign: "center", maxWidth: 500, margin: "40px auto" }} data-testid="booking-closed">
        <div className="h2" style={{ marginBottom: 8 }}>{setup.suspended ? "Booking is paused" : "Booking is closed"}</div>
        <div className="muted" style={{ marginBottom: 16 }}>{setup.message}</div>
        {!setup.suspended && <button className="btn btn-primary" onClick={() => nav("/portal/settings")} data-testid="goto-add-card">Update card</button>}
      </div>
    </PortalShell>;
  }

  function atShop(value) {
    return sameAddress(value, shop.address) || sameAddress(value, shop.formatted_address);
  }
  async function geo(value = address) {
    if (atShop(value)) {
      setAddressError("");
      setZoneInfo({ in_metro: true, reused: true });
      return;
    }
    setAddressError("");
    try {
      const { data } = await portalApi.post("/geocode", { address: value });
      setZoneInfo(data);
    } catch (e) {
      setZoneInfo(null);
      const detail = e.response?.data?.detail;
      setAddressError(typeof detail === "string" ? detail : "We couldn't find that address, please check it");
    }
  }
  async function loadSlots(d) {
    setSlots([]); setSlotsMsg(""); setSlotsError(false);
    try {
      const { data } = await portalApi.post("/portal/availability", {
        job_address: address, date: d,
      });
      setSlots(data.slots || []);
      if ((data.slots || []).length === 0) setSlotsMsg(data.message || "No slots available.");
    } catch (e) {
      setSlots([]);
      setSlotsError(true);
      const detail = e.response?.data?.detail;
      setSlotsMsg(typeof detail === "string" && detail ? detail : "Couldn't load times, try again");
    }
  }
  function pickAdas(v) {
    const opt = ADAS.find(o => o.v === v);
    setVeh({...veh, adas_system: v});
    if (opt) setCalType(opt.default);
  }
  function priceFor(t) {
    if (shop?.prices && shop.prices[t] != null) return Number(shop.prices[t]);
    if (shop.pricing_tier === "custom" && shop[`custom_rate_${t}`] != null) return Number(shop[`custom_rate_${t}`]);
    return ({static: 125, dynamic: 125, dual: 175, triple: 185, tesla: 225})[t];
  }
  const selectedRedo = pastJobs.find(row => row.id === redoOf);
  const redoDay = chosen?.start ? phoenixTodayStr(new Date(chosen.start)) : "";
  const redoFree = Boolean(redoChecked && selectedRedo && redoIsFree(selectedRedo.warranty_through, redoDay));
  const redoBilled = Boolean(redoChecked && selectedRedo && redoDay && !redoIsFree(selectedRedo.warranty_through, redoDay));
  const shownPrice = redoFree ? 0 : priceFor(calType);
  async function submit() {
    setSubmitting(true);
    setBookError("");
    try {
      const { data } = await portalApi.post("/portal/book", {
        job_address: address,
        scheduled_start: chosen.start, customer_last_name: veh.customer_last_name,
        customer_first_name: veh.customer_first_name.trim() || null,
        notes: veh.notes.trim() || null,
        year: Number(veh.year), make: veh.make, model: veh.model,
        trim: veh.trim || null, vin: veh.vin || null,
        adas_system: veh.adas_system, calibration_type: calType,
        notification_phone: notifyPhone, invoice_instead: invoiceInstead,
        warranty_of_job_id: redoChecked && redoOf ? redoOf : null,
      });
      setConfirmation(data);
    } catch (e) {
      const detail = e.response?.data?.detail;
      setBookError(typeof detail === "string" && detail ? detail : "Booking failed");
    } finally { setSubmitting(false); }
  }
  function askSubmit() {
    if (redoBilled) {
      setChargeNotice(true);
      return;
    }
    submit();
  }

  if (confirmation) {
    const pending = confirmation.requires_approval || confirmation.status === "requested";
    return <PortalShell>
      <div className="surface" style={{ padding: 30, maxWidth: 560, margin: "20px auto", textAlign: "center" }} data-testid="portal-confirm">
        {!pending && <div style={{ fontSize: 48, color: "var(--green)" }}>✓</div>}
        <div className="h2">{pending ? "Pending owner approval" : "Booking Confirmed"}</div>
        <div className="muted">Ref #{confirmation.booking_reference}</div>
        {confirmation.warranty_label && (
          <div style={{ marginTop: 12, fontSize: 14 }} data-testid="portal-warranty-label">{confirmation.warranty_label}</div>
        )}
        {confirmation.price != null && (
          <div className="font-mono" style={{ marginTop: 8 }} data-testid="portal-confirm-price">
            ${Number(confirmation.price).toFixed(2)}
          </div>
        )}
        {pending && (
          <div style={{ marginTop: 12, fontSize: 14 }} data-testid="portal-pending-note">
            This time is held until the owner approves it.
          </div>
        )}
        <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => nav("/portal/jobs")}>View My Jobs</button>
      </div>
    </PortalShell>;
  }

  return (
    <PortalShell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Book a Calibration</h1>
      <div style={{ maxWidth: 640 }}>
        {step === 1 && (
          <Card title="Where and when?" sub="The shop address is already confirmed. Change it only if the vehicle is somewhere else.">
            <AddressField
              id="b-addr"
              className="input"
              value={address}
              testId="b-addr"
              placeholder="Street, city, AZ"
              onChange={value => {
                setAddress(value);
                setChosen(null);
                setSlots([]);
                if (atShop(value)) setZoneInfo({ in_metro: true, reused: true });
                else setZoneInfo(null);
              }}
              onPlace={place => {
                setAddress(place.address);
                setChosen(null);
                setSlots([]);
                if (atShop(place.address)) {
                  setAddressError("");
                  setZoneInfo({ in_metro: true, reused: true });
                }
              }}
              onBlur={value => geo(value)}
            />
            {zoneInfo?.in_metro && <div style={{ marginTop: 10, fontSize: 14 }}>In our Phoenix service area.</div>}
            {addressError && <div role="alert" style={{ color: "var(--red)", marginTop: 10, fontSize: 14 }}>{addressError}</div>}
            {zoneInfo && !zoneInfo.in_metro && <div style={{ color: "var(--red)", marginTop: 10, fontSize: 14 }}>That address is outside the Phoenix Valley.</div>}
            <div style={{ marginTop: 16 }}>
              <label className="label" htmlFor="b-date">Date</label>
              <input id="b-date" className="input" type="date" value={date}
                min={phoenixTodayStr()}
                max={phoenixTodayStr(new Date(Date.now() + 21 * 86400000))}
                disabled={!zoneInfo?.in_metro}
                onChange={e => { setDate(e.target.value); setChosen(null); loadSlots(e.target.value); }} data-testid="b-date" />
            </div>
            {slotsMsg && <div style={{ marginTop: 10, fontSize: 14, color: slotsError ? "var(--red)" : "var(--yellow)" }} data-testid="portal-slots-message">{slotsMsg}</div>}
            {slotsError && (
              <button type="button" className="btn btn-ghost" style={{ marginTop: 12 }}
                onClick={() => loadSlots(date)} data-testid="portal-slots-retry">
                Try again
              </button>
            )}
            {slots.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="label">Available times</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 8 }}>
                  {slots.map(s => (
                    <button key={s.start} type="button"
                      className={"btn " + (chosen?.start === s.start ? "btn-primary" : "btn-ghost")}
                      onClick={() => setChosen(s)} data-testid={`b-slot-${s.start}`}
                      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, minHeight: 44 }}>
                      <span>{fmt(s.start)}</span>
                      {s.requires_approval && (
                        <span style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.2 }}>Pending approval</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <Nav onNext={() => setStep(2)} nextDisabled={!zoneInfo?.in_metro || !chosen} />
          </Card>
        )}
        {step === 2 && (
          <Card title="Vehicle and price">
            <R>
              <F label="Customer first name"><input className="input" value={veh.customer_first_name}
                onChange={e => setVeh({...veh, customer_first_name: e.target.value})} data-testid="b-fn" /></F>
              <F label="Customer last name *"><input className="input" value={veh.customer_last_name}
                onChange={e => setVeh({...veh, customer_last_name: e.target.value})} data-testid="b-ln" /></F>
            </R>
            <R><F label="Year *"><input className="input" type="number" value={veh.year}
              onChange={e => setVeh({...veh, year: e.target.value})} /></F>
              <F label="Make *"><input className="input" value={veh.make}
                onChange={e => setVeh({...veh, make: e.target.value})} data-testid="b-make" /></F></R>
            <R><F label="Model *"><input className="input" value={veh.model}
              onChange={e => setVeh({...veh, model: e.target.value})} data-testid="b-model" /></F>
              <F label="Trim"><input className="input" value={veh.trim}
                onChange={e => setVeh({...veh, trim: e.target.value})} /></F></R>
            <F label="VIN"><input className="input" maxLength={17} value={veh.vin}
              onChange={e => setVeh({...veh, vin: e.target.value.toUpperCase()})} /></F>
            <F label="ADAS system *">
              <select className="input" value={veh.adas_system} onChange={e => pickAdas(e.target.value)}>
                {ADAS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </F>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, margin: "8px 0 16px" }}>
              {Object.entries(LABELS).map(([k, l]) => (
                <button key={k} type="button"
                  className={"btn " + (calType === k ? "btn-primary" : "btn-ghost")}
                  onClick={() => setCalType(k)} style={{ justifyContent: "space-between", width: "100%" }}>
                  <span>{l}</span><span className="font-mono">${priceFor(k).toFixed(2)}</span>
                </button>
              ))}
            </div>
            {chosen?.requires_approval && (
              <div style={{ fontSize: 14, marginBottom: 12 }}>
                Pending owner approval. This time is held until the owner approves it.
              </div>
            )}
            <div style={{ margin: "8px 0 16px" }}>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <input type="checkbox" checked={redoChecked}
                  onChange={e => { setRedoChecked(e.target.checked); if (!e.target.checked) setRedoOf(""); }}
                  data-testid="warranty-redo" />
                <span>This is a redo of a past job</span>
              </label>
              {redoChecked && pastJobs.length === 0 && (
                <div className="muted" style={{ fontSize: 13, marginTop: 8 }} data-testid="warranty-none">
                  No completed jobs in the last 90 days.
                </div>
              )}
              {redoChecked && pastJobs.length > 0 && (
                <select className="input" style={{ marginTop: 8 }} value={redoOf}
                  onChange={e => setRedoOf(e.target.value)} data-testid="warranty-of">
                  <option value="">Choose a completed job</option>
                  {pastJobs.map(row => (
                    <option key={row.id} value={row.id}>{warrantyOptionLabel(row)}</option>
                  ))}
                </select>
              )}
              {redoFree && (
                <div style={{ fontSize: 13, marginTop: 8 }} data-testid="warranty-preview">{WARRANTY_FREE}</div>
              )}
              {redoBilled && (
                <div style={{ fontSize: 13, marginTop: 8 }} data-testid="warranty-preview">{WARRANTY_BILLED}</div>
              )}
            </div>
            <div className="elevated" style={{ padding: 14, fontSize: 14 }}>
              <Row k="When" v={`${new Date(chosen.start).toLocaleDateString()} · ${fmt(chosen.start)}`} />
              <Row k="Vehicle" v={`${veh.year} ${veh.make} ${veh.model}`} />
              <Row k="Customer" v={[veh.customer_first_name, veh.customer_last_name].filter(s => s.trim()).join(" ")} />
              <Row k="Total" v={`$${shownPrice.toFixed(2)}`} bold />
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                {redoFree
                  ? "This redo is within 30 days, so it is free. The card is not charged."
                  : "The card on file is charged when the job is completed, unless you ask to be invoiced."}
              </div>
            </div>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 14 }}>
              <input type="checkbox" checked={invoiceInstead} onChange={e => setInvoiceInstead(e.target.checked)} data-testid="invoice-instead" />
              <span>Please invoice me instead</span>
            </label>
            <F label="Phone">
              <input className="input" value={notifyPhone} onChange={e => setNotifyPhone(e.target.value)}
                inputMode="tel" autoComplete="tel" data-testid="b-phone" />
            </F>
            <F label="Notes (optional)">
              <textarea className="input" rows={3} value={veh.notes}
                onChange={e => setVeh({...veh, notes: e.target.value})} data-testid="b-notes" />
            </F>
            {bookError && (
              <div role="alert" data-testid="portal-book-error" style={{ color: "var(--red)", fontSize: 14, marginTop: 4 }}>
                {bookError}
              </div>
            )}
            <Nav onBack={() => setStep(1)} onNext={askSubmit}
              nextLabel={submitting ? "Booking…" : (chosen?.requires_approval ? "Request this time" : "Confirm Booking")}
              nextDisabled={submitting || !veh.customer_last_name.trim() || !String(veh.year).trim() || !veh.make.trim() || !veh.model.trim() || (redoChecked && !redoOf)} />
          </Card>
        )}
      </div>
      <WarrantyChargeNotice
        open={chargeNotice}
        onCancel={() => setChargeNotice(false)}
        onContinue={() => { setChargeNotice(false); submit(); }}
      />
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
