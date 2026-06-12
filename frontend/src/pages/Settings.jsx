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
  const [xero, setXero] = useState(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);

  async function loadXero() {
    try {
      const { data } = await api.get("/xero/status");
      setXero(data);
    } catch (e) { setXero({ connected: false }); }
  }
  useEffect(() => {
    loadXero();
    // Detect callback redirect query string
    const url = new URL(window.location.href);
    const xeroParam = url.searchParams.get("xero");
    if (xeroParam === "connected") {
      setFlash({ kind: "success", msg: "Xero connected. Invoices will be pushed automatically on job completion." });
      url.searchParams.delete("xero");
      window.history.replaceState({}, "", url.toString());
      setTimeout(() => setFlash(null), 5000);
    } else if (xeroParam === "error") {
      setFlash({ kind: "error", msg: `Xero connection failed: ${url.searchParams.get("detail") || "unknown"}` });
      url.searchParams.delete("xero"); url.searchParams.delete("detail");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  async function connectXero() {
    setBusy(true);
    try {
      const { data } = await api.get("/xero/auth/start");
      window.location.href = data.authorize_url;
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to start Xero auth");
      setBusy(false);
    }
  }

  async function disconnectXero() {
    if (!window.confirm("Disconnect Xero? Existing invoices in Xero are kept but new jobs won't auto-push until you reconnect.")) return;
    setBusy(true);
    try {
      await api.post("/xero/disconnect");
      await loadXero();
    } catch (e) { alert(e.response?.data?.detail || "Disconnect failed"); }
    finally { setBusy(false); }
  }

  async function refreshAll() {
    setBusy(true);
    try {
      const { data } = await api.post("/xero/refresh-all");
      setFlash({ kind: "success", msg: `Refreshed ${data.refreshed}/${data.total} invoice statuses.` });
      setTimeout(() => setFlash(null), 4000);
    } catch (e) { alert(e.response?.data?.detail || "Refresh failed"); }
    finally { setBusy(false); }
  }

  return (
    <div style={{ maxWidth: 640, display: "flex", flexDirection: "column", gap: 16 }} data-testid="integrations-tab">
      {flash && (
        <div style={{
          padding: "10px 14px", borderRadius: 8,
          background: flash.kind === "success" ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
          border: `1px solid ${flash.kind === "success" ? "rgba(16,185,129,0.4)" : "rgba(239,68,68,0.4)"}`,
          color: flash.kind === "success" ? "var(--green)" : "var(--red)",
          fontSize: 14,
        }} data-testid="xero-flash">{flash.msg}</div>
      )}

      <div className="surface" style={{ padding: 20 }} data-testid="xero-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div>
            <div className="h3" style={{ marginBottom: 4 }}>Xero Accounting</div>
            <div className="muted" style={{ fontSize: 13 }}>
              {xero?.connected
                ? <>Connected to <b style={{ color: "var(--text)" }}>{xero.org_name}</b> · tenant <span className="font-mono" style={{ fontSize: 11 }}>{xero.tenant_id?.slice(0, 8)}…</span></>
                : "Not connected. Invoices currently use the internal mock."}
            </div>
          </div>
          <span className="badge" style={{
            background: xero?.connected ? "rgba(16,185,129,0.18)" : "rgba(245,158,11,0.18)",
            color: xero?.connected ? "var(--green)" : "var(--yellow)",
            border: `1px solid ${xero?.connected ? "rgba(16,185,129,0.4)" : "rgba(245,158,11,0.4)"}`,
          }}>{xero?.connected ? "LIVE" : "MOCK"}</span>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
          {xero?.connected ? (
            <>
              <button className="btn btn-ghost" onClick={refreshAll} disabled={busy} data-testid="xero-refresh-all">
                Refresh all invoice statuses
              </button>
              <button className="btn btn-ghost" onClick={disconnectXero} disabled={busy} data-testid="xero-disconnect">
                Disconnect
              </button>
            </>
          ) : (
            <button className="btn btn-primary" onClick={connectXero} disabled={busy} data-testid="xero-connect">
              {busy ? "Opening Xero…" : "Connect to Xero"}
            </button>
          )}
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>
          When connected, completed jobs auto-push a DRAFT invoice to Xero with the calibration label, vehicle reference, and a $0 description line — keyed by our internal job id in the Reference field.
        </div>
      </div>

      <div className="surface" style={{ padding: 20 }}>
        <div className="h3" style={{ marginBottom: 10 }}>Other Integrations</div>
        {[
          { name: "Stripe (card-on-file)", status: "Live — test mode", color: "var(--green)" },
          { name: "Google Maps", status: "Live — Geocoding + Distance Matrix", color: "var(--green)" },
          { name: "Resend (email)", status: "Live", color: "var(--green)" },
          { name: "Linqapp (SMS)", status: "Blocked — destination phone not verified in sandbox", color: "var(--red)" },
          { name: "Google Calendar", status: "Pending OAuth setup", color: "var(--yellow)" },
        ].map(i => (
          <div key={i.name} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
            <span style={{ fontWeight: 600 }}>{i.name}</span>
            <span style={{ color: i.color, fontSize: 13 }}>{i.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (<div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>);
