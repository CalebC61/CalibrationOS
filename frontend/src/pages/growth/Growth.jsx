import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Shell from "@/components/Shell";

const CIRCLE_LABELS = { top5: "Top 5", key50: "Key 50", vital100: "Vital 100", prospect: "Prospect" };
const CIRCLE_ORDER = ["top5", "key50", "vital100", "prospect"];
const CHANNEL_LABEL = {
  sms: "SMS", email: "Email", linkedin_dm: "LinkedIn", call: "Call",
  in_person: "In Person", video_reel: "Reel",
};

export default function Growth() {
  const enabled = process.env.REACT_APP_GROWTH_MODULE_ENABLED === 'true';
  if (!enabled) {
    return (<div className="min-h-screen bg-[#2A2E37] text-[#E8E8E8] flex items-center justify-center p-8" style={{ fontFamily: 'DM Sans, sans-serif' }}>
      <div className="max-w-xl text-center border border-[#404653] rounded-2xl p-10 bg-[#343843]">
        <h1 style={{ fontFamily: 'Saira Stencil One, sans-serif' }} className="text-4xl text-[#FF7E1E] mb-2 tracking-wider">CALIBRATION<span className="bg-[#FF5F1F] text-[#0a0a0a] px-2 ml-2 rounded">OS</span></h1>
        <div style={{ fontFamily: 'Saira Stencil One, sans-serif' }} className="text-2xl mb-4">PARTNER GROWTH ENGINE</div>
        <p className="text-[#9AA0A6]">Power Connector 5+50+100<br />Module 9 – feature-flagged OFF</p>
        <div className="mt-6 text-left bg-[#2A2E37] rounded-xl p-4 text-sm" style={{ fontFamily: 'JetBrains Mono, monospace' }}>
          Top 5 → daily<br />Key 50 → weekly<br />Vital 100 → monthly<br /><br />
          <span className="text-[#FF7E1E]">favors_given ≥ 2 before ask</span>
        </div>
        <p className="text-xs text-[#6B7280] mt-4">GROWTH_MODULE_ENABLED=false · see docs/module9/README.md</p>
      </div>
    </div>);
  }
  return <GrowthEnabled />;
}

