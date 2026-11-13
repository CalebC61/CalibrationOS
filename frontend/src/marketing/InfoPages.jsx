import { Link } from "react-router-dom";
import { FaqList, SiteChrome } from "./SiteChrome";

const CITIES = ["Phoenix", "Mesa", "Chandler", "Gilbert", "Tempe", "Scottsdale", "Glendale", "Peoria", "Surprise", "Buckeye", "Goodyear", "Avondale", "Queen Creek", "Apache Junction", "San Tan Valley", "Gold Canyon", "Maricopa", "Casa Grande", "Florence", "Black Canyon City"];

export function ServicesPage() {
  return (
    <SiteChrome>
      <section className="page-hero">
        <div className="container">
          <p className="section-kicker">Services</p>
          <h1 className="display">ADAS calibration, at your shop or on the driveway</h1>
          <p className="lede">Static, dynamic, dual, triple / Subaru, and Tesla work for auto glass shops, plus radar and camera calibrations for collision and body shops. Every job follows the OEM procedure for that vehicle.</p>
          <div className="btn-row">
            <Link className="btn btn-primary" to="/signup">Create your shop account</Link>
            <Link className="btn btn-ghost" to="/pricing">View pricing</Link>
          </div>
        </div>
      </section>
      <section className="section" style={{ paddingTop: "1.5rem" }}>
        <div className="container">
          <div className="svc-grid">
            <article className="svc">
              <h3>Static calibration</h3>
              <div className="price-tag">$125</div>
              <p>Done with the vehicle parked, using manufacturer-specific targets and tools to realign cameras and sensors.</p>
              <ul>
                <li>Windshield-mounted cameras after glass replacement</li>
                <li>Lane departure, lane keep, and similar camera systems</li>
                <li>Other static OEM procedures that can be completed in the bay</li>
              </ul>
            </article>
            <article className="svc">
              <h3>Dynamic calibration</h3>
              <div className="price-tag">$125</div>
              <p>Completed on the road with a scan tool, under the speeds and conditions the manufacturer calls for.</p>
              <ul>
                <li>Systems that need a drive to finish the calibration</li>
                <li>Lane keep, adaptive cruise, and similar drive-based procedures</li>
                <li>Used when the OEM process is dynamic-only, or as the drive portion of a larger job</li>
              </ul>
            </article>
            <article className="svc">
              <h3>Dual calibration</h3>
              <div className="price-tag">$175</div>
              <p>Static and dynamic together, when the vehicle needs both to complete the OEM procedure.</p>
              <ul>
                <li>Common after some windshield replacements</li>
                <li>One visit covers the target work and the road drive</li>
                <li>Priced as a combined calibration, not two separate invoices</li>
              </ul>
            </article>
            <article className="svc">
              <h3>Triple / Subaru calibration</h3>
              <div className="price-tag">$185</div>
              <p>Three-camera and Subaru EyeSight calibrations, when the OEM procedure calls for the triple setup.</p>
              <ul>
                <li>Multi-camera systems that need more than a dual calibration</li>
                <li>Subaru EyeSight after windshield replacement</li>
                <li>Booked as its own calibration type</li>
              </ul>
            </article>
            <article className="svc">
              <h3>Tesla calibration</h3>
              <div className="price-tag">$225</div>
              <p>Tesla windshield and camera calibration, following Tesla's process. Tesla work is often a dynamic, drive-based procedure.</p>
              <ul>
                <li>Windshield replacements on Tesla vehicles</li>
                <li>Camera alignment for Autopilot and related features</li>
                <li>Booked as its own calibration type</li>
              </ul>
            </article>
          </div>
        </div>
      </section>
      <section className="section band">
        <div className="container two-col">
          <div>
            <p className="section-kicker">For glass shops</p>
            <h2 className="display">After the windshield goes in</h2>
            <p className="lede">If the car has a camera behind the mirror, a new windshield means that camera has to be recalibrated so lane-keep and auto-braking work right. We handle that last step so the job does not leave your shop unfinished.</p>
            <ul className="include">
              <li>Mobile service at your bay or the customer's driveway</li>
              <li>Book online in under a minute</li>
              <li>Job updates by text</li>
              <li>Same-day reports and invoices</li>
            </ul>
          </div>
          <div>
            <p className="section-kicker">For collision and body shops</p>
            <h2 className="display">After the bumper comes off</h2>
            <p className="lede">Mobile ADAS calibration at your shop after bumper, body, and structural repairs. No sublet trip, and no vehicle leaving your lot.</p>
            <ul className="include">
              <li>Front radar for adaptive cruise and auto-braking</li>
              <li>Blind-spot and rear radar</li>
              <li>Forward and surround-view cameras</li>
              <li>Performed to OEM procedures</li>
              <li>Pre- and post-scan reports for insurers</li>
            </ul>
          </div>
        </div>
      </section>
      <section className="cta-final">
        <div className="container">
          <h2 className="display">Get the shop into CalibrationOS</h2>
          <p className="lede">Sign up to book calibrations, track jobs, and download reports. Or call (480) 269-1329 if you want to talk through a vehicle first.</p>
          <div className="btn-row" style={{ justifyContent: "center" }}>
            <Link className="btn btn-primary btn-lg" to="/signup">Create your shop account</Link>
            <Link className="btn btn-ghost btn-lg" to="/contact">Contact us</Link>
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}

export function PricingPage() {
  return (
    <SiteChrome>
      <section className="page-hero">
        <div className="container">
          <p className="section-kicker">Pricing</p>
          <h1 className="display">Clear rates, and a first job that is easy to try</h1>
          <p className="lede">Prices are set by the type of calibration, not by the car brand. We service almost all makes and models, including Tesla. Questions about a specific vehicle? Call or text (480) 269-1329.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: "1rem" }}>
        <div className="container">
          <div className="price-grid">
            {[
              ["Static calibration", "$125", "Parked, target-based calibration for cameras and other systems the OEM process can complete in the bay."],
              ["Dynamic calibration", "$125", "A road drive with the scan tool when the manufacturer requires it."],
              ["Dual calibration", "$175", "Static and dynamic in one job, when the vehicle needs both."],
              ["Triple / Subaru", "$185", "Three-camera and Subaru EyeSight calibrations, booked as their own type."],
              ["Tesla calibration", "$225", "Tesla windshield and camera calibration, booked as its own type."],
            ].map(([name, price, copy]) => (
              <article className="price-card" key={name}>
                <h3>{name}</h3>
                <div className="amount">{price}</div>
                <p className="each">per calibration</p>
                <p>{copy}</p>
              </article>
            ))}
          </div>
          <div className="offer">
            <article className="offer-card">
              <p className="section-kicker" style={{ margin: "0 0 0.4rem" }}>First job</p>
              <div className="amount">$50 <span>to try us out</span></div>
              <p>The first calibration for a new shop is $50. After that, the standard rates above apply.</p>
            </article>
            <article className="offer-card">
              <p className="section-kicker" style={{ margin: "0 0 0.4rem" }}>5-Star Guarantee</p>
              <h3>You only pay the $50 if that first job earns your shop a 5-star review.</h3>
              <p style={{ marginTop: "0.8rem" }}>If your customer does not leave your shop a 5-star review after we handle their calibration, you do not pay for the first job.</p>
            </article>
          </div>
        </div>
      </section>
      <section className="section band">
        <div className="container two-col">
          <div>
            <p className="section-kicker">Included with the work</p>
            <h2 className="display">No surprise add-on for a same-day extra car</h2>
            <ul className="include">
              <li>Same-day add-ons are welcome at no additional charge, if a slot is open. Call or text the office to check.</li>
              <li>Same-day reports and invoices</li>
              <li>Documentation for insurance, including pre- and post-scan reports when the job needs them</li>
              <li>Online scheduling and job updates by text</li>
            </ul>
          </div>
          <div className="card">
            <p className="section-kicker">Referral program</p>
            <h2>Send us a shop, both of you save</h2>
            <p>If you refer another auto glass company and they complete their first job with us, they get $50 off and you get $100 off. Have them mention your shop name so the credit is applied.</p>
          </div>
        </div>
      </section>
      <section className="cta-final">
        <div className="container">
          <h2 className="display">Create a shop account to book the first job</h2>
          <div className="btn-row" style={{ justifyContent: "center" }}>
            <Link className="btn btn-primary btn-lg" to="/signup">Create your shop account</Link>
            <a className="btn btn-ghost btn-lg" href="https://calendly.com/calcrew/adas-calibration-appointment" target="_blank" rel="noopener noreferrer">Book a job</a>
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}

