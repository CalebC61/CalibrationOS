import { render, screen, waitFor } from "@testing-library/react";
import { OWNER_REDIRECTS } from "./ownerNav";

jest.mock("react-router-dom", () => {
  const React = require("react");
  const listeners = new Set();

  function current() {
    const url = new URL(global.location.href);
    return { pathname: url.pathname, search: url.search };
  }

  function go(to, replace) {
    const url = new URL(to, global.location.origin);
    const next = `${url.pathname}${url.search}`;
    const here = `${global.location.pathname}${global.location.search}`;
    if (here === next) return;
    if (replace) global.history.replaceState({}, "", next);
    else global.history.pushState({}, "", next);
    listeners.forEach((fn) => fn());
  }

  function useLocation() {
    const [, bump] = React.useState(0);
    const notify = React.useRef(null);
    if (!notify.current) {
      notify.current = () => bump((n) => n + 1);
      listeners.add(notify.current);
    }
    React.useEffect(() => () => listeners.delete(notify.current), []);
    return current();
  }

  function matchPath(pattern, pathname) {
    if (pattern === "*") return true;
    const expected = String(pattern || "").split("/").filter(Boolean);
    const actual = String(pathname || "").split("/").filter(Boolean);
    if (expected.length !== actual.length) return false;
    return expected.every((part, index) => part.startsWith(":") || part === actual[index]);
  }

  function routeScore(pattern) {
    if (pattern === "*") return 0;
    const parts = String(pattern || "").split("/").filter(Boolean);
    const staticParts = parts.filter((part) => part && !part.startsWith(":")).length;
    return staticParts * 10 + parts.length;
  }

  function Routes({ children }) {
    const loc = useLocation();
    let best = null;
    let bestScore = -1;
    React.Children.forEach(children, (route) => {
      if (!route || !route.props || route.props.path == null) return;
      if (!matchPath(route.props.path, loc.pathname)) return;
      const score = routeScore(route.props.path);
      if (score > bestScore) {
        best = route;
        bestScore = score;
      }
    });
    return best ? best.props.element : null;
  }

  function Navigate({ to, replace }) {
    const loc = useLocation();
    React.useEffect(() => {
      const target = typeof to === "string" ? to : "";
      if (`${loc.pathname}${loc.search}` !== target) go(target, replace !== false);
    }, [to, replace, loc.pathname, loc.search]);
    return null;
  }

  function anchor(to, children, rest, onClick) {
    return React.createElement("a", {
      href: typeof to === "string" ? to : "",
      onClick,
      ...rest,
    }, children);
  }

  return {
    BrowserRouter: ({ children }) => children,
    Routes,
    Route: () => null,
    Navigate,
    useLocation,
    useNavigate: () => (to) => go(typeof to === "string" ? to : "/", false),
    useParams: () => ({}),
    useSearchParams: () => [new URLSearchParams(global.location.search), () => {}],
    Link: ({ children, to, ...rest }) => anchor(to, children, rest, (event) => {
      event.preventDefault();
      go(to, false);
    }),
    NavLink: ({ children, to, className, end, ...rest }) => {
      const loc = useLocation();
      const href = typeof to === "string" ? to : "";
      const active = end ? loc.pathname === href : loc.pathname === href || loc.pathname.startsWith(`${href}/`);
      const cls = typeof className === "function" ? className({ isActive: active }) : className;
      return anchor(to, children, { ...rest, className: cls }, (event) => {
        event.preventDefault();
        go(href, false);
      });
    },
  };
}, { virtual: true });

jest.mock("./components/Assist", () => () => null);

jest.mock("axios", () => {
  const instance = {
    get: () => Promise.resolve({ data: [] }),
    post: () => Promise.resolve({ data: {} }),
    put: () => Promise.resolve({ data: {} }),
    patch: () => Promise.resolve({ data: {} }),
    delete: () => Promise.resolve({ data: {} }),
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
  };
  return { create: () => instance };
});

jest.mock("./lib/api", () => ({
  API: "http://localhost:8001/api",
  api: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
  getStoredAuth: () => {
    const token = global.localStorage.getItem("cos_token");
    if (!token) return null;
    return {
      token,
      role: global.localStorage.getItem("cos_role"),
      name: global.localStorage.getItem("cos_name"),
      tech_id: global.localStorage.getItem("cos_tech_id"),
    };
  },
  setStoredAuth: jest.fn(),
  setToken: jest.fn(),
  formatTime: () => "9:00 AM",
  formatDate: () => "Tue, Nov 17",
  todayStr: () => "2026-11-19",
  dateStr: () => "2026-11-19",
  phoenixTodayStr: () => "2026-11-19",
  isOnDayBoard: (job) => !job || (job.status !== "cancelled" && job.status !== "declined"),
  isPhoenixToday: () => false,
  jobStatusLabel: (status) => status || "",
}));

jest.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => children || null,
  Marker: () => null,
  Polyline: () => null,
  Tooltip: () => null,
  useMap: () => ({ fitBounds: () => {} }),
}));

jest.mock("leaflet", () => ({
  divIcon: () => ({}),
  icon: () => ({}),
  map: () => ({}),
}));

import App from "./App";
import { api } from "./lib/api";

beforeEach(() => {
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/email-log")) return Promise.resolve({ data: { sent: [], pending_manual: [] } });
    if (path.includes("/days-off")) return Promise.resolve({ data: { days: [], conflicts: [] } });
    if (path.includes("/billing/late-fees")) return Promise.resolve({ data: { events: [] } });
    if (path.includes("/integrations/status")) return Promise.resolve({ data: {} });
    return Promise.resolve({ data: [] });
  });
  api.post.mockResolvedValue({ data: {} });
});

const LANDING = {
  "/requests": { heading: "New shops" },
  "/invites": { heading: "Portal Invitations" },
  "/charges": { heading: "Charge Queue" },
  "/invoices": { heading: "Invoices" },
  "/days-off": { heading: "Days off" },
  "/email-preview": { heading: "Email preview" },
  "/messages": { heading: "Messages" },
  "/growth": { text: /PARTNER GROWTH ENGINE/ },
};

function signInOwner() {
  localStorage.setItem("cos_token", "token");
  localStorage.setItem("cos_role", "owner");
  localStorage.setItem("cos_name", "Caleb");
}

afterEach(() => {
  localStorage.clear();
  window.history.pushState({}, "", "/");
});

test("every old owner tab redirects to its new section", () => {
  expect(OWNER_REDIRECTS.map((item) => item.path).sort()).toEqual(Object.keys(LANDING).sort());
});

test.each(OWNER_REDIRECTS)("$path redirects to $to", async ({ path, to }) => {
  signInOwner();
  window.history.pushState({}, "", path);
  render(<App />);
  const expectAt = LANDING[path];
  if (expectAt.heading) {
    expect(await screen.findByRole("heading", { name: expectAt.heading })).toBeInTheDocument();
  } else {
    expect(await screen.findByText(expectAt.text)).toBeInTheDocument();
  }
  await waitFor(() => {
    expect(`${window.location.pathname}${window.location.search}`).toBe(to);
  });
});

test("an old money link stays behind the owner login", async () => {
  window.history.pushState({}, "", "/charges");
  render(<App />);
  expect(await screen.findByTestId("login-form")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Money" })).not.toBeInTheDocument();
});
