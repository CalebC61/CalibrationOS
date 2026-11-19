import { fireEvent, render, screen } from "@testing-library/react";

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: typeof to === "string" ? to : "", ...rest }, children),
  };
}, { virtual: true });

jest.mock("./components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("./lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
  formatDate: () => "Tue, Nov 17",
  formatTime: () => "9:00 AM",
}));

import ShopsList from "./pages/ShopsList";
import Money from "./pages/Money";
import Settings from "./pages/Settings";
import { api } from "./lib/api";

function renderPage(ui, path) {
  window.history.pushState({}, "", path);
  return render(ui);
}

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/email-log")) return Promise.resolve({ data: { sent: [], pending_manual: [] } });
    if (path.includes("/days-off")) return Promise.resolve({ data: { days: [], conflicts: [] } });
    if (path.includes("/billing/late-fees")) return Promise.resolve({ data: { events: [] } });
    if (path.includes("/email-outbox")) return Promise.resolve({ data: [] });
    if (path.includes("/integrations/status")) {
      return Promise.resolve({ data: { xero: { configured: false }, growth: { enabled: false, contact_count: 0 } } });
    }
    return Promise.resolve({ data: [] });
  });
});

afterEach(() => {
  window.history.pushState({}, "", "/");
});

test("shops keeps the list and opens new signups and invites without sending", async () => {
  renderPage(<ShopsList />, "/shops");
  expect(await screen.findByTestId("shop-search")).toBeInTheDocument();
  expect(screen.getByTestId("add-shop-btn")).toBeInTheDocument();
  expect(screen.getByTestId("section-list")).toHaveAttribute("aria-selected", "true");

  fireEvent.click(screen.getByTestId("section-signups"));
  expect(await screen.findByRole("heading", { name: "New shops" })).toBeInTheDocument();
  expect(screen.getByText(/do not approve them first/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Earlier requests" })).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("section-invites"));
  expect(await screen.findByRole("heading", { name: "Portal Invitations" })).toBeInTheDocument();
  const send = screen.getByTestId("send-invite");
  expect(send).toHaveTextContent("Send invite");
  expect(send).toBeDisabled();
  expect(api.post).not.toHaveBeenCalled();
  expect(`${window.location.pathname}${window.location.search}`).toBe("/shops?section=invites");
});

test("a bookmarked invites section opens the invite form", async () => {
  renderPage(<ShopsList />, "/shops?section=invites");
  expect(await screen.findByTestId("send-invite")).toBeDisabled();
  expect(screen.getByTestId("section-invites")).toHaveAttribute("aria-selected", "true");
  expect(api.post).not.toHaveBeenCalled();
});

test("money opens charges and invoices on one page", async () => {
  renderPage(<Money />, "/money");
  expect(await screen.findByRole("heading", { name: "Charge Queue" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Money" })).toBeInTheDocument();
  expect(screen.getByTestId("section-charges")).toHaveAttribute("aria-selected", "true");

  fireEvent.click(screen.getByTestId("section-invoices"));
  expect(await screen.findByRole("heading", { name: "Invoices" })).toBeInTheDocument();
  expect(screen.getByText(/files one Xero draft/i)).toBeInTheDocument();
  expect(`${window.location.pathname}${window.location.search}`).toBe("/money?section=invoices");
  expect(api.post).not.toHaveBeenCalled();
});

test("settings keeps the old tabs and adds days off, held email, messages, and growth", async () => {
  renderPage(<Settings />, "/settings?section=days-off");
  expect(await screen.findByRole("heading", { name: "Days off" })).toBeInTheDocument();
  expect(screen.getByTestId("tab-pricing")).toBeInTheDocument();
  expect(screen.getByTestId("tab-technicians")).toBeInTheDocument();
  expect(screen.getByTestId("tab-schedule")).toBeInTheDocument();
  expect(screen.getByTestId("tab-integrations")).toBeInTheDocument();
  expect(screen.getByTestId("map-pins-link")).toHaveAttribute("href", "/map-pins");
  expect(screen.getByTestId("tab-days-off")).toHaveAttribute("aria-selected", "true");

  fireEvent.click(screen.getByTestId("tab-email"));
  expect(await screen.findByRole("heading", { name: "Email preview" })).toBeInTheDocument();
  expect(screen.getByText(/Nothing on this page sends mail/i)).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("tab-messages"));
  expect(await screen.findByRole("heading", { name: "Messages" })).toBeInTheDocument();
  expect(screen.getByText(/Mock SMS log/i)).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("tab-growth"));
  expect(await screen.findByTestId("growth-off")).toBeInTheDocument();
  expect(screen.getByText(/PARTNER GROWTH ENGINE/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});