export function AreaPage() {
  return (
    <SiteChrome>
      <section className="page-hero">
        <div className="container">
          <p className="section-kicker">Service area</p>
          <h1 className="display">Valley-wide, East and West</h1>
          <p className="lede">We are based in Gilbert and travel to shops and driveways across the greater Phoenix area.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: "1rem" }}>
        <div className="container area-split">
          <div className="map-frame">
            <img src="/marketing/service-area.png" alt="Map of The Calibration Crew service area around Phoenix, outlined from Buckeye to Florence and down to Casa Grande" />
          </div>
          <div>
            <h2>How far we travel</h2>
            <p>Currently, we will travel as far west as Buckeye, as far north as Black Canyon City, as far east as Gold Canyon and Highway 79, and as far south as Casa Grande.</p>
            <p>That covers both the East Valley and the West Valley. If you are on the edge of the map and not sure we can reach you, call or text (480) 269-1329 and we will tell you straight.</p>
            <div className="btn-row">
              <Link className="btn btn-primary" to="/signup">Create your shop account</Link>
              <Link className="btn btn-ghost" to="/contact">Ask about a location</Link>
            </div>
          </div>
        </div>
        <div className="container" style={{ marginTop: "2.5rem" }}>
          <h2>Cities in the service area</h2>
          <p className="lede">A sample of cities inside those boundaries. If your shop is in the Valley and you do not see it here, you are still likely covered.</p>
          <div className="city-grid">
            {CITIES.map(city => <div className="city" key={city}>{city}</div>)}
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}

