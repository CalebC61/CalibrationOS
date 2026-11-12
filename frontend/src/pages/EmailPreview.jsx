import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Shell from "../components/Shell";

function phoenixStamp(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-US", {
    timeZone: "America/Phoenix",
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function EmailPreview() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState("");

  useEffect(() => {
    api.get("/email-outbox")
      .then(response => setRows(response.data || []))
      .catch(() => setError("Couldn't load the email preview."));
  }, []);

  return (
    <Shell>
      <div style={{ maxWidth: 760 }}>
        <h1 className="h1" style={{ marginBottom: 8 }}>Email preview</h1>
        <p className="muted" style={{ marginTop: 0, marginBottom: 20, maxWidth: "62ch" }}>
          These messages were not sent. Shop and customer mail stays here while
          shop emails are off for testing. Nothing on this page sends mail.
        </p>
        {error && <div role="alert" style={{ color: "var(--red)", marginBottom: 16 }}>{error}</div>}
        {rows.length === 0 && !error && (
          <div className="surface" style={{ padding: 24 }} data-testid="email-preview-empty">
            No held emails yet.
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {rows.map(row => {
            const open = openId === row.id;
            return (
              <article key={row.id} className="surface" style={{ padding: 16 }} data-testid={`email-preview-${row.id}`}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{row.subject}</div>
                    <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                      To {row.to} · {phoenixStamp(row.created_at)} Phoenix
                    </div>
                  </div>
                  <button type="button" className="btn btn-ghost" onClick={() => setOpenId(open ? "" : row.id)}
                    data-testid={`email-preview-toggle-${row.id}`}>
                    {open ? "Hide" : "Read"}
                  </button>
                </div>
                {open && (
                  <div style={{ marginTop: 12, fontSize: 14 }} data-testid={`email-preview-body-${row.id}`}
                    dangerouslySetInnerHTML={{ __html: row.body || "" }} />
                )}
              </article>
            );
          })}
        </div>
      </div>
    </Shell>
  );
}
