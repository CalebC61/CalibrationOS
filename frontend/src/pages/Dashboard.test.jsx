import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

var mockAuth = { role: "owner", name: "Caleb" };

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
  };
}, { virtual: true });

jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("../components/RouteMap", () => () => null);
jest.mock("../components/TomorrowStrip", () => () => null);
jest.mock("../components/JobEditModal", () => () => null);

jest.mock("../lib/api", () => {
  const phoenixNow = new Date("2026-11-18T04:00:00Z");
  function phoenixTodayStr(instant = phoenixNow) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Phoenix",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(instant);
    const get = (type) => parts.find((part) => part.type === type).value;
    return `${get("year")}-${get("month")}-${get("day")}`;
  }
  return {
    api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
    formatTime: (iso) => {
      if (typeof iso === "string" && iso.startsWith("2099-")) return `T${iso.slice(11, 16)}`;
      return "9:00 AM";
    },
    formatDate: () => "Tue, Nov 17",
    phoenixTodayStr,
    dateStr: () => "2026-11-17",
    todayStr: () => "2026-11-17",
    getStoredAuth: () => mockAuth,
    isOnDayBoard: (job) => job?.status !== "cancelled" && job?.status !== "declined",
    isPhoenixToday: (iso, now = phoenixNow) => {
      if (!iso) return false;
      return phoenixTodayStr(new Date(iso)) === phoenixTodayStr(now);
    },
    jobStatusLabel: (status) => status || "",
  };
});

import Dashboard from "./Dashboard";
import { api } from "../lib/api";

afterEach(() => {
  mockAuth = { role: "owner", name: "Caleb" };
  window.history.pushState({}, "", "/");
});

const job = {
  id: "job-1",
  status: "on_site",
  scheduled_start: "2026-11-17T16:00:00Z",
  scheduled_end: "2026-11-17T17:00:00Z",
  shop_name: "Star Windshield",
  vehicle_year: 2020,
  vehicle_make: "Honda",
  vehicle_model: "Pilot",
  calibration_label: "Static ADAS Calibration",
  calibration_type: "static",
  job_address: "1 Main St, Gilbert, AZ",
  drive_time_minutes: 12,
  price: 125,
  technician_id: "tech-1",
  payment_status: "unpaid",
};

function mockGets(documents, listed = job) {
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [listed] });
    if (path.includes("/documents")) return Promise.resolve({ data: documents });
    if (path.includes("/dashboard/summary")) {
      return Promise.resolve({ data: { job_count: 1, revenue: 125, estimated_miles: 6, done_by: null, shop_emails_enabled: true } });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
}

function completePosts() {
  return api.post.mock.calls.filter(([url]) => String(url).endsWith("/complete"));
}

test("dashboard Complete asks for type, POP, and a post-scan before it files the job", async () => {
  window.confirm = jest.fn(() => true);
  mockGets([]);
  api.post.mockResolvedValue({ data: {} });
  render(<Dashboard />);

  fireEvent.click(await screen.findByTestId("job-action-job-1"));

  expect(completePosts()).toHaveLength(0);
  expect(window.confirm).not.toHaveBeenCalled();
  expect(await screen.findByTestId("dash-cal-type-job-1")).toBeInTheDocument();

  fireEvent.change(screen.getByTestId("dash-cal-type-job-1"), { target: { value: "dynamic" } });
  fireEvent.click(screen.getByTestId("dash-pop-none-job-1"));
  const finish = screen.getByTestId("dash-complete-job-1");
  expect(finish).toBeDisabled();
  fireEvent.click(finish);
  expect(completePosts()).toHaveLength(0);

  fireEvent.click(screen.getByTestId("dash-pop-amount-job-1"));
  fireEvent.change(screen.getByTestId("dash-pop-value-job-1"), { target: { value: "450" } });
  expect(finish).toBeDisabled();
});

test("dashboard Complete sends the type and POP once a post-scan is already on the job", async () => {
  mockGets([{ file_name: "Forsley_post_scan.pdf", content_type: "application/pdf", size_bytes: 2048 }]);
  api.post.mockResolvedValue({ data: {} });
  render(<Dashboard />);

  fireEvent.click(await screen.findByTestId("job-action-job-1"));
  expect(await screen.findByTestId("doc-uploaded")).toHaveTextContent("Forsley_post_scan.pdf");

  fireEvent.change(screen.getByTestId("dash-cal-type-job-1"), { target: { value: "tesla" } });
  fireEvent.click(screen.getByTestId("dash-pop-none-job-1"));
  fireEvent.click(screen.getByTestId("dash-complete-job-1"));

  await waitFor(() => expect(completePosts()).toHaveLength(1));
  const [url, body] = completePosts()[0];
  expect(url).toBe("/jobs/job-1/complete");
  expect(body).toEqual({
    result: "pass",
    notes: null,
    calibration_type: "tesla",
    pop: "none",
  });
});

