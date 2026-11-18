import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, formatDate, formatTime } from "../lib/api";
import Shell from "../components/Shell";

export default function ShopDetail() {
  const { id } = useParams();
  const [shop, setShop] = useState(null);
  const [edit, setEdit] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let gone = false;
    api.get(`/shops/${id}`).then(({ data }) => {
      if (!gone) { setShop(data); setEdit(data); }
    });
    return () => { gone = true; };
  }, [id]);

  async function save() {
    setSaving(true);
    try {
      const { data } = await api.put(`/shops/${id}`, {
        name: edit.name,
        contact_name: edit.contact_name || null,
        contact_phone: edit.contact_phone || null,
        contact_email: edit.contact_email || null,
        address: edit.address,
        pricing_tier: edit.pricing_tier || "standard",
        status: edit.status,
        notes: edit.notes || null,
        xero_contact_id: (edit.xero_contact_id || "").trim() || null,
        wholesale_schedule: edit.wholesale_schedule || "auto",
      });
      setShop(data); setEdit(data);
      alert("Saved");
    } catch (e) {
      const detail = e.response?.data?.detail;
      alert(typeof detail === "string" ? detail : "Could not save this shop. Try again.");
    } finally { setSaving(false); }
  }

  if (!shop) return <Shell><div className="muted">Loading…</div></Shell>;

  const card = shop.card_on_file || { state: "None", charge_terms_accepted: false, can_book: false };
  const jobGroups = {
    upcoming: Array.isArray(shop.jobs?.upcoming) ? shop.jobs.upcoming : [],
    recent: Array.isArray(shop.jobs?.recent) ? shop.jobs.recent : [],
  };

  return (
    <Shell>
      <div style={{ maxWidth: 820 }}>
        <h1 className="h1" style={{ marginBottom: 6 }}>{shop.name}</h1>
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          <span className={`badge badge-${shop.zone}`}>{shop.zone === "west" ? "West Valley" : "East Valley"}</span>
          <span className="badge badge-booked" style={{ textTransform: "capitalize" }}>{shop.status}</span>
        </div>

        <div className="surface" style={{ padding: 20, marginBottom: 16 }} data-testid="shop-billing">
          <div className="h3" style={{ marginBottom: 8 }}>Card on file</div>
          <p style={{ margin: "0 0 6px", fontSize: 15 }} data-testid="shop-card-summary">{cardLine(card)}</p>
          <p style={{ margin: "0 0 6px", fontSize: 14 }} data-testid="shop-card-state">{card.state || "None"}</p>
          <p style={{ margin: "0 0 6px", fontSize: 14 }} data-testid="shop-card-terms">
            {card.charge_terms_accepted ? "Charge terms accepted" : "Charge terms not accepted"}
          </p>
          <p style={{ margin: "0 0 14px", fontSize: 14 }} data-testid="shop-can-book">
            {card.can_book ? "This shop can book right now." : (card.book_block || "This shop cannot book right now.")}
          </p>
          <p className="muted" style={{ fontSize: 14, marginTop: 0, marginBottom: 14 }}>
            This shop books from the shop portal after they log in. There is no public booking link.
          </p>
          <Link to={`/shops/${shop.id}/book`} className="btn btn-primary" data-testid="book-job">Book a job</Link>
        </div>

        <div className="surface" style={{ overflow: "hidden", marginBottom: 16 }} data-testid="shop-jobs">
          <JobGroup title="Upcoming" jobs={jobGroups.upcoming} empty="No upcoming jobs." testId="shop-jobs-upcoming" />
          <JobGroup title="Recent" jobs={jobGroups.recent} empty="No recent jobs." testId="shop-jobs-recent" />
        </div>

        <div className="surface" style={{ padding: 20 }}>
          <div className="h3" style={{ marginBottom: 12 }}>Details</div>
          <Row>
            <Field label="Name"><input className="input" value={edit.name || ""} onChange={e => setEdit({...edit, name: e.target.value})} /></Field>
            <Field label="Status">
              <select className="input" value={edit.status} onChange={e => setEdit({...edit, status: e.target.value})}>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="inactive">Inactive</option>
                <option value="suspended">Suspended</option>
              </select>
            </Field>
          </Row>
          <Row>
            <Field label="Contact name"><input className="input" value={edit.contact_name || ""} onChange={e => setEdit({...edit, contact_name: e.target.value})} /></Field>
            <Field label="Contact phone"><input className="input" value={edit.contact_phone || ""} onChange={e => setEdit({...edit, contact_phone: e.target.value})} /></Field>
          </Row>
          <Field label="Address"><input className="input" value={edit.address || ""} onChange={e => setEdit({...edit, address: e.target.value})} data-testid="shop-address" /></Field>
          <div className="muted" style={{ fontSize: 13, marginTop: -8, marginBottom: 14 }}>
            A new address updates this shop’s map pin. Nothing is sent to the shop.
          </div>
          <Field label="Contact email"><input className="input" value={edit.contact_email || ""} onChange={e => setEdit({...edit, contact_email: e.target.value})} /></Field>
          <Field label="Xero contact ID">
            <input className="input" value={edit.xero_contact_id || ""} data-testid="shop-xero-contact"
              onChange={e => setEdit({...edit, xero_contact_id: e.target.value})} />
          </Field>
          <div className="muted" style={{ fontSize: 13, marginTop: -8, marginBottom: 14 }}>
            Paste the contact’s ID from Xero. If this is blank, completion matches the shop by name and saves the ID. A contact is never created.
          </div>
          <Field label="Wholesale card">
            <select className="input" value={edit.wholesale_schedule || "auto"} data-testid="shop-wholesale-schedule"
              onChange={e => setEdit({...edit, wholesale_schedule: e.target.value})}>
              <option value="auto">Match the shop name</option>
              <option value="standard">Standard</option>
              <option value="realfast">Real Fast</option>
              <option value="preferred">Preferred</option>
              <option value="custom">This shop’s custom rates</option>
            </select>
          </Field>
          {shop.rate_label && (
            <div className="muted" style={{ fontSize: 14, marginTop: -8, marginBottom: 14 }} data-testid="shop-rate-label">
              Billed on {shop.rate_label}.
            </div>
          )}
          <button className="btn btn-primary" disabled={saving} onClick={save} data-testid="save-shop">{saving ? "Saving…" : "Save Changes"}</button>
        </div>
      </div>
    </Shell>
  );
}

