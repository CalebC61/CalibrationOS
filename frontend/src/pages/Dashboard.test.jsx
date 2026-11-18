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
jest.mock("../components/RescheduleCancelModal", () => () => null);
jest.mock("../components/TomorrowStrip", () => () => null);
jest.mock("../components/JobEditModal", () => () => null);

jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
  formatTime: () => "9:00 AM",
  formatDate: () => "Tue, Nov 17",
  phoenixTodayStr: () => "2026-11-17",
  dateStr: () => "2026-11-17",
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
});
