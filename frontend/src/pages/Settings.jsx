import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

const TABS = ["pricing", "schedule", "contractor", "integrations"];

export default function Settings() {
  const [tab, setTab] = useState("pricing");
  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 16 }}>Settings</h1>
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid var(--border)" }}>
        {TABS.map(t => (
          <button key={t} className={"tab-btn" + (tab === t ? " active" : "")}
            onClick={() => setTab(t)} data-testid={`tab-${t}`}
            style={{ textTransform: "capitalize" }}>{t}</button>
        ))}
      </div>
      {tab === "pricing" && <PricingTab />}
      {tab === "schedule" && <ScheduleTab />}
      {tab === "contractor" && <ContractorTab />}
      {tab === "integrations" && <IntegrationsTab />}
    </Shell>
  );
}

function PricingTab() {
  const [pricing, setPricing] = useState([]);
  const [edit, setEdit] = useState({});
  const [saving, setSaving] = useState(false);

  async function load() {
    const { data } = await api.get("/reference/pricing");
    setPricing(data);
    const map = {}; data.forEach(p => { map[p.calibration_type] = p.price; });
    setEdit(map);
  }
  useEffect(() => { load(); }, []);

  async function save() {
    setSaving(true);
    try {
      await api.put("/settings/pricing", edit);
      await load();
      alert("Pricing saved.");
    } catch (e) { alert(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  }

  return (
    <div className="surface" style={{ padding: 20, maxWidth: 560 }} data-testid="pricing-tab">
      <div className="h3" style={{ marginBottom: 12 }}>Standard Pricing</div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>Per-shop custom rates override these defaults.</div>
      {pricing.map(p => (
        <div key={p.calibration_type} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
          <div style={{ flex: 1 }}>{p.label}</div>
          <div style={{ width: 140 }}>
            <input className="input" type="number" step="0.01" value={edit[p.calibration_type] ?? p.price}
              onChange={e => setEdit({...edit, [p.calibration_type]: parseFloat(e.target.value)})}
              data-testid={`price-${p.calibration_type}`} />
          </div>
        </div>
      ))}
      <button className="btn btn-primary" onClick={save} disabled={saving}
        style={{ marginTop: 16 }} data-testid="save-pricing">{saving ? "Saving…" : "Save Pricing"}</button>
    </div>
  );
}

function ScheduleTab() {
  const [zones, setZones] = useState([]);
  const [edit, setEdit] = useState({});
  const [saving, setSaving] = useState(null);

  async function load() {
    const { data } = await api.get("/reference/zones");
    setZones(data);
    const e = {};
    data.forEach(z => { e[z.slug] = { start: z.start, end: z.end, max_jobs: z.max_jobs, slot_minutes: z.slot_minutes, buffer_minutes: z.buffer_minutes }; });
    setEdit(e);
  }
  useEffect(() => { load(); }, []);

  async function save(slug) {
    setSaving(slug);
    try {
      await api.put(`/settings/zones/${slug}`, edit[slug]);
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Save failed"); }
    finally { setSaving(null); }
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 16, maxWidth: 800 }} data-testid="schedule-tab">
      {zones.map(z => (
        <div key={z.slug} className="surface" style={{ padding: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <span className={`badge badge-${z.slug}`}>{z.name}</span>
          </div>
          <Row>
            <Field label="Start time">
              <input className="input" type="time" value={edit[z.slug]?.start || ""}
                onChange={e => setEdit({...edit, [z.slug]: {...edit[z.slug], start: e.target.value + ":00"}})}
                data-testid={`zone-${z.slug}-start`} />
            </Field>
            <Field label="End time">
              <input className="input" type="time" value={edit[z.slug]?.end || ""}
                onChange={e => setEdit({...edit, [z.slug]: {...edit[z.slug], end: e.target.value + ":00"}})}
                data-testid={`zone-${z.slug}-end`} />
            </Field>
          </Row>
          <Row>
            <Field label="Max jobs/day">
              <input className="input" type="number" min="1" max="20" value={edit[z.slug]?.max_jobs || 7}
                onChange={e => setEdit({...edit, [z.slug]: {...edit[z.slug], max_jobs: parseInt(e.target.value)}})}
                data-testid={`zone-${z.slug}-maxjobs`} />
            </Field>
            <Field label="Slot length (min)">
              <input className="input" type="number" min="15" max="120" step="15" value={edit[z.slug]?.slot_minutes || 45}
                onChange={e => setEdit({...edit, [z.slug]: {...edit[z.slug], slot_minutes: parseInt(e.target.value)}})}
                data-testid={`zone-${z.slug}-slot`} />
            </Field>
          </Row>
          <Field label="Drive buffer (min)">
            <input className="input" type="number" min="0" max="60" value={edit[z.slug]?.buffer_minutes || 20}
              onChange={e => setEdit({...edit, [z.slug]: {...edit[z.slug], buffer_minutes: parseInt(e.target.value)}})}
              data-testid={`zone-${z.slug}-buffer`} />
          </Field>
          <button className="btn btn-primary" onClick={() => save(z.slug)} disabled={saving === z.slug}
            data-testid={`save-zone-${z.slug}`}>{saving === z.slug ? "Saving…" : "Save"}</button>
        </div>
      ))}
    </div>
  );
}

function ContractorTab() {
  const [contractors, setContractors] = useState([]);
  const [edits, setEdits] = useState({});
  const [savingId, setSavingId] = useState(null);

  async function load() {
    const { data } = await api.get("/contractors");
    setContractors(data);
    const e = {};
    data.forEach(c => { e[c.id] = { name: c.name, phone: c.phone, home_address: c.home_address, is_active: c.is_active }; });
    setEdits(e);
  }
  useEffect(() => { load(); }, []);

  async function save(id) {
    setSavingId(id);
    try {
      await api.put(`/contractors/${id}`, edits[id]);
      await load();
    } catch (e) { alert(e.response?.data?.detail || "Save failed"); }
    finally { setSavingId(null); }
  }

  return (
    <div data-testid="contractor-tab">
      {contractors.length === 0 && <div className="muted">No contractors. Add via direct DB seed for now.</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 640 }}>
        {contractors.map(c => (
          <div key={c.id} className="surface" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div className="h3">{c.name}</div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                <input type="checkbox" checked={edits[c.id]?.is_active || false}
                  onChange={e => setEdits({...edits, [c.id]: {...edits[c.id], is_active: e.target.checked}})}
                  data-testid={`contractor-active-${c.id}`} />
                Active
              </label>
            </div>
            <Row>
              <Field label="Name"><input className="input" value={edits[c.id]?.name || ""}
                onChange={e => setEdits({...edits, [c.id]: {...edits[c.id], name: e.target.value}})} /></Field>
              <Field label="Phone"><input className="input" value={edits[c.id]?.phone || ""}
                onChange={e => setEdits({...edits, [c.id]: {...edits[c.id], phone: e.target.value}})} /></Field>
            </Row>
            <Field label="Home address (used as drive origin)"><input className="input" value={edits[c.id]?.home_address || ""}
              onChange={e => setEdits({...edits, [c.id]: {...edits[c.id], home_address: e.target.value}})} /></Field>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>Email (login): {c.email}</div>
            <button className="btn btn-primary" onClick={() => save(c.id)} disabled={savingId === c.id}
              data-testid={`save-contractor-${c.id}`}>{savingId === c.id ? "Saving…" : "Save"}</button>
          </div>
        ))}
      </div>
    </div>
  );
}

function IntegrationsTab() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState(null);

  async function load() {
    try {
      const { data } = await api.get("/integrations/status");
      setStatus(data);
    } catch { /* leave status null → shows "Loading…" */ }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const x = params.get("xero");
    if (x === "connected") setBanner({ ok: true, msg: "Xero connected. Completed jobs will now create real draft invoices." });
    else if (x === "error") setBanner({ ok: false, msg: "Xero connection failed. Please try connecting again." });
    if (x) window.history.replaceState({}, "", window.location.pathname);
    load();
  }, []);

  async function connectXero() {
    setBusy(true);
    try {
      const { data } = await api.get("/auth/xero/connect");
      window.location.href = data.authorize_url;
    } catch (e) {
      setBanner({ ok: false, msg: e.response?.data?.detail || "Xero is not configured yet." });
      setBusy(false);
    }
  }

  async function disconnectXero() {
    if (!window.confirm("Disconnect Xero? New invoices will fall back to mock mode until reconnected.")) return;
    setBusy(true);
    try { await api.post("/auth/xero/disconnect"); await load(); }
    catch (e) { setBanner({ ok: false, msg: "Disconnect failed." }); }
    finally { setBusy(false); }
  }

  const xero = status?.xero;
  const others = [
    { name: "Google Maps", status: "Mock — keyword-based geocoding", color: "var(--yellow)" },
    { name: "Twilio SMS", status: "Mock — messages logged in app", color: "var(--yellow)" },
    { name: "Google Calendar", status: "Deferred to next iteration", color: "var(--text-muted)" },
  ];

  return (
    <div className="surface" style={{ padding: 20, maxWidth: 560 }} data-testid="integrations-tab">
      {banner && (
        <div data-testid="xero-banner" style={{
          padding: "10px 12px", borderRadius: 8, marginBottom: 14, fontSize: 13,
          background: banner.ok ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
          color: banner.ok ? "var(--green)" : "var(--red)",
        }}>{banner.msg}</div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
        <div>
          <div style={{ fontWeight: 600 }}>Xero</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {!xero ? "Loading…"
              : xero.connected ? `Connected${xero.org_name ? " — " + xero.org_name : ""}`
              : xero.configured ? "Configured — not connected"
              : "Not configured — set XERO_CLIENT_ID / SECRET / REDIRECT_URI (mock mode active)"}
          </div>
        </div>
        <div>
          {xero && xero.connected && (
            <button className="btn btn-danger" onClick={disconnectXero} disabled={busy} data-testid="xero-disconnect">Disconnect</button>
          )}
          {xero && !xero.connected && xero.configured && (
            <button className="btn btn-primary" onClick={connectXero} disabled={busy} data-testid="xero-connect">{busy ? "Opening…" : "Connect Xero"}</button>
          )}
          {xero && !xero.configured && (
            <span style={{ color: "var(--yellow)", fontSize: 13 }}>Mock mode</span>
          )}
        </div>
      </div>

      {others.map(i => (
        <div key={i.name} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
          <span style={{ fontWeight: 600 }}>{i.name}</span>
          <span style={{ color: i.color, fontSize: 13 }}>{i.status}</span>
        </div>
      ))}
      <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>
        Xero invoicing is live once connected; the remaining integrations stay mocked until later steps.
      </div>
    </div>
  );
}

const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (<div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>);
