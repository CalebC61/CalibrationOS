import { fireEvent, render, screen, waitFor } from "@testing-library/react";

var mockAuth = { role: "owner", name: "Caleb" };

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
  };
}, { virtual: true });

jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("../components/DispatchModal", () => () => null);
jest.mock("../components/RouteMap", () => () => null);
jest.mock("../components/TomorrowStrip", () => () => null);
jest.mock("../components/JobEditModal", () => () => null);

jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
  formatTime: () => "9:00 AM",
  formatDate: () => "Tue, Nov 17",
  phoenixTodayStr: () => "2026-11-17",
  dateStr: () => "2026-11-17",
  todayStr: () => "2026-11-17",
  getStoredAuth: () => mockAuth,
  isOnDayBoard: (job) => job?.status !== "cancelled" && job?.status !== "declined",
  jobStatusLabel: (status) => status || "",
}));

import Dashboard from "./Dashboard";
import { api } from "../lib/api";

afterEach(() => {
  mockAuth = { role: "owner", name: "Caleb" };
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
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
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
