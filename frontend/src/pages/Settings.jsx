import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

export default function Settings() {
  const [pricing, setPricing] = useState([]);
  const [zones, setZones] = useState([]);
  useEffect(() => {
    api.get("/reference/pricing").then(r => setPricing(r.data));
    api.get("/reference/zones").then(r => setZones(r.data));
  }, []);
  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 20 }}>Settings</h1>

      <Section title="Standard Pricing">
        <div className="surface" style={{ padding: 16 }}>
          {pricing.map(p => (
            <div key={p.calibration_type} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
              <span>{p.label}</span>
              <span className="font-mono">${p.price.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Operating Zones">
        <div className="surface" style={{ padding: 16 }}>
          {zones.map(z => (
            <div key={z.slug} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
              <div>
                <span className={`badge badge-${z.slug}`}>{z.name}</span>
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                  {z.start} – {z.end} · max {z.max_jobs} jobs/day · {z.slot_minutes}-min slots
                </div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Integrations (mocked)">
        <div className="surface" style={{ padding: 16 }}>
          {[
            { name: "Xero", status: "Mock — invoices simulated", color: "var(--yellow)" },
            { name: "Google Maps", status: "Mock — keyword-based geocoding", color: "var(--yellow)" },
            { name: "Twilio SMS", status: "Mock — messages logged in app", color: "var(--yellow)" },
            { name: "Google Calendar", status: "Deferred to next iteration", color: "var(--text-muted)" },
          ].map(i => (
            <div key={i.name} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
              <span style={{ fontWeight: 600 }}>{i.name}</span>
              <span style={{ color: i.color, fontSize: 13 }}>{i.status}</span>
            </div>
          ))}
          <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>
            When you&apos;re ready, provide your API keys and we&apos;ll wire real integrations.
          </div>
        </div>
      </Section>
    </Shell>
  );
}

const Section = ({ title, children }) => (
  <section style={{ marginBottom: 24 }}>
    <h2 className="h3" style={{ marginBottom: 10 }}>{title}</h2>
    {children}
  </section>
);
