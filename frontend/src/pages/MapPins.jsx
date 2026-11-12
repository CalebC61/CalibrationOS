import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatDate, formatTime } from "../lib/api";
import Shell from "../components/Shell";

export default function MapPins() {
  const [shops, setShops] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  async function load() {
    const { data } = await api.get("/address-pins");
    setShops(data.shops || []);
    setJobs(data.jobs || []);
  }

  useEffect(() => {
    load().catch(() => setError("Couldn't load the address list."));
  }, []);

  async function recheck(kind, id) {
    setBusyId(id);
    setError("");
    setNotice("");
    try {
      const { data } = await api.post("/address-pins/recheck", { kind, id });
      setNotice(data.formatted_address
        ? `Updated to ${data.formatted_address}.`
        : "That address has a real pin now.");
      await load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "We couldn't find that address, please check it");
    } finally {
      setBusyId("");
    }
  }

  const empty = shops.length === 0 && jobs.length === 0;

  return (
    <Shell>
      <div style={{ maxWidth: 720 }}>
        <h1 className="h1" style={{ marginBottom: 8 }}>Addresses to check</h1>
        <p className="muted" style={{ marginTop: 0, marginBottom: 20, maxWidth: "62ch" }}>
          These shops and jobs were saved with a guessed map pin. New bookings will not
          keep a guess. Look the address up again, or open the shop and correct it.
        </p>
        <p style={{ marginTop: 0 }}>
          <Link to="/days-off">Back to days off</Link>
        </p>
        {error && <div role="alert" style={{ color: "var(--red)", marginBottom: 16 }} data-testid="pins-error">{error}</div>}
        {notice && <div style={{ marginBottom: 16 }} data-testid="pins-notice">{notice}</div>}

        {empty && !error && (
          <div className="surface" style={{ padding: 24 }} data-testid="pins-empty">
            Every saved address has a real map pin.
          </div>
        )}

        {shops.length > 0 && (
          <section className="surface" style={{ padding: 24, marginBottom: 20 }}>
            <h2 className="h2" style={{ marginBottom: 8 }}>Shops</h2>
            {shops.map(shop => (
              <div key={shop.id} data-testid={`pin-shop-${shop.id}`} style={{
                padding: "12px 0", borderTop: "1px solid var(--border)",
                display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap",
              }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{shop.name}</div>
                  <div style={{ fontSize: 14 }}>{shop.address}</div>
                  <Link to={`/shops/${shop.id}`}>Open shop</Link>
                </div>
                <button type="button" className="btn btn-primary" disabled={busyId === shop.id}
                  onClick={() => recheck("shop", shop.id)} data-testid={`recheck-shop-${shop.id}`}>
                  {busyId === shop.id ? "Looking up…" : "Look up again"}
                </button>
              </div>
            ))}
          </section>
        )}

        {jobs.length > 0 && (
          <section className="surface" style={{ padding: 24 }}>
            <h2 className="h2" style={{ marginBottom: 8 }}>Jobs</h2>
            {jobs.map(job => (
              <div key={job.id} data-testid={`pin-job-${job.id}`} style={{
                padding: "12px 0", borderTop: "1px solid var(--border)",
                display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap",
              }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{job.shop_name || "Job"}</div>
                  <div className="muted" style={{ fontSize: 13 }}>
                    {job.when ? `${formatDate(job.when)} · ${formatTime(job.when)}` : ""}
                    {job.vehicle ? ` · ${job.vehicle}` : ""}
                  </div>
                  <div style={{ fontSize: 14 }}>{job.address}</div>
                </div>
                <button type="button" className="btn btn-primary" disabled={busyId === job.id}
                  onClick={() => recheck("job", job.id)} data-testid={`recheck-job-${job.id}`}>
                  {busyId === job.id ? "Looking up…" : "Look up again"}
                </button>
              </div>
            ))}
          </section>
        )}
      </div>
    </Shell>
  );
}