test("dashboard Complete can upload the post-scan and then file the job", async () => {
  mockGets([]);
  api.post.mockImplementation((url) => {
    if (String(url).includes("upload-document")) {
      return Promise.resolve({
        data: { file_name: "CUSTOMER_STARWINDSHIELD_Honda_Pilot_2020.pdf", content_type: "application/pdf", size_bytes: 128 },
      });
    }
    return Promise.resolve({ data: {} });
  });
  render(<Dashboard />);

  fireEvent.click(await screen.findByTestId("job-action-job-1"));
  const input = await screen.findByTestId("doc-upload-job-1");
  fireEvent.change(input, {
    target: { files: [new File(["%PDF"], "scan.pdf", { type: "application/pdf" })] },
  });
  expect(await screen.findByTestId("doc-uploaded")).toHaveTextContent("Honda_Pilot_2020.pdf");

  fireEvent.click(screen.getByTestId("dash-pop-amount-job-1"));
  fireEvent.change(screen.getByTestId("dash-pop-value-job-1"), { target: { value: "$450.00" } });
  fireEvent.click(screen.getByTestId("dash-complete-job-1"));

  await waitFor(() => expect(completePosts()).toHaveLength(1));
  expect(completePosts()[0][1]).toEqual({
    result: "pass",
    notes: null,
    calibration_type: "static",
    pop: "$450.00",
  });
});

test("owner Delete asks before it removes the job, and Cancel sends nothing", async () => {
  mockGets([]);
  api.delete.mockResolvedValue({ data: { deleted: true, id: "job-1" } });
  render(<Dashboard />);

  fireEvent.click(await screen.findByTestId("job-delete-job-1"));
  expect(await screen.findByTestId("job-delete-dialog")).toHaveTextContent(
    "Are you sure you want to delete this job?",
  );
  expect(screen.getByTestId("job-delete-name")).toHaveTextContent("2020 Honda Pilot");
  expect(screen.getByTestId("job-delete-shop")).toHaveTextContent("Star Windshield");
  expect(screen.getByTestId("job-delete-date")).toHaveTextContent("Tue, Nov 17");
  expect(screen.queryByTestId("job-delete-warning")).not.toBeInTheDocument();
  expect(api.delete).not.toHaveBeenCalled();

  fireEvent.click(screen.getByTestId("job-delete-cancel"));
  await waitFor(() => expect(screen.queryByTestId("job-delete-dialog")).not.toBeInTheDocument());
  expect(api.delete).not.toHaveBeenCalled();
  expect(screen.getByTestId("job-card-job-1")).toBeInTheDocument();
});

function metricValue(label) {
  const labelNode = screen.getByText(label);
  return labelNode.nextElementSibling.textContent;
}

test("deleting the last job of the day clears est. miles and done by", async () => {
  const only = {
    ...job,
    id: "job-late",
    drive_time_minutes: 23,
    price: 125,
    scheduled_end: "2099-12-08T17:50:00Z",
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [only] });
    if (path.includes("/dashboard/summary")) {
      return Promise.resolve({
        data: {
          job_count: 1,
          revenue: 125,
          estimated_miles: 11.5,
          done_by: only.scheduled_end,
          shop_emails_enabled: true,
        },
      });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.delete.mockResolvedValue({ data: { deleted: true, id: "job-late" } });
  render(<Dashboard />);

  expect(await screen.findByText("11.5")).toBeInTheDocument();
  expect(metricValue("Done By")).toBe("T17:50");

  fireEvent.click(screen.getByTestId("job-delete-job-late"));
  fireEvent.click(screen.getByTestId("job-delete-confirm"));

  await waitFor(() => expect(screen.queryByTestId("job-card-job-late")).not.toBeInTheDocument());
  expect(metricValue("Jobs")).toBe("0");
  expect(metricValue("Revenue")).toBe("$0");
  expect(metricValue("Est. Miles")).toBe("0");
  expect(metricValue("Done By")).toBe("—");
});

