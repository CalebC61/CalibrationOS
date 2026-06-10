import { Link, NavLink, useNavigate } from "react-router-dom";
import { getPortalAuth, setPortalAuth } from "../lib/portalApi";

export default function PortalShell({ children }) {
  const auth = getPortalAuth();
  const nav = useNavigate();
  function logout() { setPortalAuth(null); nav("/portal/login"); }
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      <header style={{
        borderBottom: "1px solid var(--border)", padding: "12px 24px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "var(--bg-primary)", position: "sticky", top: 0, zIndex: 20,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <Link to="/portal" className="font-display" style={{ fontSize: 22, fontWeight: 800, letterSpacing: "0.04em" }}>
            CALIBRATION<span style={{ color: "var(--accent)" }}>OS</span>
            <span className="muted" style={{ fontSize: 11, marginLeft: 8, letterSpacing: "0.16em", textTransform: "uppercase" }}>Shop Portal</span>
          </Link>
          {auth && (
            <nav style={{ display: "flex", gap: 4 }}>
              {[
                { to: "/portal", label: "Dashboard", end: true },
                { to: "/portal/jobs", label: "My Jobs" },
                { to: "/portal/book", label: "Book" },
                { to: "/portal/settings", label: "Settings" },
              ].map(l => (
                <NavLink key={l.to} to={l.to} end={l.end}
                  data-testid={`portal-nav-${l.label.toLowerCase().replace(/ /g, "-")}`}
                  className={({ isActive }) => "tab-btn" + (isActive ? " active" : "")}
                  style={{ padding: "8px 12px", marginRight: 4, borderBottom: "none", borderRadius: 8 }}>
                  {l.label}
                </NavLink>
              ))}
            </nav>
          )}
        </div>
        {auth ? (
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>{auth.shop_name}</span>
            <button className="btn btn-ghost" onClick={logout} data-testid="portal-logout">Sign Out</button>
          </div>
        ) : (
          <Link to="/portal/login" className="btn btn-primary">Sign In</Link>
        )}
      </header>
      <main className="container-app page-fade">{children}</main>
    </div>
  );
}
