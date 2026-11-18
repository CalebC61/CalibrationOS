import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock("../components/PortalShell", () => ({ children }) => <div>{children}</div>);

jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn(), post: jest.fn() },
}));

jest.mock("../lib/api", () => ({
  phoenixTodayStr: (instant) => (instant ? "2026-12-09" : "2026-11-18"),
}));

import PortalBook from "./PortalBook";
import { portalApi } from "../lib/portalApi";

const shop = {
  name: "Jarvis Glass",
  address: "100 W Main, Gilbert, AZ",
  formatted_address: "100 W Main, Gilbert, AZ",
  contact_phone: "4805550100",
  prices: { static: 125, dynamic: 125, dual: 175, triple: 185, tesla: 225 },
};

beforeEach(() => {
  portalApi.get.mockImplementation((url) => {
    if (String(url).includes("/portal/me")) {
      return Promise.resolve({ data: { shop, setup: { allowed: true } } });
    }
    return Promise.resolve({ data: {} });
  });
  portalApi.post.mockImplementation((url) => {
    if (String(url).includes("/geocode")) return Promise.resolve({ data: { in_metro: true } });
    if (String(url).includes("/portal/availability")) {
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T16:00:00Z", requires_approval: false }] } });
    }
    return Promise.resolve({ data: {} });
  });
});

test("a changed address is checked while typing, before the field loses focus", async () => {
  render(<PortalBook />);
  const address = await screen.findByTestId("b-addr");
  expect(screen.getByTestId("b-date")).not.toBeDisabled();

  fireEvent.change(address, { target: { value: "200 Other St, Mesa, AZ" } });
  expect(screen.getByTestId("b-date")).toBeDisabled();

  await waitFor(() => expect(screen.getByTestId("b-date")).not.toBeDisabled());
  expect(portalApi.post).toHaveBeenCalledWith("/geocode", { address: "200 Other St, Mesa, AZ" });

  fireEvent.change(screen.getByTestId("b-date"), { target: { value: "2026-11-18" } });
  fireEvent.click(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z"));
  expect(screen.getByTestId("b-next")).not.toBeDisabled();
});

test("a redo of a past job is optional and is sent with that job", async () => {
  portalApi.get.mockImplementation((url) => {
    if (String(url).includes("/portal/me")) {
      return Promise.resolve({ data: { shop, setup: { allowed: true } } });
    }
    if (String(url).includes("/portal/warranty-jobs")) {
      return Promise.resolve({ data: [{
        id: "old-1",
        vehicle: "2020 Honda Civic",
        customer: "Ana Ng",
        completed_on: "2026-11-01",
        warranty_through: "2026-12-09",
      }] });
    }
    return Promise.resolve({ data: [] });
  });
  portalApi.post.mockImplementation((url) => {
    if (String(url).includes("/portal/availability")) {
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T16:00:00Z", requires_approval: false }] } });
    }
    if (String(url).includes("/portal/book")) {
      return Promise.resolve({ data: {
        job_id: "new-1",
        booking_reference: "ABCD1234",
        status: "booked",
        price: 0,
        warranty_label: "Warranty redo (free)",
      } });
    }
    return Promise.resolve({ data: {} });
  });

  render(<PortalBook />);
  fireEvent.change(await screen.findByTestId("b-date"), { target: { value: "2026-11-18" } });
  fireEvent.click(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z"));
  fireEvent.click(screen.getByTestId("b-next"));

  const choice = screen.getByTestId("warranty-redo");
  expect(choice).not.toBeChecked();
  fireEvent.click(choice);
  expect(await screen.findByRole("option", { name: /2020 Honda Civic · Ana Ng · Nov 1, 2026/ })).toBeInTheDocument();
  fireEvent.change(screen.getByTestId("warranty-of"), { target: { value: "old-1" } });
  expect(screen.getByTestId("warranty-preview")).toHaveTextContent("Warranty redo (free)");

  fireEvent.change(screen.getByTestId("b-ln"), { target: { value: "Ng" } });
  fireEvent.change(screen.getByTestId("b-make"), { target: { value: "Honda" } });
  fireEvent.change(screen.getByTestId("b-model"), { target: { value: "Civic" } });
  fireEvent.click(screen.getByTestId("b-next"));

  await waitFor(() => expect(portalApi.post).toHaveBeenCalledWith("/portal/book", expect.objectContaining({
    warranty_of_job_id: "old-1",
    customer_last_name: "Ng",
  })));
  expect(await screen.findByTestId("portal-warranty-label")).toHaveTextContent("Warranty redo (free)");
  expect(screen.getByTestId("portal-confirm-price")).toHaveTextContent("$0.00");
});