test("a stale summary refresh cannot put miles or done by back after the last job is gone", async () => {
  const only = {
    ...job,
    id: "job-late",
    drive_time_minutes: 23,
    price: 125,
    scheduled_end: "2099-12-08T17:50:00Z",
  };
  const stale = {
    job_count: 1,
    revenue: 125,
    estimated_miles: 11.5,
    done_by: only.scheduled_end,
    shop_emails_enabled: true,
  };
  let summaryCalls = 0;
  let releaseStale = () => {};
  const staleSummary = new Promise((resolve) => {
    releaseStale = () => resolve({ data: stale });
  });
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [only] });
    if (path.includes("/dashboard/summary")) {
      summaryCalls += 1;
      if (summaryCalls > 1) return staleSummary;
      return Promise.resolve({ data: stale });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.delete.mockResolvedValue({ data: { deleted: true, id: "job-late" } });
  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("job-delete-job-late"));
  fireEvent.click(screen.getByTestId("job-delete-confirm"));
  await waitFor(() => expect(metricValue("Est. Miles")).toBe("0"));

  window.dispatchEvent(new Event("focus"));
  await waitFor(() => expect(summaryCalls).toBeGreaterThan(1));
  await act(async () => {
    releaseStale();
  });

  expect(metricValue("Jobs")).toBe("0");
  expect(metricValue("Revenue")).toBe("$0");
  expect(metricValue("Est. Miles")).toBe("0");
  expect(metricValue("Done By")).toBe("—");
  expect(screen.queryByTestId("job-card-job-late")).not.toBeInTheDocument();
});

test("deleting one job recomputes est. miles and done by from the jobs still on the day", async () => {
  const early = {
    ...job,
    id: "job-early",
    drive_time_minutes: 40,
    price: 125,
    scheduled_end: "2099-12-08T16:00:00Z",
  };
  const late = {
    ...job,
    id: "job-late",
    drive_time_minutes: 23,
    price: 125,
    scheduled_end: "2099-12-08T17:50:00Z",
  };
  const cancelled = {
    ...job,
    id: "job-cancelled",
    status: "cancelled",
    drive_time_minutes: 200,
    price: 999,
    scheduled_end: "2099-12-08T23:00:00Z",
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [early, late, cancelled] });
    if (path.includes("/dashboard/summary")) {
      return Promise.resolve({
        data: {
          job_count: 2,
          revenue: 250,
          estimated_miles: 31.5,
          done_by: late.scheduled_end,
          shop_emails_enabled: true,
        },
      });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.delete.mockResolvedValue({ data: { deleted: true, id: "job-late" } });
  render(<Dashboard />);

  expect(await screen.findByText("31.5")).toBeInTheDocument();
  expect(metricValue("Done By")).toBe("T17:50");
  expect(screen.queryByTestId("job-card-job-cancelled")).not.toBeInTheDocument();

  fireEvent.click(screen.getByTestId("job-delete-job-late"));
  fireEvent.click(screen.getByTestId("job-delete-confirm"));

  await waitFor(() => expect(screen.queryByTestId("job-card-job-late")).not.toBeInTheDocument());
  expect(screen.getByTestId("job-card-job-early")).toBeInTheDocument();
  expect(metricValue("Jobs")).toBe("1");
  expect(metricValue("Revenue")).toBe("$125");
  expect(metricValue("Est. Miles")).toBe("20");
  expect(metricValue("Done By")).toBe("T16:00");
});

test("Yes, delete removes the card without reloading the day", async () => {
  mockGets([]);
  api.delete.mockResolvedValue({ data: { deleted: true, id: "job-1" } });
  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("job-delete-job-1"));
  const getsBefore = api.get.mock.calls.length;
  fireEvent.click(screen.getByTestId("job-delete-confirm"));

  await waitFor(() => expect(screen.queryByTestId("job-card-job-1")).not.toBeInTheDocument());
  expect(api.delete).toHaveBeenCalledTimes(1);
  expect(api.delete).toHaveBeenCalledWith("/jobs/job-1");
  expect(api.post).not.toHaveBeenCalled();
  expect(api.get.mock.calls.length).toBe(getsBefore);
});

test("the delete dialog names a linked Xero draft and Stripe invoice", async () => {
  mockGets([], {
    ...job,
    xero_draft_status: "draft",
    xero_invoice_number: "INV-1042",
    stripe_invoice_id: "in_123",
  });
  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("job-delete-job-1"));
  const warnings = await screen.findAllByTestId("job-delete-warning");
  expect(warnings.map((node) => node.textContent)).toEqual([
    "This job has Xero draft INV-1042; deleting the job does not delete it in Xero",
    "This job has Stripe invoice in_123; deleting the job does not delete it in Stripe",
  ]);
  expect(api.delete).not.toHaveBeenCalled();
});

test("Start Driving waits until the Phoenix day of the job", async () => {
  mockGets([], {
    ...job,
    status: "booked",
    scheduled_start: "2026-11-19T16:00:00Z",
  });
  render(<Dashboard />);
  const action = await screen.findByTestId("job-action-job-1");
  expect(action).toBeDisabled();
  expect(action).toHaveTextContent("Start Driving");
  expect(screen.getByTestId("job-travel-wait-job-1")).toHaveTextContent("Available on the day of the job");
  expect(screen.queryByText("Dispatch to Contractor")).not.toBeInTheDocument();
  fireEvent.click(action);
  expect(api.post).not.toHaveBeenCalled();
  expect(api.get.mock.calls.some(([url]) => String(url).includes("contractor"))).toBe(false);
});

