import { Link, NavLink, useNavigate } from "react-router-dom";
import { getStoredAuth, setStoredAuth } from "../lib/api";
import Brand from "./Brand";

export default function Shell({ children, hideNav }) {
  const auth = getStoredAuth();
  const nav = useNavigate();
  function logout() { setStoredAuth(null); nav("/login"); }
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      {!hideNav && (
        <header style={{
          borderBottom: "1px solid var(--border)", padding: "12px 24px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          background: "var(--bg-primary)", position: "sticky", top: 0, zIndex: 20,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
            <Link to="/dashboard"><Brand size={22} /></Link>
            {auth?.role === "owner" && (
              <nav style={{ display: "flex", gap: 4 }}>
                {[
                  { to: "/dashboard", label: "Dispatch" },
                  { to: "/shops", label: "Shops" },
                  { to: "/invites", label: "Invites" },
                  { to: "/charges", label: "Charges" },
                  { to: "/invoices", label: "Invoices" },
                  { to: "/messages", label: "Messages" },
                  { to: "/settings", label: "Settings" },
                ].map(l => (
                  <NavLink key={l.to} to={l.to}
                    data-testid={`nav-${l.label.toLowerCase()}`}
                    className={({ isActive }) => "tab-btn" + (isActive ? " active" : "")}
                    style={{ padding: "8px 12px", marginRight: 4, borderBottom: "none", borderRadius: 8 }}>
                    {l.label}
                  </NavLink>
                ))}
              </nav>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="muted" style={{ fontSize: 13 }}>{auth?.name}</span>
            <button className="btn btn-ghost" onClick={logout} data-testid="logout-btn">Sign Out</button>
          </div>
        </header>
      )}
      <main className="container-app page-fade">{children}</main>
    </div>
  );
}
