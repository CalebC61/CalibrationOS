import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

// Module 8 — Admin Assist Engine. Floating copilot widget, mounted in Shell so it's on every
// owner page. Self-guards: hidden entirely when the backend reports the module disabled
// (no GOOGLE_API_KEY) or when REACT_APP_ASSIST_MODULE_ENABLED is explicitly 'false'.

const SUGGESTIONS = [
  "What's on the board today?",
  "Any at-risk jobs right now?",
  "Who's due for a growth touch today?",
];

export default function Assist() {
  const flagOff = process.env.REACT_APP_ASSIST_MODULE_ENABLED === "false";
  const [enabled, setEnabled] = useState(false);
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);   // {role, text, pending?}
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (flagOff) return;
    api.get("/integrations/status")
      .then(r => setEnabled(Boolean(r.data?.assist?.enabled)))
      .catch(() => setEnabled(false));
  }, [flagOff]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, open]);

  if (flagOff || !enabled) return null;

  function push(msg) { setMessages(m => [...m, msg]); }

  function settlePending(pendingId, status) {
    setMessages(m => m.map(msg =>
      msg.pending?.id === pendingId ? { ...msg, pending: { ...msg.pending, status } } : msg));
  }

  async function send(text) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    push({ role: "user", text: message });
    setBusy(true);
    try {
      const { data } = await api.post("/assist/message", { message, conversation_id: conversationId });
      setConversationId(data.conversation_id);
      if (data.kind === "pending_action") {
        push({ role: "assistant", text: data.text, pending: data.pending_action });
      } else {
        push({ role: "assistant", text: data.text });
      }
    } catch (e) {
      push({ role: "assistant", error: true,
             text: e.response?.data?.detail || "Something went wrong — try again." });
    } finally { setBusy(false); }
  }

  async function confirmAction(pending) {
    setBusy(true);
    try {
      const { data } = await api.post(`/assist/actions/${pending.id}/confirm`);
      settlePending(pending.id, "executed");
      push({ role: "assistant", text: data.text });
    } catch (e) {
      settlePending(pending.id, "failed");
      push({ role: "assistant", error: true,
             text: e.response?.data?.detail || "Couldn't run that action." });
    } finally { setBusy(false); }
  }

  async function cancelAction(pending) {
    try {
      await api.post(`/assist/actions/${pending.id}/cancel`);
      settlePending(pending.id, "cancelled");
    } catch {
      settlePending(pending.id, "failed");
    }
  }

  return (
    <>
      {/* launcher */}
      {!open && (
        <button onClick={() => setOpen(true)} data-testid="assist-launcher" style={{
          position: "fixed", right: 20, bottom: 20, zIndex: 50,
          width: 52, height: 52, borderRadius: 26, border: "1px solid var(--border)",
          background: "var(--accent)", color: "#0a0a0a", fontWeight: 800, fontSize: 18,
          cursor: "pointer", boxShadow: "0 6px 24px rgba(0,0,0,0.45)",
        }} title="CalibrationOS Assist">
          AI
        </button>
      )}

      {/* panel */}
      {open && (
        <div data-testid="assist-panel" style={{
          position: "fixed", right: 20, bottom: 20, zIndex: 50,
          width: "min(420px, calc(100vw - 40px))", height: "min(560px, calc(100vh - 80px))",
          display: "flex", flexDirection: "column",
          background: "var(--bg-surface)", border: "1px solid var(--border)",
          borderRadius: 14, boxShadow: "0 12px 40px rgba(0,0,0,0.55)", overflow: "hidden",
        }}>
          <div style={{
            padding: "10px 14px", borderBottom: "1px solid var(--border)",
            display: "flex", justifyContent: "space-between", alignItems: "center",
            background: "var(--bg-elevated)",
          }}>
            <div style={{ fontFamily: "'Barlow Semi Condensed', sans-serif", fontWeight: 600 }}>
              <span className="accent">ASSIST</span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={() => { setMessages([]); setConversationId(null); }}
                data-testid="assist-new-chat">New chat</button>
              <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={() => setOpen(false)} data-testid="assist-close">✕</button>
            </div>
          </div>

          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: 14,
                                        display: "flex", flexDirection: "column", gap: 10 }}>
            {messages.length === 0 && (
              <div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
                  Ask me anything about the operation, or tell me to do something — real actions
                  always wait for your confirmation.
                </div>
                {SUGGESTIONS.map(s => (
                  <button key={s} className="btn btn-ghost"
                    style={{ display: "block", width: "100%", textAlign: "left",
                             marginBottom: 6, fontSize: 13 }}
                    onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} style={{
                alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "88%",
              }}>
                <div style={{
                  padding: "8px 12px", borderRadius: 10, fontSize: 13.5,
                  whiteSpace: "pre-wrap", wordBreak: "break-word",
                  background: m.role === "user" ? "var(--accent-dim)" : "var(--bg-elevated)",
                  border: "1px solid " + (m.error ? "rgba(239,68,68,0.4)" : "var(--border)"),
                  color: m.error ? "var(--red)" : "var(--text-primary)",
                }}>{m.text}</div>

                {m.pending && (
                  <div data-testid={`assist-confirm-${m.pending.id}`} style={{
                    marginTop: 6, padding: 10, borderRadius: 10,
                    border: "1px solid rgba(249,115,22,0.45)", background: "rgba(249,115,22,0.08)",
                  }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 8 }}>
                      {m.pending.summary}
                    </div>
                    {m.pending.status === "pending" ? (
                      <div style={{ display: "flex", gap: 8 }}>
                        <button className="btn btn-primary" style={{ padding: "5px 14px", fontSize: 12.5 }}
                          disabled={busy} onClick={() => confirmAction(m.pending)}
                          data-testid="assist-confirm-btn">Confirm</button>
                        <button className="btn btn-ghost" style={{ padding: "5px 14px", fontSize: 12.5 }}
                          disabled={busy} onClick={() => cancelAction(m.pending)}
                          data-testid="assist-cancel-btn">Cancel</button>
                      </div>
                    ) : (
                      <span className={`badge badge-${m.pending.status === "executed" ? "complete" : "cancelled"}`}>
                        {m.pending.status}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="muted" style={{ fontSize: 13 }}>Thinking…</div>}
          </div>

          <form onSubmit={e => { e.preventDefault(); send(); }} style={{
            display: "flex", gap: 8, padding: 12, borderTop: "1px solid var(--border)",
            background: "var(--bg-elevated)",
          }}>
            <input className="input" style={{ flex: 1 }} value={input} disabled={busy}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask or command…" data-testid="assist-input" />
            <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}
              data-testid="assist-send">Send</button>
          </form>
        </div>
      )}
    </>
  );
}
