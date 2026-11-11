import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

const TABS = ["pricing", "technicians", "schedule", "contractor", "integrations"];

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
      {tab === "technicians" && <TechniciansTab />}
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

function TechniciansTab() {
  const [techs, setTechs] = useState([]);
  const [edits, setEdits] = useState({});
  const [savingId, setSavingId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ name: "", phone: "", home_address: "", service_radius_miles: "" });

  async function load() {
    const { data } = await api.get("/routing-techs");
    setTechs(data);
    const next = {};
    data.forEach(t => {
      next[t.id] = {
        name: t.name || "",
        phone: t.phone || "",
        home_address: t.home_address || "",
        service_radius_miles: t.service_radius_miles ?? "",
        day_start: (t.day_start || "08:00").slice(0, 5),
        day_end: (t.day_end || "19:00").slice(0, 5),
        is_active: t.is_active !== false,
      };
    });
    setEdits(next);
  }
  useEffect(() => { load(); }, []);

  function patch(id, fields) {
    setEdits(current => ({ ...current, [id]: { ...current[id], ...fields } }));
  }

  async function save(id) {
    const edit = edits[id];
    setSavingId(id);
    try {
      await api.put(`/routing-techs/${id}`, {
        name: edit.name,
        phone: edit.phone || null,
        home_address: edit.home_address,
        service_radius_miles: edit.service_radius_miles === "" ? null : Number(edit.service_radius_miles),
        clear_service_radius: edit.service_radius_miles === "",
        day_start: edit.day_start,
        day_end: edit.day_end,
        is_active: edit.is_active,
      });
      await load();
    } catch (e) {
      alert(typeof e.response?.data?.detail === "string" ? e.response.data.detail : "Save failed");
    } finally { setSavingId(null); }
  }

  async function createTech() {
    setCreating(true);
    try {
      await api.post("/routing-techs", {
        name: draft.name,
        phone: draft.phone || null,
        home_address: draft.home_address,
        service_radius_miles: draft.service_radius_miles === "" ? null : Number(draft.service_radius_miles),
      });
      setDraft({ name: "", phone: "", home_address: "", service_radius_miles: "" });
      await load();
    } catch (e) {
      alert(typeof e.response?.data?.detail === "string" ? e.response.data.detail : "Could not add that technician.");
    } finally { setCreating(false); }
  }

  return (
    <div data-testid="technicians-tab" style={{ maxWidth: 720 }}>
      <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
        With one technician, every Phoenix Valley job goes to them. Add another home base and jobs split by whoever is nearest, or by a service radius when you set one. Saving does not send a message.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {techs.map(t => (
          <div key={t.id} className="surface" style={{ padding: 20 }} data-testid={`routing-tech-${t.id}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div className="h3" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: 99, background: t.color || "#FF5F1F" }} />
                {t.role === "owner" ? "Owner" : "Technician"}
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                <input type="checkbox" checked={edits[t.id]?.is_active || false}
                  onChange={e => patch(t.id, { is_active: e.target.checked })} />
                Active
              </label>
            </div>
            <Row>
              <Field label="Name"><input className="input" value={edits[t.id]?.name || ""}
                onChange={e => patch(t.id, { name: e.target.value })} data-testid={`tech-name-${t.id}`} /></Field>
              <Field label="Phone"><input className="input" value={edits[t.id]?.phone || ""}
                onChange={e => patch(t.id, { phone: e.target.value })} /></Field>
            </Row>
            <Field label="Home base"><input className="input" value={edits[t.id]?.home_address || ""}
              onChange={e => patch(t.id, { home_address: e.target.value })} data-testid={`tech-home-${t.id}`} /></Field>
            <Row>
              <Field label="Day start"><input className="input" type="time" value={edits[t.id]?.day_start || "08:00"}
                onChange={e => patch(t.id, { day_start: e.target.value })} /></Field>
              <Field label="Day end"><input className="input" type="time" value={edits[t.id]?.day_end || "19:00"}
                onChange={e => patch(t.id, { day_end: e.target.value })} /></Field>
            </Row>
            <Field label="Service radius in miles (optional)">
              <input className="input" type="number" min="1" step="1" placeholder="Blank covers by nearest home"
                value={edits[t.id]?.service_radius_miles ?? ""}
                onChange={e => patch(t.id, { service_radius_miles: e.target.value })} />
            </Field>
            <button className="btn btn-primary" onClick={() => save(t.id)} disabled={savingId === t.id}
              data-testid={`save-tech-${t.id}`}>{savingId === t.id ? "Saving…" : "Save"}</button>
          </div>
        ))}
        <div className="surface" style={{ padding: 20 }}>
          <div className="h3" style={{ marginBottom: 12 }}>Add a technician</div>
          <Row>
            <Field label="Name"><input className="input" value={draft.name}
              onChange={e => setDraft({ ...draft, name: e.target.value })} data-testid="new-tech-name" /></Field>
            <Field label="Phone"><input className="input" value={draft.phone}
              onChange={e => setDraft({ ...draft, phone: e.target.value })} /></Field>
          </Row>
          <Field label="Home base"><input className="input" value={draft.home_address}
            onChange={e => setDraft({ ...draft, home_address: e.target.value })} data-testid="new-tech-home" /></Field>
          <Field label="Service radius in miles (optional)">
            <input className="input" type="number" min="1" value={draft.service_radius_miles}
              onChange={e => setDraft({ ...draft, service_radius_miles: e.target.value })} />
          </Field>
          <button className="btn btn-primary" onClick={createTech} disabled={creating || !draft.name || !draft.home_address}
            data-testid="add-tech">{creating ? "Adding…" : "Add technician"}</button>
        </div>
      </div>
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
    <div data-testid="schedule-tab">
    <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
      Booking no longer splits the valley into East and West. These clocks are leftover and are not used to place jobs.
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 16, maxWidth: 800 }}>
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
  const maps = status?.google_maps;
  const others = [
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

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
        <div>
          <div style={{ fontWeight: 600 }}>Partner Growth Engine</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {!status ? "Loading…"
              : status.growth?.enabled ? `Enabled — ${status.growth.contact_count} contact${status.growth.contact_count === 1 ? "" : "s"}`
              : "Disabled — set GROWTH_MODULE_ENABLED=true"}
          </div>
        </div>
        {status?.growth?.enabled && (
          <a href="/growth" className="btn btn-ghost" data-testid="growth-open-link">Open Growth</a>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border)" }} data-testid="assist-status-row">
        <div>
          <div style={{ fontWeight: 600 }}>Assist (AI copilot)</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {!status ? "Loading…"
              : status.assist?.enabled ? "Live — chat bubble on every admin page; actions require your confirmation"
              : status.assist?.configured ? "Disabled — set ASSIST_MODULE_ENABLED=true"
              : "Not configured — set GOOGLE_API_KEY (Google AI Studio)"}
          </div>
        </div>
        {status && !status.assist?.enabled && (
          <span style={{ color: "var(--yellow)", fontSize: 13 }}>Off</span>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--border)" }} data-testid="maps-status-row">
        <div>
          <div style={{ fontWeight: 600 }}>Google Maps</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {!status ? "Loading…"
              : maps?.mode === "live" ? "Live — real geocoding + drive times (Distance Matrix, daily-cached)"
              : "Not configured — set GOOGLE_MAPS_API_KEY (mock geocoding/drive-time active)"}
          </div>
        </div>
        {status && maps?.mode !== "live" && (
          <span style={{ color: "var(--yellow)", fontSize: 13 }}>Mock mode</span>
        )}
      </div>

      {others.map(i => (
        <div key={i.name} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
          <span style={{ fontWeight: 600 }}>{i.name}</span>
          <span style={{ color: i.color, fontSize: 13 }}>{i.status}</span>
        </div>
      ))}
      <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>
        Xero and Google Maps go live automatically once their credentials are set (Xero also needs
        Connect); the remaining integrations stay mocked until later steps.
      </div>
    </div>
  );
}

const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (<div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>);