function cardLine(card) {
  if (!card || card.state === "None") return "No card on file";
  const raw = String(card.brand || "").trim();
  const brand = raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : "Card";
  const last4 = card.last4 ? ` ending ${card.last4}` : "";
  let exp = "";
  if (card.exp_month && card.exp_year) {
    const word = card.state === "Expired" ? "expired" : "expires";
    exp = `, ${word} ${card.exp_month}/${card.exp_year}`;
  }
  return `${brand}${last4}${exp}`;
}

function jobMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  if (Number.isNaN(amount)) return "—";
  return `$${amount.toFixed(2)}`;
}

function jobHref(job) {
  const params = new URLSearchParams();
  if (job.board_date) params.set("date", job.board_date);
  if (job.id) params.set("job", job.id);
  const query = params.toString();
  return query ? `/dashboard?${query}` : "/dashboard";
}

function JobGroup({ title, jobs, empty, testId }) {
  return (
    <div data-testid={testId}>
      <div className="h3" style={{ padding: "16px 16px 8px" }}>{title}</div>
      {jobs.length === 0 && (
        <div className="muted" style={{ fontSize: 14, padding: "0 16px 16px" }}>{empty}</div>
      )}
      {jobs.map(job => (
        <Link key={job.id} to={jobHref(job)} data-testid={`shop-job-${job.id}`}
          style={{ display: "block", padding: "12px 16px", borderTop: "1px solid var(--border)", color: "inherit", textDecoration: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontWeight: 600 }}>{job.vehicle || "Vehicle not listed"}</div>
              <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
                {formatDate(job.scheduled_start)} · {formatTime(job.scheduled_start)}
                {job.calibration_label ? ` · ${job.calibration_label}` : ""}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 14 }}>{job.status_label || job.status}</div>
              <div className="font-mono" style={{ fontSize: 13, marginTop: 4 }}>{jobMoney(job.price)}</div>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}

const Row = ({ children }) => <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>{children}</div>;
const Field = ({ label, children }) => (
  <div style={{ marginBottom: 14 }}><label className="label">{label}</label>{children}</div>
);
