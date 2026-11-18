import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("../lib/api", () => ({
  api: { get: jest.fn() },
}));

import Invoices from "./Invoices";
import { api } from "../lib/api";

test("focusing the window refreshes the Xero invoice badge", async () => {
  let status = "NEEDS_ATTENTION";
  api.get.mockImplementation((url) => {
    if (String(url).includes("/invoices")) {
      return Promise.resolve({
        data: [{
          invoice_id: "INV-9",
          contact_name: "Star Windshield",
          status,
          total: 185,
          created_at: "2026-11-17T16:00:00Z",
        }],
      });
    }
    return Promise.resolve({ data: { events: [] } });
  });

  render(<Invoices />);
  expect(await screen.findByTestId("invoice-INV-9")).toHaveTextContent("NEEDS_ATTENTION");

  status = "DRAFT";
  fireEvent(window, new Event("focus"));

  await waitFor(() => expect(screen.getByTestId("invoice-INV-9")).toHaveTextContent("DRAFT"));
});

test("the invoice list shows paid and open with the due date", async () => {
  api.get.mockImplementation((url) => {
    if (String(url).includes("/invoices")) {
      return Promise.resolve({
        data: [
          {
            invoice_id: "in_paid",
            contact_name: "Star Windshield",
            status: "paid",
            total: 185,
            created_at: "2026-11-18T16:00:00Z",
            due_at: "2026-11-25",
          },
          {
            invoice_id: "in_open",
            contact_name: "Jarvis Glass",
            status: "open",
            total: 125,
            created_at: "2026-11-18T17:00:00Z",
            due_at: "2026-11-25",
          },
        ],
      });
    }
    return Promise.resolve({ data: { events: [] } });
  });

  render(<Invoices />);
  expect(await screen.findByTestId("invoice-in_paid")).toHaveTextContent("Paid");
  expect(screen.getByTestId("invoice-in_paid")).toHaveTextContent("Nov 25, 2026");
  expect(screen.getByTestId("invoice-in_open")).toHaveTextContent("Open");
  expect(screen.getByTestId("invoice-in_open")).toHaveTextContent("Nov 25, 2026");
});