test("Start Driving sends the on-my-way step on a Phoenix-today job", async () => {
  mockGets([], {
    ...job,
    status: "booked",
    scheduled_start: "2026-11-18T02:00:00Z",
  });
  api.post.mockResolvedValue({ data: {} });
  render(<Dashboard />);
  const action = await screen.findByTestId("job-action-job-1");
  expect(action).toBeEnabled();
  expect(screen.queryByTestId("job-travel-wait-job-1")).not.toBeInTheDocument();
  fireEvent.click(action);
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/jobs/job-1/status", { status: "driving" }));
});

test("I've Arrived waits until the Phoenix day of the job", async () => {
  mockGets([], {
    ...job,
    status: "driving",
    scheduled_start: "2026-11-16T16:00:00Z",
  });
  render(<Dashboard />);
  const action = await screen.findByTestId("job-action-job-1");
  expect(action).toBeDisabled();
  expect(action).toHaveTextContent("I've Arrived");
  expect(screen.getByTestId("job-travel-wait-job-1")).toHaveTextContent("Available on the day of the job");
  fireEvent.click(action);
  expect(api.post).not.toHaveBeenCalled();
});

test("a non-owner dispatch login does not get Delete", async () => {
  mockAuth = { role: "technician", name: "Field" };
  mockGets([]);
  render(<Dashboard />);
  expect(await screen.findByTestId("job-card-job-1")).toBeInTheDocument();
  expect(screen.queryByTestId("job-delete-job-1")).not.toBeInTheDocument();
  expect(screen.queryByTestId("job-edit-job-1")).not.toBeInTheDocument();
  expect(screen.queryByTestId("closed-jobs-toggle")).not.toBeInTheDocument();
});

const attentionJob = {
  ...job,
  status: "complete",
  xero_draft_status: "needs_attention",
  xero_attention_reason: "Xero is not connected.",
  updated_at: "2026-11-17T16:00:00Z",
};

const draftedJob = {
  ...attentionJob,
  xero_draft_status: "draft",
  xero_invoice_number: "INV-9",
  xero_invoice_id: "inv-9",
  xero_attention_reason: null,
  updated_at: "2026-11-17T16:05:00Z",
};

test("Retry shows the new Xero draft even when the job list is still the old one", async () => {
  let jobsCalls = 0;
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) {
      jobsCalls += 1;
      if (jobsCalls === 1) return Promise.resolve({ data: [attentionJob] });
      return Promise.resolve({ data: [attentionJob] });
    }
    if (path.includes("/documents")) return Promise.resolve({ data: [] });
    if (path.includes("/dashboard/summary")) {
      return Promise.resolve({ data: { job_count: 1, revenue: 125, estimated_miles: 6, done_by: null, shop_emails_enabled: true } });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.post.mockResolvedValue({ data: { job: draftedJob } });

  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("xero-retry-job-1"));

  expect(await screen.findByTestId("xero-draft-job-1")).toHaveTextContent("Xero draft INV-9");
  expect(screen.queryByTestId("xero-attention-job-1")).not.toBeInTheDocument();
});

test("Complete shows the Xero draft from the response without waiting on a reload", async () => {
  mockGets([{ file_name: "scan.pdf", content_type: "application/pdf", size_bytes: 100 }]);
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [{ ...job, updated_at: "2026-11-17T16:00:00Z" }] });
    if (path.includes("/documents")) {
      return Promise.resolve({ data: [{ file_name: "scan.pdf", content_type: "application/pdf", size_bytes: 100 }] });
    }
    if (path.includes("/dashboard/summary")) {
      return Promise.resolve({ data: { job_count: 1, revenue: 125, estimated_miles: 6, done_by: null, shop_emails_enabled: true } });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.post.mockImplementation((url) => {
    if (String(url).endsWith("/complete")) {
      return Promise.resolve({
        data: {
          job: {
            ...job,
            status: "complete",
            xero_draft_status: "draft",
            xero_invoice_number: "INV-9",
            xero_invoice_id: "inv-9",
            updated_at: "2026-11-17T16:05:00Z",
          },
        },
      });
    }
    return Promise.resolve({ data: {} });
  });

  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("job-action-job-1"));
  expect(await screen.findByTestId("doc-uploaded")).toHaveTextContent("scan.pdf");
  fireEvent.change(screen.getByTestId("dash-cal-type-job-1"), { target: { value: "static" } });
  fireEvent.click(screen.getByTestId("dash-pop-none-job-1"));
  fireEvent.click(screen.getByTestId("dash-complete-job-1"));

  expect(await screen.findByTestId("xero-draft-job-1")).toHaveTextContent("Xero draft INV-9");
});

