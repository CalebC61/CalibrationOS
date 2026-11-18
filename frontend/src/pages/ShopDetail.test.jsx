import { render, screen } from "@testing-library/react";

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
    useParams: () => ({ id: "shop-1" }),
  };
}, { virtual: true });

jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), put: jest.fn() },
  formatDate: (iso) => `date:${iso}`,
  formatTime: (iso) => `time:${iso}`,
}));

import ShopDetail from "./ShopDetail";
import { api } from "../lib/api";

const readyShop = {
  id: "shop-1",
  name: "Preferred Auto Glass",
  zone: "east",
  status: "active",
  address: "Gilbert, AZ",
  pricing_tier: "standard",
  wholesale_schedule: "auto",
  rate_label: "Preferred: $115 / $75 / $165",
  card_on_file: {
    brand: "visa",
    last4: "4242",
    exp_month: 12,
    exp_year: 2099,
    state: "Active",
    charge_terms_accepted: true,
    can_book: true,
    book_block: null,
  },
  jobs: {
    upcoming: [{
      id: "job-next",
      scheduled_start: "2026-11-19T17:00:00+00:00",
      board_date: "2026-11-19",
      status: "requested",
      status_label: "Pending approval",
      vehicle: "2020 Honda Civic",
      price: 115,
      calibration_label: "Static ADAS Calibration",
    }],
    recent: [{
      id: "job-done",
      scheduled_start: "2026-11-10T17:00:00+00:00",
      board_date: "2026-11-10",
      status: "complete",
      status_label: "Complete",
      vehicle: "2019 Toyota Camry",
      price: 165,
    }],
  },
};

test("the shop page lists jobs, the card on file, and that the shop can book", async () => {
  api.get.mockResolvedValue({ data: readyShop });
  render(<ShopDetail />);

  expect(await screen.findByTestId("shop-rate-label")).toHaveTextContent("Preferred: $115 / $75 / $165");
  expect(screen.getByTestId("shop-card-summary")).toHaveTextContent("Visa ending 4242, expires 12/2099");
  expect(screen.getByTestId("shop-card-state")).toHaveTextContent("Active");
  expect(screen.getByTestId("shop-card-terms")).toHaveTextContent("Charge terms accepted");
  expect(screen.getByTestId("shop-can-book")).toHaveTextContent("This shop can book right now.");

  const upcoming = screen.getByTestId("shop-job-job-next");
  expect(upcoming).toHaveTextContent("2020 Honda Civic");
  expect(upcoming).toHaveTextContent("Pending approval");
  expect(upcoming).toHaveTextContent("$115.00");
  expect(upcoming).toHaveTextContent("date:2026-11-19T17:00:00+00:00");
  expect(upcoming).toHaveTextContent("time:2026-11-19T17:00:00+00:00");
  expect(upcoming).toHaveAttribute("href", "/dashboard?date=2026-11-19&job=job-next");

  expect(screen.getByTestId("shop-job-job-done")).toHaveTextContent("2019 Toyota Camry");
  expect(screen.getByTestId("shop-job-job-done")).toHaveTextContent("Complete");
  expect(screen.getByTestId("shop-job-job-done")).toHaveAttribute("href", "/dashboard?date=2026-11-10&job=job-done");
});

test("a shop with no card shows why it cannot book", async () => {
  api.get.mockResolvedValue({ data: {
    ...readyShop,
    card_on_file: {
      brand: null,
      last4: null,
      exp_month: null,
      exp_year: null,
      state: "None",
      charge_terms_accepted: false,
      can_book: false,
      book_block: "Add a card in Settings before booking. A shop needs a valid card on file.",
    },
    jobs: { upcoming: [], recent: [] },
  } });
  render(<ShopDetail />);

  expect(await screen.findByTestId("shop-card-state")).toHaveTextContent("None");
  expect(screen.getByTestId("shop-card-summary")).toHaveTextContent("No card on file");
  expect(screen.getByTestId("shop-card-terms")).toHaveTextContent("Charge terms not accepted");
  expect(screen.getByTestId("shop-can-book")).toHaveTextContent("Add a card in Settings before booking.");
  expect(screen.getByTestId("shop-jobs-upcoming")).toHaveTextContent("No upcoming jobs.");
  expect(screen.getByTestId("shop-jobs-recent")).toHaveTextContent("No recent jobs.");
});
