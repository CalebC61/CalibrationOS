import { Component } from "react";
import Brand from "./Brand";

export function reportClientError({ message, stack, source, path }) {
  try {
    const base = process.env.REACT_APP_BACKEND_URL;
    if (!base) return;
    const page = String(path || (typeof window !== "undefined" ? window.location.pathname : "") || "/")
      .split("?")[0]
      .split("#")[0]
      .slice(0, 200);
    const body = JSON.stringify({
      message: String(message || "").slice(0, 500),
      stack: String(stack || "").slice(0, 1200),
      path: page || "/",
      source: String(source || "client").slice(0, 40),
    });
    if (body.length > 3500) return;
    fetch(`${base}/api/client-errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // A failed report must not replace the original error.
  }
}

function CrashScreen() {
  return (
    <main
      data-testid="app-error"
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2.5rem 1.5rem",
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
      }}
    >
      <div style={{ width: "min(100%, 32rem)" }}>
        <Brand size={28} />
        <h1
          style={{
            fontFamily: "var(--font-body), sans-serif",
            fontSize: "1.75rem",
            fontWeight: 600,
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
            margin: "1.75rem 0 0.75rem",
          }}
        >
          Something went wrong
        </h1>
        <p
          style={{
            color: "var(--text-muted)",
            fontSize: "1rem",
            lineHeight: 1.5,
            margin: "0 0 1.75rem",
            maxWidth: "36rem",
          }}
        >
          Refresh the page to keep going.
        </p>
        <button
          type="button"
          className="btn btn-primary app-error-refresh"
          data-testid="app-error-refresh"
          onClick={() => window.location.reload()}
        >
          Refresh
        </button>
      </div>
    </main>
  );
}

export default class AppErrorBoundary extends Component {
  state = { crashed: false };

  reported = false;

  static getDerivedStateFromError() {
    return { crashed: true };
  }

  componentDidMount() {
    window.addEventListener("error", this.onWindowError);
    window.addEventListener("unhandledrejection", this.onRejection);
  }

  componentWillUnmount() {
    window.removeEventListener("error", this.onWindowError);
    window.removeEventListener("unhandledrejection", this.onRejection);
  }

  reportOnce(payload) {
    if (this.reported) return;
    this.reported = true;
    reportClientError(payload);
  }

  componentDidCatch(error, info) {
    this.reportOnce({
      message: error && error.message,
      stack: [error && error.stack, info && info.componentStack].filter(Boolean).join("\n"),
      source: "boundary",
    });
  }

  onWindowError = (event) => {
    if (event.target && event.target !== window) return;
    const error = event.error;
    this.reportOnce({
      message: (error && error.message) || event.message || "Script error",
      stack: (error && error.stack) || "",
      source: "window",
    });
    this.setState({ crashed: true });
  };

  onRejection = (event) => {
    if (event.preventDefault) event.preventDefault();
    const reason = event.reason;
    const error = reason instanceof Error ? reason : null;
    this.reportOnce({
      message: error ? error.message : String(reason || "Unhandled rejection"),
      stack: error && error.stack ? error.stack : "",
      source: "unhandledrejection",
    });
    this.setState({ crashed: true });
  };

  render() {
    if (this.state.crashed) return <CrashScreen />;
    return this.props.children;
  }
}
