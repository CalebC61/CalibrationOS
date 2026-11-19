import { Link } from "react-router-dom";
import { FaqList, SiteChrome } from "./SiteChrome";

const RATES = [
  ["Static", "$125", "Targets and tools, vehicle parked. Common after windshield work on camera systems."],
  ["Dynamic", "$125", "A road drive with the scan tool, when the OEM procedure calls for it."],
  ["Dual", "$175", "Static and dynamic together, when the vehicle needs both."],
  ["Triple / Subaru", "$185", "Three-camera and Subaru EyeSight calibrations, when the vehicle needs the triple procedure."],
  ["Tesla", "$225", "Tesla windshield and camera calibration, following Tesla's process."],
];

const STEPS = [
  ["Create your shop account", "Sign up with the shop, a card, and the service agreement. You can book in the same sitting."],
  ["Book a calibration", "Tell us the vehicle, the calibration type, and a time that works. Book it from your shop account."],
  ["We come to you", "We calibrate at your bay or your customer's driveway, then the report and invoice show up the same day."],
];

const REASONS = [
  ["We come to you", "Mobile service at your shop or your customer's driveway. No shuttling the car across town for the calibration."],
  ["Valley-wide, East and West", "Based in Gilbert, and covering the Phoenix Valley from Buckeye to Gold Canyon, and from Black Canyon City to Casa Grande."],
  ["Job status in your account", "Follow the job in your shop account. Same-day reports and invoices, including pre- and post-scan documentation when the job calls for it."],
  ["Same-day add-ons welcome", "Need to add a car after the route is already set? Call or text the office. If there is a slot, there is no additional charge for the same-day add-on."],
];

const QUOTES = [
  ["Caleb was above and beyond as a calibration tech.", "Customer review"],
  ["Scheduled and completed in one day! Caleb and Ruben were professional and worked quickly.", "Google review"],
  ["Caleb who found and remedied the calibration problem quickly. I highly recommend using this company.", "CBA Autoglass customer"],
  ["Caleb is a superstar for sure. We are very fortunate to have him part of our team.", "Owner of Preferred Auto Glass"],
];

function CalibrationTarget() {
  const cells = [];
  const origin = 48;
  const size = 44;
  for (let row = 0; row < 6; row += 1) {
    for (let col = 0; col < 6; col += 1) {
      const light = (row + col) % 2 === 0;
      cells.push(
        <rect
          key={`${row}-${col}`}
          x={origin + col * size}
          y={origin + row * size}
          width={size}
          height={size}
          fill={light ? "#F3F0E8" : "#14161A"}
        />
      );
    }
  }
  return (
    <svg viewBox="0 0 360 360" role="img" aria-label="Black and white calibration target with an orange center mark">
      <rect x="14" y="18" width="332" height="328" fill="#12141A" />
      <rect x="18" y="14" width="328" height="332" fill="none" stroke="#8B909C" strokeWidth="10" />
      {cells}
      <circle cx="180" cy="180" r="42" fill="#F3F0E8" />
      <circle cx="180" cy="180" r="27" fill="none" stroke="#FF5F1F" strokeWidth="5" />
      <path d="M180 146 V164 M180 196 V214 M146 180 H164 M196 180 H214" stroke="#14161A" strokeWidth="3" />
      <circle cx="180" cy="180" r="3.5" fill="#14161A" />
      <path d="M40 68 V40 H68" fill="none" stroke="#FF5F1F" strokeWidth="3.5" />
      <path d="M320 68 V40 H292" fill="none" stroke="#FF5F1F" strokeWidth="3.5" />
      <path d="M40 292 V320 H68" fill="none" stroke="#FF5F1F" strokeWidth="3.5" />
      <path d="M320 292 V320 H292" fill="none" stroke="#FF5F1F" strokeWidth="3.5" />
    </svg>
  );
}

export default function HomePage() {
  return (
    <SiteChrome>
      <div className="home">
        <section className="hero">
          <div className="container hero-grid">
            <h1 className="display">You set the<br />glass.<br /><span className="accent hero-line">We calibrate it.</span></h1>
            <figure className="target-board">
              <CalibrationTarget />
              <figcaption>A calibration target, the kind set up in the bay for a static camera job.</figcaption>
            </figure>
            <div className="hero-copy">
              <p className="subhead">Mobile ADAS calibration for auto glass shops. Create a shop account in CalibrationOS to book a visit, track the job, and get the report. We come to your bay or your customer's driveway, anywhere in the Valley.</p>
              <div className="btn-row">
                <Link className="btn btn-primary btn-lg" to="/signup">Create your shop account</Link>
                <a className="btn btn-ghost btn-lg" href="#how-it-works">See how it works</a>
              </div>
              <p className="hero-note">Already have an account? <Link to="/portal/login">Log in to CalibrationOS</Link></p>
            </div>
          </div>
        </section>

        <section className="section" id="how-it-works">
          <div className="container">
            <h2 className="display">From signup to the report</h2>
            <p className="lede">CalibrationOS is how your shop gets into our books, follows the job, and keeps the paperwork in one place.</p>
            <ol className="work-order">
              {STEPS.map(([title, copy]) => (
                <li key={title}>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="section band">
          <div className="container">
            <h2 className="display">Priced by the calibration, not by the brand</h2>
            <p className="lede">We service almost all makes and models, including Tesla. If you have a question about a specific car, call or text and we will answer right away.</p>
            <div className="rate-sheet">
              {RATES.map(([name, price, copy]) => (
                <article key={name}>
                  <h3>{name}</h3>
                  <p className="rate">{price} <span>per calibration</span></p>
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
            <h2 className="display">Try us for $50</h2>
            <div className="offer-sheet">
              <article>
                <p className="amount">$50 <span>first calibration</span></p>
                <p>Your first job with us is $50, so you can see how the process feels in your shop before you commit to regular work.</p>
              </article>
              <article>
                <h3>The 5-Star Guarantee</h3>
                <p>You only pay that $50 if the first job earns your shop a 5-star review.</p>
                <p>If your customer does not leave your shop a 5-star review after we handle their calibration, you do not pay a dime for that first job.</p>
              </article>
            </div>
          </div>
        </section>

        <section className="section band">
          <div className="container">
            <h2 className="display">Built around your bay, not a drop-off lot</h2>
            <div className="bay-notes">
              {REASONS.map(([title, copy]) => (
                <article key={title}><h3>{title}</h3><p>{copy}</p></article>
              ))}
            </div>
          </div>
        </section>

        <section className="section">
          <div className="container">
            <h2 className="display">Don't take our word for it</h2>
            <p className="lede">These are reviews The Calibration Crew already uses on shop flyers.</p>
            <div className="flyer-quotes">
              {QUOTES.map(([quote, cite]) => (
                <blockquote key={cite}><p>“{quote}”</p><cite>{cite}</cite></blockquote>
              ))}
            </div>
          </div>
        </section>

        <section className="section band" id="faq">
          <div className="container">
            <h2 className="display">Common questions from shops</h2>
            <FaqList />
          </div>
        </section>

        <section className="close-band">
          <div className="container">
            <h2 className="display">Ready for the next windshield?</h2>
            <p className="lede">Create a shop account to get into CalibrationOS. After that, you can log in anytime to book and get reports.</p>
            <div className="btn-row">
              <Link className="btn btn-primary btn-lg" to="/signup">Create your shop account</Link>
              <Link className="btn btn-ghost btn-lg" to="/portal/login">Log in</Link>
            </div>
          </div>
        </section>
      </div>
    </SiteChrome>
  );
}

