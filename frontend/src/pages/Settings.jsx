import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

const TABS = ["pricing", "shops", "schedule", "contractor", "integrations"];

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
      {tab === "shops" && <ShopsTab />}
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


const STANDARD_PRICES = { static: 125, dynamic: 125, dual: 175, triple: 185, tesla: 225 };
const CAL_TYPES = [
  { k: "static",  l: "Static ADAS" },
  { k: "dynamic", l: "Dynamic ADAS" },
  { k: "dual",    l: "Dual ADAS" },
  { k: "triple",  l: "Triple / Subaru" },
  { k: "tesla",   l: "Tesla ADAS" },
];

function ShopsTab() {
  const [shops, setShops] = useState([]);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [savedFlash, setSavedFlash] = useState(null);

  async function load() {
    const { data } = await api.get("/shops");
    setShops(data);
  }
  useEffect(() => { load(); }, []);

  const filtered = shops.filter(s => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return [s.name, s.legal_name, s.contact_name, s.contact_email,
            s.contact_phone, s.address, s.city, s.zip]
      .filter(Boolean).some(v => String(v).toLowerCase().includes(q));
  });

  function onSaved(updated) {
    setShops(prev => prev.map(s => s.id === updated.id ? updated : s));
    setEditing(null);
    setSavedFlash(`Saved ${updated.name}.`);
    setTimeout(() => setSavedFlash(null), 3500);
  }

  return (
    <div style={{ maxWidth: 980 }} data-testid="shops-tab">
      {savedFlash && (
        <div style={{
          padding: "8px 14px", marginBottom: 12, borderRadius: 8,
          background: "rgba(16,185,129,0.12)", border: "1px solid rgba(16,185,129,0.4)",
          color: "var(--green)", fontSize: 13,
        }} data-testid="shops-flash">{savedFlash}</div>
      )}

      <div className="surface" style={{ padding: 16, marginBottom: 14 }}>
        <input className="input" value={query} onChange={e => setQuery(e.target.value)}
          placeholder="Search by shop name, contact, email, phone, address…"
          data-testid="shops-search" />
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          {filtered.length} of {shops.length} shops · click any row to edit details and custom rate card.
        </div>
      </div>

      <div className="surface" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "1.4fr 1.1fr 1.1fr 0.7fr 0.7fr 0.8fr",
          gap: 10, padding: "12px 16px", borderBottom: "1px solid var(--border)",
          fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em",
          color: "var(--text-muted)", fontWeight: 700, background: "var(--bg-elevated)",
        }}>
          <div>Shop</div><div>Contact</div><div>Address</div>
          <div>Zone</div><div>Rate Card</div><div style={{ textAlign: "right" }}>Status</div>
        </div>
        {filtered.length === 0 && (
          <div className="muted" style={{ padding: 24, textAlign: "center" }}>No shops match.</div>
        )}
        {filtered.map(s => (
          <button key={s.id} onClick={() => setEditing(s)}
            data-testid={`shop-row-${s.id}`}
            style={{
              all: "unset", cursor: "pointer", display: "grid",
              gridTemplateColumns: "1.4fr 1.1fr 1.1fr 0.7fr 0.7fr 0.8fr",
              gap: 10, padding: "14px 16px", borderBottom: "1px solid var(--border)",
              alignItems: "center", width: "100%", boxSizing: "border-box",
              fontSize: 13, transition: "background 0.1s",
            }}
            onMouseEnter={e => e.currentTarget.style.background = "var(--bg-elevated)"}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
            <div>
              <div style={{ fontWeight: 700 }}>{s.name}</div>
              {s.legal_name && s.legal_name !== s.name &&
                <div className="muted" style={{ fontSize: 11 }}>{s.legal_name}</div>}
            </div>
            <div>
              <div>{s.contact_name || "—"}</div>
              <div className="muted" style={{ fontSize: 11 }}>{s.contact_email || s.contact_phone || "—"}</div>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>{s.address}</div>
            <div>
              <span className={`badge badge-${s.zone || "west"}`}>{s.zone || "—"}</span>
            </div>
            <div>
              <span className="badge" style={{
                background: s.pricing_tier === "custom" ? "rgba(249,115,22,0.18)" : "rgba(148,163,184,0.18)",
                color: s.pricing_tier === "custom" ? "var(--accent)" : "var(--text-muted)",
                border: `1px solid ${s.pricing_tier === "custom" ? "rgba(249,115,22,0.4)" : "var(--border)"}`,
              }}>{s.pricing_tier === "custom" ? "CUSTOM" : "STANDARD"}</span>
            </div>
            <div style={{ textAlign: "right" }}>
              <StatusBadge status={s.status} />
            </div>
          </button>
        ))}
      </div>

      {editing && (
        <ShopEditModal shop={editing} onClose={() => setEditing(null)} onSaved={onSaved} />
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    active:   { c: "var(--green)",  bg: "rgba(16,185,129,0.18)",   bd: "rgba(16,185,129,0.4)" },
    pending:  { c: "var(--yellow)", bg: "rgba(245,158,11,0.18)",   bd: "rgba(245,158,11,0.4)" },
    paused:   { c: "var(--text-muted)", bg: "rgba(148,163,184,0.18)", bd: "var(--border)" },
    inactive: { c: "var(--red)",    bg: "rgba(239,68,68,0.18)",    bd: "rgba(239,68,68,0.4)" },
  };
  const s = map[status] || map.active;
  return <span className="badge" style={{
    background: s.bg, color: s.c, border: `1px solid ${s.bd}`,
  }} data-testid={`status-${status}`}>{(status || "active").toUpperCase()}</span>;
}

