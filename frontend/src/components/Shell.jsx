import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { getStoredAuth, setStoredAuth } from "../lib/api";
import { OWNER_NAV } from "../ownerNav";
import Brand from "./Brand";
import Assist from "./Assist";

export default function Shell({ children, hideNav }) {
  const auth = getStoredAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [menu, setMenu] = useState(false);
  const owner = auth?.role === "owner";
  useEffect(() => { setMenu(false); }, [pathname]);
  function logout() { setStoredAuth(null); nav("/login"); }
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      {!hideNav && (
        <header className="shell-header">
          <div className="shell-header-bar">
            <Link to="/dashboard" className="shell-brand"><Brand size={22} /></Link>
            {owner && (
              <button
                className="btn btn-ghost nav-toggle"
                type="button"
                onClick={() => setMenu((open) => !open)}
                aria-expanded={menu}
                aria-controls="owner-nav"
                data-testid="owner-menu"
              >
                Menu
              </button>
            )}
            {owner && (
              <nav
                id="owner-nav"
                className={"owner-nav" + (menu ? " open" : "")}
                data-testid="owner-nav"
                onClick={() => setMenu(false)}
              >
                {OWNER_NAV.map((link) => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    end={link.end}
                    data-testid={link.testId}
                    className={({ isActive }) => {
                      const extra = (link.also || []).includes(pathname);
                      return "tab-btn" + ((isActive || extra) ? " active" : "");
                    }}
                  >
                    {link.label}
                  </NavLink>
                ))}
              </nav>
            )}
            <div className="shell-account">
              <span className="muted shell-user">{auth?.name}</span>
              <button className="btn btn-ghost" type="button" onClick={logout} data-testid="logout-btn">Sign Out</button>
            </div>
          </div>
        </header>
      )}
      <main className="container-app page-fade">{children}</main>
      {owner && <Assist />}
    </div>
  );
}
