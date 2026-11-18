import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock("../components/JobEditModal", () => () => null);

jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn() },
  formatTime: () => "9:00 AM",
  formatDate: () => "Tue, Nov 17",
  getStoredAuth: () => ({ role: "owner", name: "Caleb" }),
  setStoredAuth: jest.fn(),
  todayStr: () => "2026-11-17",
  phoenixTodayStr: () => "2026-11-17",
  isPhoenixToday: () => true,
  isOnDayBoard: (job) => job?.status !== "cancelled" && job?.status !== "declined",
  jobStatusLabel: (status) => status || "",
}));

import Field from "./Field";
import { api } from "../lib/api";

const attentionJob = {
  id: "job-1",
  status: "complete",
  scheduled_start: "2026-11-17T16:00:00Z",
  shop_name: "Star Windshield",
  vehicle_year: 2020,
  vehicle_make: "Honda",
  vehicle_model: "Pilot",
  calibration_label: "Static",
  job_address: "1 Main St",
  price: 125,
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

function mockList(listed) {
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [listed] });
    if (path.includes("/documents")) return Promise.resolve({ data: [] });
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
}

test("Retry on the field job shows the new draft when the list is still old", async () => {
  mockList(attentionJob);
  api.post.mockResolvedValue({ data: { job: draftedJob } });
  render(<Field />);

  fireEvent.click(await screen.findByTestId("field-job-job-1"));
  fireEvent.click(await screen.findByTestId("retry-xero-draft"));

  await waitFor(() => expect(document.body.textContent).toContain("Draft INV-9 created"));
  expect(screen.queryByTestId("retry-xero-draft")).not.toBeInTheDocument();
});

test("focusing the window refreshes the field Xero outcome", async () => {
  let listed = attentionJob;
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.startsWith("/jobs?")) return Promise.resolve({ data: [listed] });
    if (path.includes("/documents")) return Promise.resolve({ data: [] });
    if (path.includes("/contractor-offers")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  render(<Field />);
  fireEvent.click(await screen.findByTestId("field-job-job-1"));
  expect(await screen.findByText(/needs attention/)).toBeInTheDocument();

  listed = draftedJob;
  fireEvent(window, new Event("focus"));

  await waitFor(() => expect(document.body.textContent).toContain("Draft INV-9 created"));
});

test("the complete confirmation says when the card was paid", async () => {
  mockList({
    ...draftedJob,
    payment_status: "paid",
    charged_at: "2026-11-18T16:05:00Z",
    charged_amount: 185,
  });
  render(<Field />);
  fireEvent.click(await screen.findByTestId("field-job-job-1"));
  expect(await screen.findByTestId("payment-status-line")).toHaveTextContent("Paid $185.00");
  expect(screen.getByTestId("xero-draft-status")).toHaveTextContent("Draft INV-9 created");
});

test("the complete confirmation shows an invoice due date", async () => {
  mockList({
    ...draftedJob,
    payment_mode: "invoice_hold",
    payment_status: "unpaid",
    invoice_id: "in_1",
    invoice_status: "open",
    invoice_due_at: "2026-11-25",
  });
  render(<Field />);
  fireEvent.click(await screen.findByTestId("field-job-job-1"));
  expect(await screen.findByTestId("payment-status-line")).toHaveTextContent("Invoiced, due Nov 25, 2026");
});

test("the complete confirmation says when the charge failed", async () => {
  mockList({
    ...attentionJob,
    payment_status: "payment_failed",
    charge_error: "Card declined.",
  });
  render(<Field />);
  fireEvent.click(await screen.findByTestId("field-job-job-1"));
  expect(await screen.findByTestId("payment-status-line")).toHaveTextContent("Charge failed");
  expect(screen.getByTestId("xero-draft-status")).toHaveTextContent("needs attention");
});

test("a free warranty redo shows its badge and does not offer a Xero retry", async () => {
  mockList({
    ...attentionJob,
    warranty_of_job_id: "orig-1",
    warranty_eligible: true,
    warranty_label: "Warranty redo (free)",
    warranty_skip_reason: "Warranty redo (free). The redo is within 30 days of the original completion, so no Xero draft is filed and the card is not charged.",
    xero_draft_status: "skipped",
    xero_attention_reason: null,
    price: 0,
  });
  render(<Field />);
  fireEvent.click(await screen.findByTestId("field-job-job-1"));
  expect(await screen.findByTestId("warranty-badge-job-1")).toHaveTextContent("Warranty redo (free)");
  expect(screen.getByTestId("xero-draft-status")).toHaveTextContent("no Xero draft is filed");
  expect(screen.queryByTestId("retry-xero-draft")).not.toBeInTheDocument();
});