function GrowthEnabled() {
  const [grid, setGrid] = useState(null);
  const [nudges, setNudges] = useState([]);
  const [intros, setIntros] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [showAddContact, setShowAddContact] = useState(false);
  const [form, setForm] = useState({ first_name: "", last_name: "", company_name: "", circle: "prospect", phone: "", email: "" });
  const [introForm, setIntroForm] = useState({ a_contact_id: "", b_contact_id: "", value_prop_a: "", value_prop_b: "" });

  async function loadAll() {
    const [g, n, i] = await Promise.all([
      api.get("/growth/grid"), api.get("/growth/nudges/today"), api.get("/growth/intros"),
    ]);
    setGrid(g.data); setNudges(n.data); setIntros(i.data.slice(0, 20));
    setLoading(false);
  }
  useEffect(() => { loadAll(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const allContacts = grid ? CIRCLE_ORDER.flatMap(c => grid.circles[c] || []) : [];
  const contactById = Object.fromEntries(allContacts.map(c => [c.id, c]));

  function fail(e, fallback) {
    setError(e?.response?.data?.detail || fallback);
  }

  async function addContact(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.post("/growth/contacts", form);
      setForm({ first_name: "", last_name: "", company_name: "", circle: "prospect", phone: "", email: "" });
      setShowAddContact(false);
      await loadAll();
    } catch (err) { fail(err, "Could not add contact."); }
    finally { setBusy(false); }
  }

  async function moveCircle(contact, circle) {
    setError(null);
    try { await api.patch(`/growth/contacts/${contact.id}`, { circle }); await loadAll(); }
    catch (err) { fail(err, "Could not move contact — the target circle may be full."); }
  }

  async function approveTouch(id) {
    try { await api.post(`/growth/touches/${id}/approve`); await loadAll(); }
    catch (err) { fail(err, "Could not approve touch."); }
  }
  async function sendTouch(id) {
    try { await api.post(`/growth/touches/${id}/send`); await loadAll(); }
    catch (err) { fail(err, "Could not send touch."); }
  }
  async function approveIntro(id) {
    try { await api.post(`/growth/intros/${id}/approve`); await loadAll(); }
    catch (err) { fail(err, "Could not approve intro."); }
  }
  async function sendIntro(id) {
    try { await api.post(`/growth/intros/${id}/send`); await loadAll(); }
    catch (err) { fail(err, "Could not send intro — both contacts need an email on file."); }
  }

  async function createIntro(e) {
    e.preventDefault();
    if (!introForm.a_contact_id || !introForm.b_contact_id || introForm.a_contact_id === introForm.b_contact_id) {
      setError("Pick two different contacts for an introduction.");
      return;
    }
    setBusy(true); setError(null);
    try {
      await api.post("/growth/intros", introForm);
      setIntroForm({ a_contact_id: "", b_contact_id: "", value_prop_a: "", value_prop_b: "" });
      await loadAll();
    } catch (err) { fail(err, "Could not create intro."); }
    finally { setBusy(false); }
  }

  if (loading) {
    return (<Shell><h1 className="h1" style={{ marginBottom: 8 }}>Partner Growth</h1><div className="muted">Loading…</div></Shell>);
  }

  return (
    <Shell>
      <h1 className="h1" style={{ marginBottom: 8 }}>Partner Growth</h1>
      <div className="muted" style={{ marginBottom: 20, fontSize: 14 }}>
        Power Connector 5+50+100 — Top 5 daily, Key 50 weekly, Vital 100 monthly. Give two favors before asking.
      </div>
      {error && (
        <div style={{
          padding: "10px 12px", borderRadius: 8, marginBottom: 14, fontSize: 13,
          background: "rgba(239,68,68,0.12)", color: "var(--red)",
        }} data-testid="growth-error">{error}</div>
      )}

      {/* Today's Nudges */}
      <section className="surface" style={{ padding: 18, marginBottom: 20 }} data-testid="growth-nudges">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div className="h3">Today's Nudges</div>
          <div className="muted" style={{ fontSize: 13 }}>{nudges.length} due</div>
        </div>
        {nudges.length === 0 && <div className="muted" style={{ fontSize: 14 }}>Nothing due today.</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {nudges.map(t => (
            <div key={t.id} className="elevated" style={{ padding: 12 }} data-testid={`nudge-${t.id}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>
                  {t.contact ? `${t.contact.first_name} ${t.contact.last_name}` : "Unknown contact"}
                  <span className="muted" style={{ fontWeight: 400 }}> · {t.contact?.company_name}</span>
                </div>
                <span className="badge badge-booked">{CHANNEL_LABEL[t.channel] || t.channel}</span>
              </div>
              <div style={{ marginTop: 6, fontSize: 13, whiteSpace: "pre-wrap" }}>{t.body}</div>
              <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                {t.status === "draft" && <button className="btn btn-primary" onClick={() => approveTouch(t.id)} data-testid={`nudge-approve-${t.id}`}>Approve</button>}
                {t.status === "approved" && <button className="btn btn-primary" onClick={() => sendTouch(t.id)} data-testid={`nudge-send-${t.id}`}>Send</button>}
                {t.status === "sent" && <span className="badge badge-complete">Sent</span>}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Grid */}
      <section style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div className="h3">Contacts</div>
          <button className="btn btn-ghost" onClick={() => setShowAddContact(s => !s)} data-testid="growth-add-contact-toggle">
            {showAddContact ? "Cancel" : "+ Add Contact"}
          </button>
        </div>
        {showAddContact && (
          <form onSubmit={addContact} className="surface" style={{
            padding: 14, marginBottom: 14, display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10,
          }} data-testid="growth-add-contact-form">
            <input className="input" placeholder="First name" required
              value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} />
            <input className="input" placeholder="Last name" required
              value={form.last_name} onChange={e => setForm({ ...form, last_name: e.target.value })} />
            <input className="input" placeholder="Company" required
              value={form.company_name} onChange={e => setForm({ ...form, company_name: e.target.value })} />
            <select className="input" value={form.circle} onChange={e => setForm({ ...form, circle: e.target.value })}>
              {CIRCLE_ORDER.map(c => <option key={c} value={c}>{CIRCLE_LABELS[c]}</option>)}
            </select>
            <input className="input" placeholder="Phone" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} />
            <input className="input" placeholder="Email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
            <button className="btn btn-primary" type="submit" disabled={busy} style={{ gridColumn: "1 / -1" }}>
              {busy ? "Saving…" : "Save Contact"}
            </button>
          </form>
        )}

        {CIRCLE_ORDER.map(circle => {
          const contacts = grid.circles[circle] || [];
          const cap = grid.caps[circle];
          return (
            <div key={circle} className="surface" style={{ padding: 16, marginBottom: 12 }} data-testid={`growth-circle-${circle}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{CIRCLE_LABELS[circle]}</div>
                <div className="muted" style={{ fontSize: 13 }}>{contacts.length}{cap < 9999 ? `/${cap}` : ""}</div>
              </div>
              {contacts.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No contacts yet.</div>}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {contacts.map(c => (
                  <div key={c.id} data-testid={`contact-${c.id}`} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "8px 10px", borderRadius: 8, background: "var(--bg-elevated)",
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{c.first_name} {c.last_name}</div>
                      <div className="muted" style={{ fontSize: 12 }}>{c.company_name} · favors {c.favors_given}g/{c.favors_asked}a</div>
                    </div>
                    <select className="input" style={{ width: 130 }} value={c.circle}
                      onChange={e => moveCircle(c, e.target.value)} data-testid={`contact-circle-${c.id}`}>
                      {CIRCLE_ORDER.map(opt => <option key={opt} value={opt}>{CIRCLE_LABELS[opt]}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </section>

      {/* Intros */}
      <section className="surface" style={{ padding: 18 }} data-testid="growth-intros">
        <div className="h3" style={{ marginBottom: 12 }}>3-D Introductions</div>
        <form onSubmit={createIntro} style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10, marginBottom: 14,
        }}>
          <select className="input" value={introForm.a_contact_id} onChange={e => setIntroForm({ ...introForm, a_contact_id: e.target.value })}>
            <option value="">Contact A…</option>
            {allContacts.map(c => <option key={c.id} value={c.id}>{c.first_name} {c.last_name} — {c.company_name}</option>)}
          </select>
          <select className="input" value={introForm.b_contact_id} onChange={e => setIntroForm({ ...introForm, b_contact_id: e.target.value })}>
            <option value="">Contact B…</option>
            {allContacts.map(c => <option key={c.id} value={c.id}>{c.first_name} {c.last_name} — {c.company_name}</option>)}
          </select>
          <input className="input" placeholder="Value to A" value={introForm.value_prop_a} onChange={e => setIntroForm({ ...introForm, value_prop_a: e.target.value })} />
          <input className="input" placeholder="Value to B" value={introForm.value_prop_b} onChange={e => setIntroForm({ ...introForm, value_prop_b: e.target.value })} />
          <button className="btn btn-primary" type="submit" disabled={busy}>Draft Intro</button>
        </form>
        {intros.length === 0 && <div className="muted" style={{ fontSize: 14 }}>No introductions yet.</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {intros.map(i => {
            const a = contactById[i.a_contact_id]; const b = contactById[i.b_contact_id];
            return (
              <div key={i.id} className="elevated" style={{ padding: 12 }} data-testid={`intro-${i.id}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>
                    {a ? `${a.first_name} ${a.last_name}` : "?"} ↔ {b ? `${b.first_name} ${b.last_name}` : "?"}
                  </div>
                  <span className={`badge badge-${i.status === "sent" ? "complete" : "draft"}`}>{i.status}</span>
                </div>
                <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                  {(i.status === "draft" || i.status === "pending_approval") &&
                    <button className="btn btn-primary" onClick={() => approveIntro(i.id)}>Approve</button>}
                  {i.status === "approved" &&
                    <button className="btn btn-primary" onClick={() => sendIntro(i.id)}>Send</button>}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </Shell>
  );
}