export function AboutPage() {
  return (
    <SiteChrome>
      <section className="page-hero">
        <div className="container">
          <p className="section-kicker">About us</p>
          <h1 className="display">A mobile ADAS crew, built for glass shops</h1>
          <p className="lede">The Calibration Crew is a Gilbert, Arizona company that comes to you, books in one place, and treats the calibration like it is part of your shop's job, not a handoff that can go sideways.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: "1rem" }}>
        <div className="container about-split">
          <div>
            <h2>How we started</h2>
            <p>Caleb Cerdhe has been an ADAS calibration technician since May 2022, when he joined Complete Calibrations and began running a mobile camera calibration route in the Valley. He later founded The Calibration Crew so auto glass shops would have a dedicated mobile partner they could book without the usual back and forth.</p>
            <p>The company is based in Gilbert and is family run. Caleb is the technician in the field. His wife, Maddy, helps run the business. We work Monday through Saturday, and we speak English and Spanish.</p>
            <p>Today shops book through CalibrationOS, our shop portal for scheduling, job tracking, and reports. You can also call, text, or use our online scheduler.</p>
          </div>
          <div>
            <div className="card" style={{ marginBottom: "1rem" }}>
              <h3>What we aim to be for your shop</h3>
              <p>An extension of your brand. On-time arrival, clear communication, and documentation for every job, so the calibration helps your customer's experience instead of putting it at risk.</p>
            </div>
            <div className="card">
              <h3>The work itself</h3>
              <p>Mobile ADAS calibration across the Phoenix Valley: static, dynamic, dual, and Tesla, plus radar and camera work for collision shops. Calibrations follow OEM procedures. Reports and invoices go out the same day.</p>
            </div>
          </div>
        </div>
      </section>
      <section className="section band">
        <div className="container">
          <p className="section-kicker">From people we have already worked with</p>
          <h2 className="display">A few words shops and customers have shared</h2>
          <div className="quotes">
            <blockquote className="quote">
              <p>“Caleb is a superstar for sure. We are very fortunate to have him part of our team.”</p>
              <cite>Owner of Preferred Auto Glass</cite>
            </blockquote>
            <blockquote className="quote">
              <p>“Caleb came to do my recalibration for my cameras and sensors. Caleb was great, he answered all of my questions and was very quick.”</p>
              <cite>Google review</cite>
            </blockquote>
          </div>
        </div>
      </section>
      <section className="cta-final">
        <div className="container">
          <h2 className="display">Work with the crew</h2>
          <div className="btn-row" style={{ justifyContent: "center" }}>
            <Link className="btn btn-primary btn-lg" to="/signup">Create your shop account</Link>
            <Link className="btn btn-ghost btn-lg" to="/contact">Get in touch</Link>
          </div>
        </div>
      </section>
    </SiteChrome>
  );
}

export function FaqPage() {
  return (
    <SiteChrome>
      <section className="page-hero">
        <div className="container">
          <p className="section-kicker">FAQ</p>
          <h1 className="display">Common questions from shops</h1>
          <p className="lede">Prices, the valley, and how a shop gets into CalibrationOS.</p>
        </div>
      </section>
      <section className="section" style={{ paddingTop: "1rem" }}>
        <div className="container">
          <FaqList />
        </div>
      </section>
    </SiteChrome>
  );
}
