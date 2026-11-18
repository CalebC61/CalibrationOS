import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn(), put: jest.fn() },
}));

import Settings from "./Settings";
import { api } from "../lib/api";

function statusBody({ connected, org }) {
  return {
    data: {
      xero: {
        configured: true,
        connected,
        org_name: org,
        mode: connected ? "live" : "ready",
      },
      google_maps: { mode: "mock" },
      growth: { enabled: false, contact_count: 0 },
      assist: { enabled: false, configured: false },
    },
  };
}

afterEach(() => {
  window.history.pushState({}, "", "/settings");
});

test("returning from Xero shows the connected org without a reload", async () => {
  window.history.pushState({}, "", "/settings?xero=connected");
  api.get.mockImplementation((url) => {
    if (String(url).includes("/integrations/status")) {
      return Promise.resolve(statusBody({ connected: true, org: "The Calibration Crew" }));
    }
    return Promise.resolve({ data: [] });
  });

  render(<Settings />);

  expect(await screen.findByText("Connected — The Calibration Crew")).toBeInTheDocument();
  expect(screen.getByTestId("xero-disconnect")).toBeInTheDocument();
  expect(screen.getByTestId("xero-banner")).toHaveTextContent("Xero connected");
});

test("a failed Xero return shows the error and the disconnected state", async () => {
  window.history.pushState({}, "", "/settings?xero=error");
  api.get.mockImplementation((url) => {
    if (String(url).includes("/integrations/status")) {
      return Promise.resolve(statusBody({ connected: false, org: null }));
    }
    return Promise.resolve({ data: [] });
  });

  render(<Settings />);

  expect(await screen.findByTestId("xero-banner")).toHaveTextContent("Xero connection failed");
  expect(screen.getByText("Configured — not connected")).toBeInTheDocument();
  expect(screen.getByTestId("xero-connect")).toBeInTheDocument();
});

test("Disconnect shows not connected even when the follow-up read does not return", async () => {
  window.confirm = jest.fn(() => true);
  let statusCalls = 0;
  api.get.mockImplementation((url) => {
    if (String(url).includes("/integrations/status")) {
      statusCalls += 1;
      if (statusCalls === 1) return Promise.resolve(statusBody({ connected: true, org: "The Calibration Crew" }));
      return new Promise(() => {});
    }
    return Promise.resolve({ data: [] });
  });
  api.post.mockResolvedValue({ data: { ok: true } });

  render(<Settings />);
  fireEvent.click(screen.getByTestId("tab-integrations"));
  expect(await screen.findByText("Connected — The Calibration Crew")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("xero-disconnect"));

  await waitFor(() => expect(screen.getByText("Configured — not connected")).toBeInTheDocument());
  expect(screen.getByTestId("xero-connect")).toBeInTheDocument();
  expect(screen.queryByTestId("xero-disconnect")).not.toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("/auth/xero/disconnect");
});

test("focusing the window replaces a stale Xero org name", async () => {
  let org = "Old Org";
  api.get.mockImplementation((url) => {
    if (String(url).includes("/integrations/status")) {
      return Promise.resolve(statusBody({ connected: true, org }));
    }
    return Promise.resolve({ data: [] });
  });

  render(<Settings />);
  fireEvent.click(screen.getByTestId("tab-integrations"));
  expect(await screen.findByText("Connected — Old Org")).toBeInTheDocument();

  org = "New Org";
  fireEvent(window, new Event("focus"));

  expect(await screen.findByText("Connected — New Org")).toBeInTheDocument();
});

test("restoring the page after the Xero redirect refetches the connection", async () => {
  api.get.mockImplementation((url) => {
    if (String(url).includes("/integrations/status")) {
      return Promise.resolve(statusBody({ connected: false, org: null }));
    }
    return Promise.resolve({ data: [] });
  });

  render(<Settings />);
  fireEvent.click(screen.getByTestId("tab-integrations"));
  expect(await screen.findByText("Configured — not connected")).toBeInTheDocument();

  api.get.mockImplementation((url) => {
    if (String(url).includes("/integrations/status")) {
      return Promise.resolve(statusBody({ connected: true, org: "The Calibration Crew" }));
    }
    return Promise.resolve({ data: [] });
  });
  fireEvent(window, new Event("pageshow"));

  expect(await screen.findByText("Connected — The Calibration Crew")).toBeInTheDocument();
  expect(screen.getByTestId("xero-disconnect")).toBeInTheDocument();
});
