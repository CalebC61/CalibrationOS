import { fireEvent, render, screen } from "@testing-library/react";

const auth = { current: null };

jest.mock("../lib/api", () => ({
  getStoredAuth: () => auth.current,
  setStoredAuth: (value) => { auth.current = value; },
}));

jest.mock("./Assist", () => () => null);

jest.mock("react-router-dom", () => {
  const React = require("react");
  const state = { path: "/dashboard" };
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

import Shell from "./Shell";
import { setPath } from "react-router-dom";

beforeEach(() => {
  auth.current = { token: "token", role: "owner", name: "Caleb" };
  setPath("/dashboard");
});

function renderShell() {
  return render(<Shell><p>Board</p></Shell>);
}

test("the owner bar is Today, Shops, Money, and Settings", () => {
  renderShell();
  expect(screen.getByTestId("nav-today")).toHaveAttribute("href", "/dashboard");
  expect(screen.getByTestId("nav-shops")).toHaveAttribute("href", "/shops");
  expect(screen.getByTestId("nav-money")).toHaveAttribute("href", "/money");
  expect(screen.getByTestId("nav-settings")).toHaveAttribute("href", "/settings");
  expect(screen.getAllByRole("link").filter((link) => link.getAttribute("data-testid")?.startsWith("nav-"))).toHaveLength(4);
  for (const label of ["Dispatch", "New shops", "Days off", "Email preview", "Invites", "Charges", "Invoices", "Messages", "Growth"]) {
    expect(screen.queryByRole("link", { name: label })).not.toBeInTheDocument();
  }
  expect(screen.getByTestId("logout-btn")).toBeInTheDocument();
});

test("the menu button opens the owner nav and closes after a choice", () => {
  renderShell();
  const menu = screen.getByTestId("owner-menu");
  const nav = screen.getByTestId("owner-nav");
  expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(menu).toHaveAttribute("aria-controls", "owner-nav");
  expect(nav).not.toHaveClass("open");
  fireEvent.click(menu);
  expect(menu).toHaveAttribute("aria-expanded", "true");
  expect(nav).toHaveClass("open");
  fireEvent.click(screen.getByTestId("nav-shops"));
  expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(nav).not.toHaveClass("open");
  expect(screen.getByTestId("nav-shops")).toHaveClass("active");
});

test("settings stays marked while checking addresses", () => {
  setPath("/map-pins");
  renderShell();
  expect(screen.getByTestId("nav-settings")).toHaveClass("active");
  expect(screen.getByTestId("nav-today")).not.toHaveClass("active");
});

test("a technician does not get the owner bar", () => {
  auth.current = { token: "token", role: "tech", name: "Alex" };
  renderShell();
  expect(screen.queryByTestId("owner-nav")).not.toBeInTheDocument();
  expect(screen.queryByTestId("owner-menu")).not.toBeInTheDocument();
  expect(screen.getByTestId("logout-btn")).toBeInTheDocument();
});
