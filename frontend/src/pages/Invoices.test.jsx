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
