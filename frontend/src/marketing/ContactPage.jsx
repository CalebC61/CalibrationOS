import { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { SiteChrome } from "./SiteChrome";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ContactPage() {
  const [form, setForm] = useState({ shop_name: "", name: "", email: "", phone: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { data } = await axios.post(`${API}/public/contact`, form);
      setNotice(data.message || "Caleb has your note.");
      setForm({ shop_name: "", name: "", email: "", phone: "", message: "" });
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not send that. Call (480) 269-1329.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <SiteChrome>
      <section className="page-hero">
        <div className="container">
          <p className="section-kicker">Contact</p>
          <h1 className="display">Call, text, or send a note</h1>
          <p className="lede">We are a mobile shop based in Gilbert, open Monday through Saturday. Hablo Español.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: "1rem" }}>
        <div className="container contact-grid">
          <div className="contact-facts">
            <article className="card fact">
              <h3>Phone</h3>
              <p><a href="tel:4802691329">(480) 269-1329</a></p>
              <p>Call or text the office, including same-day add-ons.</p>
            </article>
            <article className="card fact">
              <h3>Email</h3>
              <p><a href="mailto:admin@thecalibrationcrew.us">admin@thecalibrationcrew.us</a></p>
            </article>
            <article className="card fact">
              <h3>Book a job</h3>
              <p><Link to="/signup">Request a CalibrationOS account</Link></p>
              <p><a href="https://calendly.com/calcrew/adas-calibration-appointment" target="_blank" rel="noopener noreferrer">Or use the online scheduler</a></p>
            </article>
            <article className="card fact">
              <h3>Hours and area</h3>
              <p>Monday through Saturday</p>
              <p>Gilbert, AZ · Phoenix Valley</p>
              <p><Link to="/service-area">See the service area</Link></p>
            </article>
          </div>
          <form className="form" onSubmit={submit}>
            <div>
              <label className="label" htmlFor="c-shop">Shop name</label>
              <input id="c-shop" value={form.shop_name} onChange={e => setForm({ ...form, shop_name: e.target.value })} autoComplete="organization" />
            </div>
            <div>
              <label className="label" htmlFor="c-name">Your name</label>
              <input id="c-name" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} autoComplete="name" data-testid="contact-name" />
            </div>
            <div>
              <label className="label" htmlFor="c-email">Email</label>
              <input id="c-email" type="email" required value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} autoComplete="email" data-testid="contact-email" />
            </div>
            <div>
              <label className="label" htmlFor="c-phone">Phone</label>
              <input id="c-phone" type="tel" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} autoComplete="tel" />
            </div>
            <div>
              <label className="label" htmlFor="c-msg">Message</label>
              <textarea id="c-msg" required value={form.message} onChange={e => setForm({ ...form, message: e.target.value })} data-testid="contact-message" />
            </div>
            <button className="btn btn-primary" type="submit" disabled={busy} data-testid="contact-submit">
              {busy ? "Sending…" : "Send message"}
            </button>
            {notice && <div className="form-msg is-on" data-testid="contact-sent">{notice}</div>}
            {error && <div className="form-msg is-on">{error}</div>}
          </form>
        </div>
      </section>
    </SiteChrome>
  );
}
