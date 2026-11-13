import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { getStoredAuth } from "../lib/api";
import "./marketing.css";

const LOGO = "/marketing/logo-crew-transparent.png";

const LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/services", label: "Services" },
  { to: "/pricing", label: "Pricing" },
  { to: "/service-area", label: "Service Area" },
  { to: "/about", label: "About" },
  { to: "/faq", label: "FAQ" },
  { to: "/contact", label: "Contact" },
];

export function SiteChrome({ children }) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const staff = getStoredAuth();
  return (
    <div className={"marketing" + (open ? " nav-open" : "")}>
      <header className="site-header">
        <div className="container header-inner">
          <Link className="brand" to="/" aria-label="The Calibration Crew home" onClick={() => setOpen(false)}>
            <img src={LOGO} alt="The Calibration Crew" width="190" height="96" />
          </Link>
          <button
            className="menu-toggle"
            type="button"
            aria-expanded={open}
            aria-controls="site-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen(v => !v)}
          >
            <span /><span /><span />
          </button>
          <nav className="site-nav" id="site-nav">
            <div className="nav-links">
              {LINKS.map(link => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.end}
                  className={({ isActive }) => (isActive || (link.to === "/faq" && loc.hash === "#faq") ? "is-active" : "")}
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                </NavLink>
              ))}
            </div>
            <div className="nav-actions">
              <Link className="link-quiet" to={staff ? "/dashboard" : "/login"} onClick={() => setOpen(false)}>
                {staff ? "Dispatch" : "Staff login"}
              </Link>
              <Link className="btn btn-primary" to="/signup" onClick={() => setOpen(false)}>Sign up</Link>
            </div>
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <div className="container footer-grid">
          <div>
            <Link className="brand brand-footer" to="/" aria-label="The Calibration Crew home">
              <img src={LOGO} alt="The Calibration Crew" width="180" height="91" />
            </Link>
            <p className="footer-lead">Mobile ADAS calibration for auto glass shops, collision shops, and the Phoenix Valley.</p>
            <p className="legal">The Calibration Crew LLC · Gilbert, AZ</p>
            <p className="legal">Monday through Saturday</p>
            <p className="legal">Hablo Español</p>
          </div>
          <div>
            <h2>Pages</h2>
            <ul>
              <li><Link to="/services">Services</Link></li>
              <li><Link to="/pricing">Pricing</Link></li>
              <li><Link to="/service-area">Service Area</Link></li>
              <li><Link to="/about">About Us</Link></li>
              <li><Link to="/faq">FAQ</Link></li>
              <li><Link to="/contact">Contact</Link></li>
            </ul>
          </div>
          <div>
            <h2>CalibrationOS</h2>
            <ul>
              <li><Link to="/signup">Create a shop account</Link></li>
              <li><Link to="/portal/login">Shop login</Link></li>
              <li><Link to="/login">Staff login</Link></li>
              <li><a href="https://calendly.com/calcrew/adas-calibration-appointment" target="_blank" rel="noopener noreferrer">Book a job</a></li>
            </ul>
          </div>
          <div>
            <h2>Contact</h2>
            <ul>
              <li><a href="tel:4802691329">(480) 269-1329</a></li>
              <li><a href="mailto:admin@thecalibrationcrew.us">admin@thecalibrationcrew.us</a></li>
              <li>thecalibrationcrew.us</li>
              <li>Gilbert, AZ · Phoenix Valley</li>
            </ul>
          </div>
        </div>
        <div className="container footer-bottom">
          <p>© 2026 The Calibration Crew LLC</p>
        </div>
      </footer>
    </div>
  );
}

export const FAQS = [
  ["How do we start booking with you?", "Create a shop account in CalibrationOS. That is how you get access to book, track jobs, and pull reports. You can also call or text (480) 269-1329."],
  ["What does a calibration cost?", "Static and dynamic calibrations are $125. Dual is $175. Triple / Subaru is $185. Tesla is $225. Your first job with us is $50, and that $50 is covered by the 5-Star Guarantee: you only pay it if the first job earns your shop a 5-star review."],
  ["Do you come to the shop or to the customer?", "Both. We calibrate at your bay or at your customer's driveway, whichever the job needs."],
  ["Where do you service?", "The Phoenix Valley, East and West. We travel as far west as Buckeye, as far north as Black Canyon City, as far east as Gold Canyon and Highway 79, and as far south as Casa Grande. We are based in Gilbert."],
  ["What days are you available?", "Monday through Saturday. Same-day add-ons are welcome at no additional charge if a slot is open. Call or text the office to check."],
  ["Do you work on Teslas and radar jobs?", "Yes. Tesla calibrations are $225. We also handle front radar, blind-spot and rear radar, and forward and surround-view cameras, including work for collision and body shops after bumper or structural repairs. Calibrations follow OEM procedures, with pre- and post-scan reports when needed for insurers."],
  ["Do you speak Spanish?", "Sí. Hablo Español."],
];

export function FaqList() {
  const [open, setOpen] = useState(0);
  return (
    <div className="faq-list">
      {FAQS.map(([q, a], i) => (
        <div className={"faq-item" + (open === i ? " is-open" : "")} key={q}>
          <button type="button" aria-expanded={open === i} onClick={() => setOpen(open === i ? -1 : i)}>
            {q} <span className="mark">{open === i ? "–" : "+"}</span>
          </button>
          <div className="faq-body">{a}</div>
        </div>
      ))}
    </div>
  );
}
