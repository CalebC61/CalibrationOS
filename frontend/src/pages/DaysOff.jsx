import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatDate, formatTime } from "../lib/api";
import Shell from "../components/Shell";

function prettyDay(iso) {
  if (!iso) return "";
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12)).toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
}

export default function DaysOff() {
  const [days, setDays] = useState([]);
  const [conflicts, setConflicts] = useState([]);
  const [error, setError] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [label, setLabel] = useState("Vacation");
  const [busy, setBusy] = useState(false);

  async function load() {
    const { data } = await api.get("/days-off");
    setDays(data.days || []);
    setConflicts(data.conflicts || []);
  }

  useEffect(() => {
    load().catch(() => setError("Couldn't load days off. Try again."));
  }, []);

  async function toggle(row) {
    setError("");
    try {
      await api.put(`/days-off/${row.key}`, { blocked: !row.blocked });
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't update that day.");
    }
  }

  async function addRange(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/days-off", { start, end: end || start, label: label || "Vacation" });
      setStart("");
      setEnd("");
      setLabel("Vacation");
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't add those dates.");
    } finally {
      setBusy(false);
    }
  }

  async function removeCustom(row) {
    setError("");
    try {
      await api.delete(`/days-off/${row.key}`);
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't remove that range.");
    }
  }

  const holidays = days.filter(row => row.kind === "holiday");
  const custom = days.filter(row => row.kind !== "holiday");

  return (
    <Shell>
      <div style={{ maxWidth: 720 }}>
        <h1 className="h1" style={{ marginBottom: 8 }}>Days off</h1>
        <p className="muted" style={{ marginTop: 0, marginBottom: 20, maxWidth: "62ch" }}>
          Shops cannot book a closed day. A job already on the board stays there.
          It is listed below so you can move it. Nothing is cancelled for you.
        </p>
        {error && (
          <div role="alert" style={{ color: "var(--red)", marginBottom: 16 }} data-testid="days-off-error">{error}</div>
        )}

        <section className="surface" style={{ padding: 24, marginBottom: 20 }}>
          <h2 className="h2" style={{ marginBottom: 4 }}>Holidays</h2>
          <p className="muted" style={{ marginTop: 0, marginBottom: 8 }}>
            These start closed. Open a day if you are working it.
          </p>
          {holidays.length === 0 && <div className="muted">Loading the holiday list…</div>}
          {holidays.map(row => (
            <div key={row.key} data-testid={`holiday-${row.key}`} style={{
              display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap",
              alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--border)",
            }}>
              <div>
                <div style={{ fontWeight: 600 }}>{row.label}</div>
                <div className="muted" style={{ fontSize: 13 }}>{prettyDay(row.start)}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ color: row.blocked ? "var(--red)" : "var(--green)", fontWeight: 600 }}>
                  {row.blocked ? "Closed" : "Open"}
                </span>
                <button type="button" className="btn btn-ghost" onClick={() => toggle(row)}
                  data-testid={`toggle-${row.key}`}>
                  {row.blocked ? "Open this day" : "Close this day"}
                </button>
              </div>
            </div>
          ))}
        </section>

        <section className="surface" style={{ padding: 24, marginBottom: 20 }}>
          <h2 className="h2" style={{ marginBottom: 12 }}>Add dates</h2>
          <form onSubmit={addRange}>
            <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
              <label>
                <span className="label">First day</span>
                <input className="input" type="date" required value={start}
                  onChange={e => setStart(e.target.value)} data-testid="day-off-start" />
              </label>
              <label>
                <span className="label">Last day</span>
                <input className="input" type="date" value={end} min={start || undefined}
                  onChange={e => setEnd(e.target.value)} data-testid="day-off-end" />
              </label>
              <label>
                <span className="label">What to call it</span>
                <input className="input" value={label} onChange={e => setLabel(e.target.value)}
                  data-testid="day-off-label" />
              </label>
            </div>
            <button className="btn btn-primary" type="submit" disabled={busy || !start}
              style={{ marginTop: 16 }} data-testid="day-off-add">
              {busy ? "Adding…" : "Add these dates"}
            </button>
          </form>
          {custom.length > 0 && (
            <div style={{ marginTop: 16 }}>
              {custom.map(row => (
                <div key={row.key} data-testid={`custom-${row.key}`} style={{
                  display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap",
                  alignItems: "center", padding: "12px 0", borderTop: "1px solid var(--border)",
                }}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{row.label}</div>
                    <div className="muted" style={{ fontSize: 13 }}>
                      {prettyDay(row.start)}{row.end && row.end !== row.start ? ` – ${prettyDay(row.end)}` : ""}
                      {" · "}{row.blocked ? "Closed" : "Open"}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="button" className="btn btn-ghost" onClick={() => toggle(row)}>
                      {row.blocked ? "Open" : "Close"}
                    </button>
                    <button type="button" className="btn btn-ghost" onClick={() => removeCustom(row)}
                      data-testid={`remove-${row.key}`}>
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="surface" style={{ padding: 24, marginBottom: 20 }} data-testid="day-off-conflicts">
          <h2 className="h2" style={{ marginBottom: 4 }}>Jobs already on a closed day</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            These were not cancelled. Move them from dispatch when you can.
          </p>
          {conflicts.length === 0 && <div className="muted">None right now.</div>}
          {conflicts.map(job => (
            <div key={job.id} style={{ padding: "12px 0", borderTop: "1px solid var(--border)" }}
              data-testid={`conflict-${job.id}`}>
              <div style={{ fontWeight: 600 }}>{job.shop_name || "Shop"} · {job.label}</div>
              <div className="muted" style={{ fontSize: 13 }}>
                {job.when ? `${formatDate(job.when)} · ${formatTime(job.when)}` : "Time not set"}
                {job.vehicle ? ` · ${job.vehicle}` : ""}
              </div>
              {job.address && <div style={{ fontSize: 14, marginTop: 4 }}>{job.address}</div>}
            </div>
          ))}
        </section>

        <p style={{ marginTop: 8 }}>
          <Link to="/map-pins" data-testid="map-pins-link">Addresses saved with a guessed pin</Link>
        </p>
      </div>
    </Shell>
  );
}
