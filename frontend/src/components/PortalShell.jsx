import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { getPortalAuth, setPortalAuth } from "../lib/portalApi";
import Brand from "./Brand";

const LINKS = [
  { to: "/portal", label: "Today", end: true },
  { to: "/portal/jobs", label: "Jobs" },
  { to: "/portal/book", label: "Book" },
  { to: "/portal/settings", label: "Account" },
];

export default function PortalShell({ children }) {
  const auth = getPortalAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [menu, setMenu] = useState(false);
  useEffect(() => { setMenu(false); }, [pathname]);
  function logout() { setPortalAuth(null); nav("/portal/login"); }
  return (
    <div className="portal-app" style={{ minHeight: "100dvh", background: "var(--bg-primary)" }}>
      <header className="portal-header">
        <div className="portal-header-bar">
          <Link to="/portal" className="portal-brand"><Brand size={20} tag="Shop Portal" /></Link>
          {auth && (
            <button
              className="btn btn-ghost portal-menu"
              type="button"
              onClick={() => setMenu(open => !open)}
              aria-expanded={menu}
              aria-controls="portal-nav"
              data-testid="portal-menu"
            >
              Menu
            </button>
          )}
          {auth && (
            <nav id="portal-nav" className={"portal-nav" + (menu ? " open" : "")} data-testid="portal-nav">
              {LINKS.map(l => (
                <NavLink key={l.to} to={l.to} end={l.end}
                  data-testid={`portal-nav-${l.label.toLowerCase()}`}
                  className={({ isActive }) => "tab-btn" + (isActive ? " active" : "")}>
                  {l.label}
                </NavLink>
              ))}
            </nav>
          )}
          {auth ? (
            <div className="portal-account">
              <span className="muted portal-shop-name">{auth.shop_name}</span>
              <button className="btn btn-ghost" type="button" onClick={logout} data-testid="portal-logout">Sign Out</button>
            </div>
          ) : (
            <Link to="/portal/login" className="btn btn-primary portal-account">Sign In</Link>
          )}
        </div>
      </header>
      <main className="container-app page-fade">{children}</main>
    </div>
  );
}
