import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import AddressField from "../components/AddressField";
import AgreementView from "../components/AgreementView";
import { CardSetup, CHARGE_ACCEPTANCE_FALLBACK } from "../components/CardSetup";
import { setPortalAuth } from "../lib/portalApi";
import { SiteChrome } from "./SiteChrome";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const DRAFT_KEY = "cos_signup_draft";

function detailMessage(error) {
  const detail = error?.response?.data?.detail;
  if (!detail) return "Could not create the shop. Call (480) 269-1329.";
  if (typeof detail === "string") return detail;
  if (detail.message) return detail.message;
  return Object.values(detail).join(" ");
}

function emptyForm() {
  return {
    shop_name: "", contact_name: "", mobile: "", email: "", password: "", confirm: "",
    address: "", place_id: null,
  };
}

export default function SignupPage() {
  const nav = useNavigate();
  const cardRef = useRef(null);
  const resumed = useRef(false);
  const [form, setForm] = useState(emptyForm);
  const [agreement, setAgreement] = useState(null);
  const [acceptance, setAcceptance] = useState(CHARGE_ACCEPTANCE_FALLBACK);
  const [signature, setSignature] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [chargeAccepted, setChargeAccepted] = useState(false);
  const [secondLocation, setSecondLocation] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [acceptedAddress, setAcceptedAddress] = useState(false);
  const [clientSecret, setClientSecret] = useState("");
  const [stripeNote, setStripeNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dupEmail, setDupEmail] = useState(false);

  useEffect(() => {
    axios.get(`${API}/public/agreement`).then(r => {
      setAgreement(r.data);
      if (r.data.acceptance) setAcceptance(r.data.acceptance);
    }).catch(() => {});
    axios.post(`${API}/public/card-setup`).then(r => {
      if (r.data.client_secret) setClientSecret(r.data.client_secret);
      else setStripeNote(r.data.message || "");
    }).catch(err => setStripeNote(detailMessage(err)));
  }, []);

  useEffect(() => {
    if (resumed.current) return;
    const params = new URLSearchParams(window.location.search);
    const intent = params.get("setup_intent");
    const status = params.get("redirect_status");
    if (!intent || status !== "succeeded") return;
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    let draft;
    try { draft = JSON.parse(raw); } catch { return; }
    resumed.current = true;
    setBusy(true);
    axios.post(`${API}/public/card-setup/complete`, { setup_intent_id: intent })
      .then(r => axios.post(`${API}/public/shops`, { ...draft, payment_method_id: r.data.payment_method_id }))
      .then(({ data }) => {
        sessionStorage.removeItem(DRAFT_KEY);
        setPortalAuth({
          token: data.token,
          full_name: data.full_name,
          shop_name: data.shop_name,
          shop_user_id: data.shop_user_id,
          shop_id: data.shop_id,
          has_payment_method: data.has_payment_method,
        });
        nav("/portal/book");
      })
      .catch(err => {
        setError(detailMessage(err));
        setBusy(false);
      });
  }, [nav]);

  function set(key, value) {
    setForm(prev => ({ ...prev, [key]: value, ...(key === "address" ? { place_id: null } : {}) }));
    if (key === "address") {
      setConfirm(null);
      setAcceptedAddress(false);
    }
  }

  function payload(extra = {}) {
    return {
      shop_name: form.shop_name,
      contact_name: form.contact_name,
      mobile: form.mobile,
      email: form.email,
      password: form.password,
      address: form.address,
      place_id: form.place_id,
      address_confirmed: acceptedAddress,
      confirmed_address: confirm?.formatted_address || null,
      terms_signature: signature,
      terms_agreed: agreed,
      charge_accepted: chargeAccepted,
      second_location: secondLocation,
      ...extra,
    };
  }

  async function finish(body) {
    const { data } = await axios.post(`${API}/public/shops`, body);
    sessionStorage.removeItem(DRAFT_KEY);
    setPortalAuth({
      token: data.token,
      full_name: data.full_name,
      shop_name: data.shop_name,
      shop_user_id: data.shop_user_id,
      shop_id: data.shop_id,
      has_payment_method: data.has_payment_method,
    });
    nav("/portal/book");
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setDupEmail(false);
    if (form.password !== form.confirm) {
      setError("Passwords don't match.");
      return;
    }
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (!agreed || !signature.trim()) {
      setError("Sign the agreement to create the shop.");
      return;
    }
    if (!chargeAccepted) {
      setError("Accept the charge terms to create the shop.");
      return;
    }
    setBusy(true);
    try {
      let paymentMethodId = null;
      if (clientSecret && cardRef.current) {
        sessionStorage.setItem(DRAFT_KEY, JSON.stringify(payload()));
        paymentMethodId = await cardRef.current();
      }
      await finish(payload(paymentMethodId ? { payment_method_id: paymentMethodId } : {}));
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.code === "needs_confirmation") {
        setConfirm(detail);
        setError("Check the address we found, then create the shop.");
      } else if (detail?.code === "duplicate_name") {
        setSecondLocation(false);
        setError(detail.message);
      } else if (detail?.code === "duplicate_email") {
        setDupEmail(true);
        setError(detail.message);
      } else if (err.message && !err.response) {
        setError(err.message);
      } else {
        setError(detailMessage(err));
      }
      sessionStorage.removeItem(DRAFT_KEY);
      setBusy(false);
    }
  }

  return (
    <SiteChrome>
      <div className="signup-wrap">
        <h1 className="display">Create your shop</h1>
        <p className="lede">One page. You sign the agreement, save a card, and land on booking. No charge today. If you leave after the account exists, log in and open Settings to finish the card. This is not a one-time link.</p>
        <form className="form" onSubmit={submit}>
          <div>
            <label className="label" htmlFor="shop">Shop name</label>
            <input id="shop" value={form.shop_name} onChange={e => set("shop_name", e.target.value)} required autoComplete="organization" data-testid="signup-shop-name" />
          </div>
          <div>
            <label className="label" htmlFor="contact">Contact name</label>
            <input id="contact" value={form.contact_name} onChange={e => set("contact_name", e.target.value)} required autoComplete="name" data-testid="signup-contact-name" />
          </div>
          <div>
            <label className="label" htmlFor="phone">Mobile</label>
            <input id="phone" value={form.mobile} onChange={e => set("mobile", e.target.value)} required autoComplete="tel" inputMode="tel" data-testid="signup-mobile" />
          </div>
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" type="email" value={form.email} onChange={e => set("email", e.target.value)} required autoComplete="email" data-testid="signup-email" />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input id="password" type="password" value={form.password} onChange={e => set("password", e.target.value)} required autoComplete="new-password" minLength={8} data-testid="signup-password" />
          </div>
          <div>
            <label className="label" htmlFor="confirm">Confirm password</label>
            <input id="confirm" type="password" value={form.confirm} onChange={e => set("confirm", e.target.value)} required autoComplete="new-password" data-testid="signup-confirm" />
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
                setAcceptedAddress(false);
              }}
              required
              placeholder="Street, city, AZ"
              testId="signup-address"
            />
            <p className="notice">Phoenix Valley only. A suggestion you pick is the confirmed address.</p>
          </div>
          {confirm && (
            <label className="check-row">
              <input
                type="checkbox"
                checked={acceptedAddress}
                onChange={e => {
                  setAcceptedAddress(e.target.checked);
                  if (e.target.checked) setForm(prev => ({ ...prev, address: confirm.formatted_address }));
                }}
                data-testid="signup-confirm-address"
              />
              <span>Use this address: {confirm.formatted_address}</span>
            </label>
          )}
          {error && error.includes("second location") && (
            <label className="check-row">
              <input type="checkbox" checked={secondLocation} onChange={e => setSecondLocation(e.target.checked)} data-testid="signup-second-location" />
              <span>This is a second location of a shop already on file.</span>
            </label>
          )}
          <div className="agreement-pane">
            <h2>Service agreement</h2>
            <AgreementView sections={agreement?.sections || []} paragraphs={agreement?.paragraphs || []} />
          </div>
          <div>
            <label className="label" htmlFor="signature">Type your name to sign</label>
            <input id="signature" value={signature} onChange={e => setSignature(e.target.value)} required data-testid="signup-signature" />
          </div>
          <label className="check-row">
            <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} data-testid="signup-agree" />
            <span>I am allowed to sign for this shop. My typed name is my signature.</span>
          </label>
          <div>
            <h2>Card on file</h2>
            <p className="notice">No charge today. The card is used after a job is completed, unless you asked to be invoiced.</p>
            {clientSecret ? (
              <CardSetup clientSecret={clientSecret} bindRef={cardRef} returnUrl={`${window.location.origin}/signup`} />
            ) : (
              <p className="notice">{stripeNote || "Loading card setup…"}</p>
            )}
          </div>
          <label className="check-row">
            <input type="checkbox" checked={chargeAccepted} onChange={e => setChargeAccepted(e.target.checked)} data-testid="signup-charge" />
            <span>{acceptance}</span>
          </label>
          {error && <p className="form-msg is-on" data-testid="signup-error">{error}</p>}
          {dupEmail && (
            <p className="hero-note" style={{ margin: 0, textAlign: "center" }}>
              <Link to="/portal/login">Log in</Link>
              {" · "}
              <Link to="/portal/forgot">Forgot password</Link>
            </p>
          )}
          <button className="btn btn-primary btn-lg" type="submit" disabled={busy} data-testid="signup-submit">
            {busy ? "Creating…" : "Create my shop"}
          </button>
          <p className="hero-note" style={{ margin: 0, textAlign: "center" }}>
            Already have an account? <Link to="/portal/login">Log in</Link>
          </p>
        </form>
      </div>
    </SiteChrome>
  );
}