test("focusing the window refreshes a job's Xero badge", async () => {
  let listed = attentionJob;
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [listed] });
    if (path.includes("/documents")) return Promise.resolve({ data: [] });
    if (path.includes("/dashboard/summary")) {
      return Promise.resolve({ data: { job_count: 1, revenue: 125, estimated_miles: 6, done_by: null, shop_emails_enabled: true } });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });

  render(<Dashboard />);
  expect(await screen.findByTestId("xero-attention-job-1")).toBeInTheDocument();

  listed = draftedJob;
  fireEvent(window, new Event("focus"));

  expect(await screen.findByTestId("xero-draft-job-1")).toHaveTextContent("Xero draft INV-9");
});

const keepAlert = {
  id: "alert-keep",
  job_id: "job-keep",
  shop_name: "Keep Glass",
  vehicle: "2021 Ford F-150",
  scheduled_start: "2026-11-17T18:00:00Z",
  zone: "east",
};

function summaryGet() {
  return Promise.resolve({
    data: { job_count: 1, revenue: 125, estimated_miles: 6, done_by: null, shop_emails_enabled: true },
  });
}

test("declining a pending job drops it from the new-bookings count without a reload", async () => {
  const pending = {
    ...job,
    id: "job-pending",
    status: "requested",
    shop_name: "Pending Glass",
  };
  const pendingAlert = {
    id: "alert-pending",
    job_id: "job-pending",
    shop_name: "Pending Glass",
    vehicle: "2020 Honda Pilot",
    scheduled_start: pending.scheduled_start,
    zone: "west",
  };
  let declined = false;
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("closed=true")) return Promise.resolve({ data: [] });
    if (path.startsWith("/jobs?")) {
      return Promise.resolve({ data: [declined ? { ...pending, status: "declined" } : pending] });
    }
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) {
      return Promise.resolve({ data: { count: 2, alerts: [pendingAlert, keepAlert] } });
    }
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.post.mockImplementation((url) => {
    if (String(url).endsWith("/decline")) {
      declined = true;
      return Promise.resolve({ data: { ...pending, status: "declined" } });
    }
    return Promise.resolve({ data: {} });
  });

  render(<Dashboard />);
  expect(await screen.findByTestId("new-bookings-count")).toHaveTextContent("2");
  fireEvent.click(screen.getByTestId("job-decline-job-pending"));

  await waitFor(() => expect(screen.getByTestId("new-bookings-count")).toHaveTextContent("1"));
  expect(api.post).toHaveBeenCalledWith("/jobs/job-pending/decline");
  fireEvent.click(screen.getByTestId("new-bookings-pill"));
  expect(screen.getByTestId("new-bookings-panel")).toHaveTextContent("Keep Glass");
  expect(screen.getByTestId("new-bookings-panel")).not.toHaveTextContent("Pending Glass");
  expect(screen.queryByTestId("job-card-job-pending")).not.toBeInTheDocument();
});

test("cancelling a job drops it from the new-bookings count without a reload", async () => {
  const booked = { ...job, id: "job-booked", status: "booked", shop_name: "Booked Glass", shop_id: "shop-1" };
  const bookedAlert = {
    id: "alert-booked",
    job_id: "job-booked",
    shop_name: "Booked Glass",
    vehicle: "2020 Honda Pilot",
    scheduled_start: booked.scheduled_start,
    zone: "west",
  };
  let cancelled = false;
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("closed=true")) return Promise.resolve({ data: [] });
    if (path.startsWith("/jobs?")) {
      return Promise.resolve({ data: [cancelled ? { ...booked, status: "cancelled" } : booked] });
    }
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) {
      return Promise.resolve({ data: { count: 2, alerts: [bookedAlert, keepAlert] } });
    }
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.post.mockImplementation((url) => {
    if (String(url).endsWith("/cancel")) {
      cancelled = true;
      return Promise.resolve({ data: { ...booked, status: "cancelled" } });
    }
    return Promise.resolve({ data: {} });
  });

  render(<Dashboard />);
  expect(await screen.findByTestId("new-bookings-count")).toHaveTextContent("2");
  fireEvent.click(screen.getByTestId("job-cancel-job-booked"));
  fireEvent.click(await screen.findByTestId("modal-confirm"));

  await waitFor(() => expect(screen.getByTestId("new-bookings-count")).toHaveTextContent("1"));
  expect(api.post).toHaveBeenCalledWith("/jobs/job-booked/cancel", { reason: null });
  fireEvent.click(screen.getByTestId("new-bookings-pill"));
  expect(screen.getByTestId("new-bookings-panel")).not.toHaveTextContent("Booked Glass");
  expect(screen.getByTestId("new-bookings-panel")).toHaveTextContent("Keep Glass");
});

