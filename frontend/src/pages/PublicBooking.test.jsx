import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("react-router-dom", () => ({
  useParams: () => ({ token: "tok" }),
}), { virtual: true });

jest.mock("../components/Brand", () => () => <div>Brand</div>);
jest.mock("../components/JobEditModal", () => () => null);

jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn() },
  formatTime: () => "9:00 AM",
  formatDate: () => "Nov 18",
  getStoredAuth: () => null,
  jobStatusLabel: (status) => status || "",
  phoenixTodayStr: (instant) => (instant ? "2026-12-09" : "2026-11-18"),
}));

import PublicBooking from "./PublicBooking";
import { api } from "../lib/api";

const preferred = {
  name: "Preferred Auto Glass",
  address: "1 Shop St, Phoenix, AZ",
  contact_phone: "4805550100",
  booking_open: true,
  prices: { static: 115, dynamic: 75, dual: 165, triple: 165, tesla: 215 },
};

test("the public date step renders and the quote uses the shop wholesale card", async () => {
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/public/shop/")) return Promise.resolve({ data: preferred });
    if (path.includes("/public/bookings/")) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  api.post.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/geocode")) return Promise.resolve({ data: { in_metro: true } });
    if (path.includes("/public/availability")) {
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T16:00:00Z" }] } });
    }
    return Promise.resolve({ data: {} });
  });

  render(<PublicBooking />);
  expect(await screen.findByText("Preferred Auto Glass")).toBeInTheDocument();

  fireEvent.blur(screen.getByTestId("booking-address"));
  await waitFor(() => expect(screen.getByTestId("address-next")).not.toBeDisabled());
  fireEvent.click(screen.getByTestId("address-next"));

  const date = screen.getByTestId("booking-date");
  expect(date).toHaveAttribute("min", "2026-11-18");
  expect(date).toHaveAttribute("max", "2026-12-09");

  fireEvent.change(date, { target: { value: "2026-11-18" } });
  fireEvent.click(await screen.findByTestId("slot-2026-11-18T16:00:00Z"));
  fireEvent.click(screen.getByTestId("step-next"));

  fireEvent.change(screen.getByTestId("vehicle-lastname"), { target: { value: "Ng" } });
  fireEvent.change(screen.getByTestId("vehicle-make"), { target: { value: "Honda" } });
  fireEvent.change(screen.getByTestId("vehicle-model"), { target: { value: "Civic" } });
  fireEvent.click(screen.getByTestId("step-next"));

  expect(screen.getByTestId("cal-type-dynamic")).toHaveTextContent("$75.00");
  expect(screen.getByTestId("cal-type-static")).toHaveTextContent("$115.00");
  expect(screen.getByTestId("cal-type-dual")).toHaveTextContent("$165.00");
});
