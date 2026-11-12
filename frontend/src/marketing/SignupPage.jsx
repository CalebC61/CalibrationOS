import { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import AddressField from "../components/AddressField";
import { SiteChrome } from "./SiteChrome";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function detailMessage(error) {
  const detail = error?.response?.data?.detail;
  if (!detail) return "Could not send that request. Call (480) 269-1329.";
  if (typeof detail === "string") return detail;
  if (detail.message) return detail.message;
  return Object.values(detail).join(" ");
}

export default function SignupPage() {
  const [form, setForm] = useState({
    shop_name: "", contact_name: "", mobile: "", email: "", address: "", place_id: null,
  });
  const [confirm, setConfirm] = useState(null);
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  function set(key, value) {
    setForm(prev => ({ ...prev, [key]: value }));
    if (key === "address") { setConfirm(null); setAccepted(false); }
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...form,
        address_confirmed: accepted,
        confirmed_address: confirm?.formatted_address || null,
      };
      const { data } = await axios.post(`${API}/public/shop-requests`, payload);
      setDone(data.message || "Caleb will send your setup link shortly.");
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.code === "needs_confirmation") {
        setConfirm(detail);
        setError("Check the address below, then send the request.");
      } else {
        setError(detailMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <SiteChrome>
      <div className="signup-wrap">
        <p className="eyebrow" style={{ marginLeft: "auto", marginRight: "auto" }}>CalibrationOS</p>
        <h1 className="display">Request a shop account</h1>
        <p className="lede">Tell Caleb the shop and how to reach you. He sends the setup link. This does not create a password.</p>
        {done ? (
          <div className="form" data-testid="signup-done">
            <p>{done}</p>
            <p className="hero-note" style={{ margin: 0, textAlign: "center" }}>
              Already have an account? <Link to="/portal/login">Log in</Link>
            </p>
          </div>
        ) : (
          <form className="form" onSubmit={submit}>
            <div>
              <label className="label" htmlFor="shop">Shop name</label>
              <input id="shop" value={form.shop_name} onChange={e => set("shop_name", e.target.value)} required autoComplete="organization" data-testid="request-shop-name" />
            </div>
            <div>
              <label className="label" htmlFor="contact">Contact name</label>
              <input id="contact" value={form.contact_name} onChange={e => set("contact_name", e.target.value)} required autoComplete="name" data-testid="request-contact-name" />
            </div>
            <div>
              <label className="label" htmlFor="phone">Mobile</label>
              <input id="phone" value={form.mobile} onChange={e => set("mobile", e.target.value)} required autoComplete="tel" inputMode="tel" data-testid="request-mobile" />
            </div>
            <div>
              <label className="label" htmlFor="email">Email</label>
              <input id="email" type="email" value={form.email} onChange={e => set("email", e.target.value)} required autoComplete="email" data-testid="request-email" />
            </div>
            <div>
              <label className="label" htmlFor="address">Shop address</label>
              <AddressField
                id="address"
                value={form.address}
                onChange={value => set("address", value)}
                onPlace={place => {
                  setForm(prev => ({ ...prev, address: place.address, place_id: place.placeId }));
                  setConfirm(null);
                }}
                required
                placeholder="Street, city, AZ"
                testId="request-address"
              />
              <p className="notice">Phoenix Valley addresses only. Pick the shop from the suggestions when they appear.</p>
            </div>
            {confirm && (
              <label className="notice" style={{ color: "var(--text-primary)" }}>
                <input
                  type="checkbox"
                  checked={accepted}
                  onChange={e => {
                    setAccepted(e.target.checked);
                    if (e.target.checked) setForm(prev => ({ ...prev, address: confirm.formatted_address }));
                  }}
                  data-testid="request-confirm-address"
                />{" "}
                Use this address: {confirm.formatted_address}
              </label>
            )}
            {error && <p className="form-msg is-on" data-testid="request-error">{error}</p>}
            <button className="btn btn-primary btn-lg" type="submit" disabled={busy} data-testid="request-submit">
              {busy ? "Sending…" : "Request a shop account"}
            </button>
            <p className="hero-note" style={{ margin: 0, textAlign: "center" }}>
              Already have an account? <Link to="/portal/login">Log in</Link>
            </p>
          </form>
        )}
      </div>
    </SiteChrome>
  );
}