test("Cancelled & declined lists those jobs and Delete still asks before it removes one", async () => {
  const cancelledJob = {
    id: "job-cancelled",
    status: "cancelled",
    shop_name: "Star Windshield",
    vehicle_year: 2019,
    vehicle_make: "Honda",
    vehicle_model: "Civic",
    customer_first_name: "Casey",
    customer_last_name: "Lee",
    cancellation_reason: "Customer requested",
    scheduled_start: "2026-11-16T16:00:00Z",
    price: 125,
  };
  const declinedJob = {
    id: "job-declined",
    status: "declined",
    shop_name: "Jarvis Glass",
    vehicle_year: 2022,
    vehicle_make: "Toyota",
    vehicle_model: "Camry",
    customer_first_name: "Ben",
    customer_last_name: "Ng",
    scheduled_start: "2026-11-17T17:00:00Z",
    price: 175,
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("closed=true")) return Promise.resolve({ data: [cancelledJob, declinedJob] });
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [job] });
    if (path.includes("/documents")) return Promise.resolve({ data: [] });
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.delete.mockResolvedValue({ data: { deleted: true, id: "job-declined" } });

  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("closed-jobs-toggle"));

  const declinedRow = await screen.findByTestId("closed-job-job-declined");
  expect(declinedRow).toHaveTextContent("Jarvis Glass");
  expect(declinedRow).toHaveTextContent("2022 Toyota Camry");
  expect(declinedRow).toHaveTextContent("Ben Ng");
  expect(declinedRow).toHaveTextContent("Declined");
  expect(declinedRow).toHaveTextContent("Tue, Nov 17");
  expect(screen.getByTestId("closed-reason-job-declined")).toHaveTextContent("—");

  const cancelledRow = screen.getByTestId("closed-job-job-cancelled");
  expect(cancelledRow).toHaveTextContent("Star Windshield");
  expect(cancelledRow).toHaveTextContent("2019 Honda Civic");
  expect(cancelledRow).toHaveTextContent("Casey Lee");
  expect(cancelledRow).toHaveTextContent("Cancelled");
  expect(screen.getByTestId("closed-reason-job-cancelled")).toHaveTextContent("Customer requested");

  fireEvent.click(screen.getByTestId("job-delete-job-declined"));
  expect(await screen.findByTestId("job-delete-dialog")).toHaveTextContent("Yes, delete");
  expect(api.delete).not.toHaveBeenCalled();
  const getsBefore = api.get.mock.calls.length;
  fireEvent.click(screen.getByTestId("job-delete-confirm"));

  await waitFor(() => expect(screen.queryByTestId("closed-job-job-declined")).not.toBeInTheDocument());
  expect(screen.getByTestId("closed-job-job-cancelled")).toBeInTheDocument();
  expect(api.delete).toHaveBeenCalledWith("/jobs/job-declined");
  expect(api.get.mock.calls.length).toBe(getsBefore);
});

test("a shop cancellation shows Cancelled by shop", async () => {
  const shopCancelled = {
    id: "job-shop-cancelled",
    status: "cancelled",
    shop_name: "Test Shop",
    vehicle_year: 2021,
    vehicle_make: "Ford",
    vehicle_model: "F-150",
    customer_first_name: "Riley",
    customer_last_name: "Nguyen",
    cancellation_reason: "Cancelled by shop",
    scheduled_start: "2026-11-25T16:00:00Z",
    price: 125,
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("closed=true")) return Promise.resolve({ data: [shopCancelled] });
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [] });
    if (path.includes("/documents")) return Promise.resolve({ data: [] });
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });

  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("closed-jobs-toggle"));
  expect(await screen.findByTestId("closed-reason-job-shop-cancelled")).toHaveTextContent("Cancelled by shop");
  expect(screen.getByTestId("closed-job-job-shop-cancelled")).toHaveTextContent("Cancelled");
});

test("dispatch shows a free warranty redo and does not offer a card charge", async () => {
  mockGets([], {
    ...job,
    status: "complete",
    price: 0,
    payment_status: "not_charged",
    warranty_of_job_id: "orig-1",
    warranty_eligible: true,
    warranty_label: "Warranty redo (free)",
  });
  render(<Dashboard />);
  expect(await screen.findByTestId("warranty-badge-job-1")).toHaveTextContent("Warranty redo (free)");
  expect(screen.queryByTestId("job-charge-job-1")).not.toBeInTheDocument();
});

test("dispatch shows a redo that is past the 30-day warranty", async () => {
  mockGets([], {
    ...job,
    warranty_of_job_id: "orig-1",
    warranty_eligible: false,
    warranty_label: "Past 30-day warranty — billed normally",
  });
  render(<Dashboard />);
  expect(await screen.findByTestId("warranty-badge-job-1")).toHaveTextContent(
    "Past 30-day warranty — billed normally",
  );
});

