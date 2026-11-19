import { fireEvent, render, screen } from "@testing-library/react";

const auth = { current: null };

jest.mock("../lib/portalApi", () => ({
  getPortalAuth: () => auth.current,
  setPortalAuth: (value) => { auth.current = value; },
}));

jest.mock("react-router-dom", () => {
  const React = require("react");
  const state = { path: "/portal" };
  const listeners = new Set();
  function setPath(next) {
    state.path = next;
    listeners.forEach((fn) => fn());
  }
  return {
    setPath,
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
    NavLink: ({ children, to, className, end, ...rest }) => {
      const active = end ? state.path === to : state.path === to || state.path.startsWith(`${to}/`);
      const cls = typeof className === "function" ? className({ isActive: active }) : className;
      return React.createElement("a", {
        href: to,
        className: cls,
        onClick: (event) => {
          event.preventDefault();
          setPath(to);
        },
        ...rest,
      }, children);
    },
    useNavigate: () => setPath,
    useLocation: () => {
      const [, bump] = React.useState(0);
      React.useEffect(() => {
        const fn = () => bump((n) => n + 1);
        listeners.add(fn);
        return () => listeners.delete(fn);
      }, []);
      return { pathname: state.path };
    },
  };
}, { virtual: true });

import PortalShell from "./PortalShell";
import { setPath } from "react-router-dom";

beforeEach(() => {
  auth.current = { token: "token", shop_name: "Jarvis Glass" };
  setPath("/portal");
});

function renderShell() {
  return render(<PortalShell><p>Day</p></PortalShell>);
}

test("the shop menu is Today, Jobs, Book, and Account", () => {
  renderShell();
  expect(screen.getByTestId("portal-nav-today")).toHaveAttribute("href", "/portal");
  expect(screen.getByTestId("portal-nav-jobs")).toHaveAttribute("href", "/portal/jobs");
  expect(screen.getByTestId("portal-nav-book")).toHaveAttribute("href", "/portal/book");
  expect(screen.getByTestId("portal-nav-account")).toHaveAttribute("href", "/portal/settings");
  expect(screen.queryByText("Scorecard")).not.toBeInTheDocument();
  expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
  expect(screen.getByTestId("portal-logout")).toBeInTheDocument();
});

test("the menu button opens the shop nav", () => {
  renderShell();
  const menu = screen.getByTestId("portal-menu");
  const nav = screen.getByTestId("portal-nav");
  expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(nav).not.toHaveClass("open");
  fireEvent.click(menu);
  expect(menu).toHaveAttribute("aria-expanded", "true");
  expect(nav).toHaveClass("open");
  fireEvent.click(screen.getByTestId("portal-nav-jobs"));
  expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(nav).not.toHaveClass("open");
});
