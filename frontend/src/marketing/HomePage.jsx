import { Link } from "react-router-dom";
import { FaqList, SiteChrome } from "./SiteChrome";

export default function HomePage() {
  return (
    <SiteChrome>
      <section className="hero">
        <div className="container hero-grid">
          <div>
            <p className="eyebrow">For auto glass shops · Phoenix Valley</p>
            <h1 className="display">You set the<br />glass.<br /><span className="accent hero-line">We calibrate it.</span></h1>
            <p className="subhead">Mobile ADAS calibration for auto glass shops. Create a shop account in CalibrationOS to book a visit, track the job, and get the report. We come to your bay or your customer's driveway, anywhere in the Valley.</p>
            <div className="btn-row">
              <Link className="btn btn-primary btn-lg" to="/signup">Create your shop account</Link>
              <a className="btn btn-ghost btn-lg" href="#how-it-works">See how it works</a>
            </div>
            <p className="hero-note">Already have an account? <Link to="/portal/login">Log in to CalibrationOS</Link></p>
          </div>
          <div className="app-frame" aria-hidden="true">
            <div className="app-bar"><i /><i /><i /><span>CalibrationOS</span></div>
            <div className="app-body">
              <aside className="app-side">
                <p>Shop portal</p>
                <div className="nav-item is-on">Bookings</div>
                <div className="nav-item">Reports</div>
                <div className="nav-item">Account</div>
              </aside>
              <div className="app-main">
                <div className="mini-card">
                  <h3>Request a calibration</h3>
                  <strong>Vehicle, calibration type, and a time that works</strong>
                  <p className="meta">Book online in under a minute. Add-ons the same day are welcome.</p>
                </div>
                <div className="mini-card">
                  <h3>Today's job</h3>
                  <strong>Static camera calibration</strong>
                  <p className="meta">On site at your shop · report in your account</p>
                  <span className="pill pill-wait">Scheduled</span>
                </div>
                <div className="mini-card">
                  <h3>Report</h3>
                  <strong>OEM-procedure calibration report</strong>
                  <p className="meta">Same-day reports and invoices</p>
                  <span className="pill pill-ok">Ready</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="how-it-works">
        <div className="container">
          <p className="section-kicker">How it works</p>
          <h2 className="display">From signup to the report</h2>
          <p className="lede">CalibrationOS is how your shop gets into our books, follows the job, and keeps the paperwork in one place.</p>
          <div className="steps">
            <article className="step">
              <div className="step-num">01</div>
              <h3>Create your shop account</h3>
              <p>Sign up with the shop, a card, and the service agreement. You can book in the same sitting.</p>
            </article>
            <article className="step">
              <div className="step-num">02</div>
              <h3>Book a calibration</h3>
              <p>Tell us the vehicle, the calibration type, and a time that works. You can book online in under a minute.</p>
            </article>
            <article className="step">
              <div className="step-num">03</div>
              <h3>We come to you</h3>
              <p>We calibrate at your bay or your customer's driveway, then the report and invoice show up the same day.</p>
            </article>
          </div>
        </div>
      </section>

      <section className="section band">
        <div className="container">
          <p className="section-kicker">Services and pricing</p>
          <h2 className="display">Priced by the calibration, not by the brand</h2>
          <p className="lede">We service almost all makes and models, including Tesla. If you have a question about a specific car, call or text and we will answer right away.</p>
          <div className="price-grid">
            {[
              ["Static", "$125", "Targets and tools, vehicle parked. Common after windshield work on camera systems."],
              ["Dynamic", "$125", "A road drive with the scan tool, when the OEM procedure calls for it."],
              ["Dual", "$175", "Static and dynamic together, when the vehicle needs both."],
              ["Triple / Subaru", "$185", "Three-camera and Subaru EyeSight calibrations, when the vehicle needs the triple procedure."],
              ["Tesla", "$225", "Tesla windshield and camera calibration, following Tesla's process."],
            ].map(([name, price, copy]) => (
              <article className="price-card" key={name}>
                <h3>{name}</h3>
                <div className="amount">{price}</div>
                <p className="each">per calibration</p>
                <p>{copy}</p>
              </article>
            ))}
          </div>
          <div className="btn-row">
            <Link className="btn btn-ghost" to="/pricing">See full pricing and offers</Link>
            <Link className="btn btn-ghost" to="/services">Browse services</Link>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <p className="section-kicker">First job offer</p>
          <h2 className="display">Try us for $50</h2>
          <div className="offer">
            <article className="offer-card">
              <p className="section-kicker" style={{ margin: "0 0 0.4rem" }}>Introductory rate</p>
              <div className="amount">$50 <span>first calibration</span></div>
              <p>Your first job with us is $50, so you can see how the process feels in your shop before you commit to regular work.</p>
            </article>
            <article className="offer-card">
              <p className="section-kicker" style={{ margin: "0 0 0.4rem" }}>The 5-Star Guarantee</p>
              <h3>You only pay that $50 if the first job earns your shop a 5-star review.</h3>
              <p style={{ marginTop: "0.8rem" }}>If your customer does not leave your shop a 5-star review after we handle their calibration, you do not pay a dime for that first job.</p>
            </article>
          </div>
        </div>
      </section>

      <section className="section band">
        <div className="container">
          <p className="section-kicker">Why shops use us</p>
          <h2 className="display">Built around your bay, not a drop-off lot</h2>
          <div className="benefit-grid">
            {[
              ["We come to you", "Mobile service at your shop or your customer's driveway. No shuttling the car across town for the calibration."],
              ["Valley-wide, East and West", "Based in Gilbert, and covering the Phoenix Valley from Buckeye to Gold Canyon, and from Black Canyon City to Casa Grande."],
              ["Updates by text, reports the same day", "Real-time ETAs and job updates by text. Same-day reports and invoices, including pre- and post-scan documentation when the job calls for it."],
              ["Same-day add-ons welcome", "Need to add a car after the route is already set? Call or text the office. If there is a slot, there is no additional charge for the same-day add-on."],
            ].map(([title, copy]) => (
              <article className="benefit" key={title}><h3>{title}</h3><p>{copy}</p></article>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <p className="section-kicker">From shop partners and their customers</p>
          <h2 className="display">Don't take our word for it</h2>
          <p className="lede">These are reviews The Calibration Crew already uses on shop flyers.</p>
          <div className="quotes">
            {[
              ["Caleb was above and beyond as a calibration tech.", "Customer review"],
              ["Scheduled and completed in one day! Caleb and Ruben were professional and worked quickly.", "Google review"],
              ["Caleb who found and remedied the calibration problem quickly. I highly recommend using this company.", "CBA Autoglass customer"],
              ["Caleb is a superstar for sure. We are very fortunate to have him part of our team.", "Owner of Preferred Auto Glass"],
            ].map(([quote, cite]) => (
              <blockquote className="quote" key={cite}><p>“{quote}”</p><cite>{cite}</cite></blockquote>
            ))}
          </div>
        </div>
      </section>

      <section className="section band" id="faq">
        <div className="container">
          <p className="section-kicker">FAQ</p>
          <h2 className="display">Common questions from shops</h2>
          <FaqList />
        </div>
      </section>

      <section className="cta-final">
        <div className="container">
          <h2 className="display">Ready for the next windshield?</h2>
          <p className="lede">Create a shop account to get into CalibrationOS. After that, you can log in anytime to book and get reports.</p>
          <div className="btn-row" style={{ justifyContent: "center" }}>
            <Link className="btn btn-primary btn-lg" to="/signup">Create your shop account</Link>
            <Link className="btn btn-ghost btn-lg" to="/portal/login">Log in</Link>
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}