test("a paid charge shows the amount and time and hides Charge card now", async () => {
  mockGets([], {
    ...job,
    status: "complete",
    payment_mode: "charge_on_completion",
    payment_status: "paid",
    charged_at: "2026-11-18T16:05:00Z",
    charged_amount: 125,
    updated_at: "2026-11-18T16:05:00Z",
  });
  render(<Dashboard />);
  expect(await screen.findByTestId("job-paid-job-1")).toHaveTextContent("Paid $125.00 · 9:00 AM");
  expect(screen.queryByTestId("job-charge-job-1")).not.toBeInTheDocument();
});

test("a paid invoice-hold job hides the hold badge and Charge card now", async () => {
  mockGets([], {
    ...job,
    status: "complete",
    payment_mode: "invoice_hold",
    payment_status: "paid",
    charged_at: "2026-11-18T16:05:00Z",
    charged_amount: 185.5,
    invoice_id: "in_1",
    updated_at: "2026-11-18T16:05:00Z",
  });
  render(<Dashboard />);
  expect(await screen.findByTestId("job-paid-job-1")).toHaveTextContent("Paid $185.50 · 9:00 AM");
  expect(screen.queryByText("Invoice — hold charge")).not.toBeInTheDocument();
  expect(screen.queryByTestId("job-charge-job-1")).not.toBeInTheDocument();
});

test("new bookings show the current time and status, not an older booking time", async () => {
  const moved = {
    id: "alert-moved",
    job_id: "job-moved",
    shop_name: "Preferred Auto Glass",
    vehicle: "2020 Honda Civic",
    scheduled_start: "2099-06-02T15:30:00Z",
    original_scheduled_start: "2099-06-02T08:00:00Z",
    status: "requested",
    status_label: "Pending approval",
    zone: "east",
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [] });
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 1, alerts: [moved] } });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });

  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("new-bookings-pill"));
  expect(screen.getByTestId("new-booking-time-job-moved")).toHaveTextContent("T15:30");
  expect(screen.getByTestId("new-booking-status-job-moved")).toHaveTextContent("Pending approval");
  expect(screen.getByTestId("new-bookings-panel")).not.toHaveTextContent("T08:00");
});

test("held shop mail uses plain words and still opens the held-email list", async () => {
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [] });
    if (path.includes("/dashboard/summary")) {
      return Promise.resolve({ data: { job_count: 0, revenue: 0, estimated_miles: 0, done_by: null, shop_emails_enabled: false } });
    }
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });

  render(<Dashboard />);
  const link = await screen.findByTestId("shop-emails-off");
  expect(link).toHaveTextContent("Shop emails are on hold — view held emails");
  expect(link).toHaveAttribute("href", "/settings?section=email");
  expect(screen.queryByText(/OFF \(testing\)/)).not.toBeInTheDocument();
});

test("the held-mail link stays hidden while shop emails are sending", async () => {
  mockGets([]);
  render(<Dashboard />);
  await screen.findByTestId("today-btn");
  expect(screen.queryByTestId("shop-emails-off")).not.toBeInTheDocument();
});

test("a shop job link opens Dispatch on that job's day", async () => {
  window.history.pushState({}, "", "/dashboard?date=2099-04-04&job=job-1");
  mockGets([]);
  render(<Dashboard />);
  await screen.findByTestId("today-btn");
  expect(api.get).toHaveBeenCalledWith("/jobs?date_str=2099-04-04");
  window.history.pushState({}, "", "/");
});

test("Charge card now keeps the paid job when the day list is still unpaid", async () => {
  const unpaid = {
    ...job,
    status: "complete",
    payment_mode: "invoice_hold",
    payment_status: "unpaid",
    invoice_status: "open",
    invoice_id: "in_1",
    updated_at: "2026-11-18T16:00:00Z",
  };
  const paid = {
    ...unpaid,
    payment_status: "paid",
    invoice_status: "paid",
    charged_at: "2026-11-18T16:05:00Z",
    charged_amount: 125,
    updated_at: "2026-11-18T16:05:00Z",
  };
  mockGets([], unpaid);
  api.post.mockImplementation((url) => {
    if (String(url).endsWith("/charge-card")) return Promise.resolve({ data: { job: paid } });
    return Promise.resolve({ data: {} });
  });
  render(<Dashboard />);
  expect(await screen.findByText("Invoice — hold charge")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("job-charge-job-1"));
  expect(await screen.findByTestId("job-paid-job-1")).toHaveTextContent("Paid $125.00 · 9:00 AM");
  expect(screen.queryByText("Invoice — hold charge")).not.toBeInTheDocument();
  expect(screen.queryByTestId("job-charge-job-1")).not.toBeInTheDocument();
});