function ShopEditModal({ shop, onClose, onSaved }) {
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!shop) return;
    setForm({
      name: shop.name || "",
      legal_name: shop.legal_name || "",
      contact_name: shop.contact_name || "",
      contact_phone: shop.contact_phone || "",
      contact_email: shop.contact_email || "",
      address: shop.address || "",
      city: shop.city || "",
      state: shop.state || "AZ",
      zip: shop.zip || "",
      pricing_tier: shop.pricing_tier || "standard",
      custom_rate_static:  shop.custom_rate_static  ?? "",
      custom_rate_dynamic: shop.custom_rate_dynamic ?? "",
      custom_rate_dual:    shop.custom_rate_dual    ?? "",
      custom_rate_triple:  shop.custom_rate_triple  ?? "",
      custom_rate_tesla:   shop.custom_rate_tesla   ?? "",
      status: shop.status || "active",
      notes: shop.notes || "",
    });
    setError("");
  }, [shop]);

  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }

  async function save() {
    setBusy(true); setError("");
    try {
      const payload = { ...form };
      // Convert blank strings → null for rate fields so backend doesn't store ""
      for (const k of ["custom_rate_static","custom_rate_dynamic","custom_rate_dual","custom_rate_triple","custom_rate_tesla"]) {
        payload[k] = payload[k] === "" || payload[k] === null ? null : Number(payload[k]);
      }
      if (payload.pricing_tier === "standard") {
        for (const k of ["custom_rate_static","custom_rate_dynamic","custom_rate_dual","custom_rate_triple","custom_rate_tesla"]) {
          payload[k] = null;
        }
      }
      const { data } = await api.put(`/shops/${shop.id}`, payload);
      onSaved?.(data);
    } catch (e) {
      setError(e.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 50,
      display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 16,
      overflowY: "auto",
    }} data-testid="shop-edit-modal">
      <div onClick={e => e.stopPropagation()} className="surface page-fade"
        style={{ padding: 24, maxWidth: 720, width: "100%", margin: "40px 0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 4 }}>
          <h2 className="h2" style={{ margin: 0 }}>Edit Shop</h2>
          <StatusBadge status={form.status} />
        </div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 18 }}>
          {shop.id.slice(0, 8).toUpperCase()} · created via {shop.created_via || "admin"}
        </div>

        <SectionBox title="Business">
          <Grid2>
            <SField label="Display name *">
              <input className="input" value={form.name} onChange={e => set("name", e.target.value)}
                data-testid="se-name" />
            </SField>
            <SField label="Legal name">
              <input className="input" value={form.legal_name} onChange={e => set("legal_name", e.target.value)}
                data-testid="se-legal-name" />
            </SField>
            <SField label="Contact name">
              <input className="input" value={form.contact_name} onChange={e => set("contact_name", e.target.value)}
                data-testid="se-contact-name" />
            </SField>
            <SField label="Status">
              <select className="input" value={form.status} onChange={e => set("status", e.target.value)}
                data-testid="se-status">
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="inactive">Inactive</option>
              </select>
            </SField>
            <SField label="Phone">
              <input className="input" value={form.contact_phone} onChange={e => set("contact_phone", e.target.value)}
                data-testid="se-phone" />
            </SField>
            <SField label="Email">
              <input className="input" type="email" value={form.contact_email}
                onChange={e => set("contact_email", e.target.value)} data-testid="se-email" />
            </SField>
          </Grid2>
        </SectionBox>

        <SectionBox title="Location">
          <SField label="Address (changing this re-geocodes + reassigns zone)">
            <input className="input" value={form.address} onChange={e => set("address", e.target.value)}
              data-testid="se-address" />
          </SField>
          <Grid3>
            <SField label="City"><input className="input" value={form.city}
              onChange={e => set("city", e.target.value)} data-testid="se-city" /></SField>
            <SField label="State"><input className="input" value={form.state}
              onChange={e => set("state", e.target.value)} data-testid="se-state" /></SField>
            <SField label="ZIP"><input className="input" value={form.zip}
              onChange={e => set("zip", e.target.value)} data-testid="se-zip" /></SField>
          </Grid3>
        </SectionBox>

        <SectionBox title="Rate Card">
          <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
            <button type="button"
              className={"btn " + (form.pricing_tier === "standard" ? "btn-primary" : "btn-ghost")}
              onClick={() => set("pricing_tier", "standard")} data-testid="se-tier-standard">
              Standard Pricing
            </button>
            <button type="button"
              className={"btn " + (form.pricing_tier === "custom" ? "btn-primary" : "btn-ghost")}
              onClick={() => set("pricing_tier", "custom")} data-testid="se-tier-custom">
              Negotiated (Custom)
            </button>
          </div>
          {form.pricing_tier === "custom" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {CAL_TYPES.map(t => (
                <div key={t.k} style={{
                  display: "grid", gridTemplateColumns: "1.4fr 0.9fr 0.9fr",
                  gap: 12, alignItems: "center",
                }}>
                  <div style={{ fontSize: 14 }}>{t.l}</div>
                  <div className="muted font-mono" style={{ fontSize: 12 }}>
                    standard ${STANDARD_PRICES[t.k]}
                  </div>
                  <div style={{ position: "relative" }}>
                    <span style={{ position: "absolute", left: 10, top: 9, color: "var(--text-muted)" }}>$</span>
                    <input className="input" type="number" step="0.01" min="0"
                      style={{ paddingLeft: 22 }}
                      value={form[`custom_rate_${t.k}`]}
                      onChange={e => set(`custom_rate_${t.k}`, e.target.value)}
                      placeholder={String(STANDARD_PRICES[t.k])}
                      data-testid={`se-rate-${t.k}`} />
                  </div>
                </div>
              ))}
              <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                Leave a row blank to fall back to standard pricing for that calibration type.
              </div>
            </div>
          ) : (
            <div className="muted" style={{ fontSize: 13 }}>
              This shop is billed at the standard rate card.
            </div>
          )}
        </SectionBox>

        <SectionBox title="Notes">
          <textarea className="input" value={form.notes} rows={3}
            onChange={e => set("notes", e.target.value)} data-testid="se-notes"
            placeholder="Internal notes (not visible to the shop)" />
        </SectionBox>

        {error && (
          <div style={{ color: "var(--red)", fontSize: 13, marginTop: 10 }} data-testid="shop-edit-error">{error}</div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <button className="btn btn-ghost" onClick={onClose} data-testid="se-cancel">Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={busy} data-testid="se-save">
            {busy ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

const SectionBox = ({ title, children }) => (
  <div style={{ marginBottom: 18 }}>
    <div className="muted" style={{
      fontSize: 11, fontWeight: 700, textTransform: "uppercase",
      letterSpacing: "0.12em", marginBottom: 8,
    }}>{title}</div>
    <div className="elevated" style={{ padding: 14 }}>{children}</div>
  </div>
);
const Grid2 = ({ children }) => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>
);
const Grid3 = ({ children }) => (
  <div style={{ display: "grid", gridTemplateColumns: "2fr 0.8fr 0.8fr", gap: 12 }}>{children}</div>
);
const SField = ({ label, children }) => (
  <div><div className="label" style={{ marginBottom: 4 }}>{label}</div>{children}</div>
);


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