test("the desk card shows one next action and keeps the rest under More", async () => {
  mockGets([], { ...job, status: "booked", scheduled_start: "2026-11-18T02:00:00Z" });
  render(<Dashboard />);
  const card = await screen.findByTestId("job-card-job-1");
  const next = card.querySelector(".job-next");
  expect(next).toHaveTextContent("Start Driving");
  expect(next).toHaveTextContent("Open on the phone");
  expect(next).not.toHaveTextContent("Delete");
  expect(next).not.toHaveTextContent("Reschedule");
  expect(next).not.toHaveTextContent("Cancel");
  expect(screen.getByTestId("job-phone-job-1")).toHaveAttribute("href", "/field?job=job-1");
  const more = screen.getByTestId("job-more-job-1");
  expect(more).toHaveTextContent("Delete");
  expect(more).toHaveTextContent("Reschedule");
  expect(more).toHaveTextContent("Cancel");
  expect(more).toHaveTextContent("More");
});

test("a failed next action stays on the board instead of a browser alert", async () => {
  window.alert = jest.fn();
  mockGets([], { ...job, status: "booked", scheduled_start: "2026-11-18T02:00:00Z" });
  api.post.mockRejectedValue({ response: { data: { detail: "Not today." } } });
  render(<Dashboard />);
  fireEvent.click(await screen.findByTestId("job-action-job-1"));
  expect(await screen.findByTestId("board-notice")).toHaveTextContent("Not today.");
  expect(window.alert).not.toHaveBeenCalled();
});

test("a deep link shows the job when it is assigned to someone else", async () => {
  window.history.pushState({}, "", "/dashboard?date=2026-11-13&job=job-glass");
  const glass = {
    ...job,
    id: "job-glass",
    status: "booked",
    shop_name: "Preferred Auto Glass",
    scheduled_start: "2026-11-13T21:00:00+00:00",
    technician_id: "not-on-the-board",
    price: 150,
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [glass] });
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) {
      return Promise.resolve({ data: [{ id: "caleb", name: "Caleb", role: "owner", routes_jobs: true, is_active: true }] });
    }
    return Promise.resolve({ data: [] });
  });
  const scroll = jest.fn();
  window.HTMLElement.prototype.scrollIntoView = scroll;

  render(<Dashboard />);
  const card = await screen.findByTestId("job-card-job-glass");
  expect(card).toHaveTextContent("Preferred Auto Glass");
  expect(card).toHaveClass("card-job-focus");
  expect(screen.queryByText("No jobs for this technician yet")).not.toBeInTheDocument();
  expect(screen.queryByText("No jobs on this day")).not.toBeInTheDocument();
  await waitFor(() => expect(scroll).toHaveBeenCalled());
});

test("a deep link rings an at-risk card without replacing the risk border", async () => {
  window.history.pushState({}, "", "/dashboard?date=2026-11-13&job=job-glass");
  const glass = {
    ...job,
    id: "job-glass",
    status: "booked",
    shop_name: "Preferred Auto Glass",
    scheduled_start: "2026-11-13T21:00:00+00:00",
    is_at_risk: true,
    risk_reason: "Running late",
    price: 150,
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [glass] });
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });

  render(<Dashboard />);
  const card = await screen.findByTestId("job-card-job-glass");
  expect(card).toHaveClass("card-job-focus");
  expect(card).toHaveClass("card-job-at-risk");
  expect(screen.getByTestId("badge-at-risk-job-glass")).toBeInTheDocument();
});

test("a deep link still shows the job when the day list missed it", async () => {
  window.history.pushState({}, "", "/dashboard?date=2026-11-14&job=job-glass");
  const glass = {
    ...job,
    id: "job-glass",
    status: "booked",
    shop_name: "Preferred Auto Glass",
    scheduled_start: "2026-11-13T21:00:00+00:00",
    technician_id: "not-on-the-board",
    price: 150,
  };
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [] });
    if (path === "/jobs/job-glass") return Promise.resolve({ data: glass });
    if (path.includes("/dashboard/summary")) return summaryGet();
    if (path.includes("/notifications")) return Promise.resolve({ data: { count: 0, alerts: [] } });
    if (path.includes("/routing-techs")) {
      return Promise.resolve({ data: [{ id: "caleb", name: "Caleb", role: "owner", routes_jobs: true, is_active: true }] });
    }
    return Promise.resolve({ data: [] });
  });

  render(<Dashboard />);
  expect(await screen.findByTestId("job-card-job-glass")).toHaveTextContent("Preferred Auto Glass");
  expect(screen.queryByText("No jobs for this technician yet")).not.toBeInTheDocument();
  expect(screen.queryByText("No jobs on this day")).not.toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith("/jobs?date_str=2026-11-13");
  expect(api.get).toHaveBeenCalledWith("/jobs/job-glass");
});
