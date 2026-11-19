import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { resetPlacesLoader } from "../components/AddressField";

const mockRouter = { nav: jest.fn() };

jest.mock("react-router-dom", () => ({
  useParams: () => ({ id: "shop-1" }),
  useNavigate: () => mockRouter.nav,
}), { virtual: true });

jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("../components/PortalShell", () => ({ children }) => <div>{children}</div>);

jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn(), post: jest.fn() },
  getPortalAuth: () => null,
  setPortalAuth: jest.fn(),
}));

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

beforeEach(() => {
  resetPlacesLoader();
  delete window.google;
  delete process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
  mockRouter.nav.mockReset();
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path === "/shops") {
      return Promise.resolve({ data: [
        { id: "shop-1", name: "Preferred Auto Glass" },
        { id: "shop-2", name: "Jarvis Glass" },
      ] });
    }
    if (path.includes("/shops/")) return Promise.resolve({ data: { ...preferred, id: "shop-1" } });
    return Promise.resolve({ data: [] });
  });
  api.post.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/geocode")) return Promise.resolve({ data: { in_metro: true } });
    if (path.includes("/availability")) {
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T16:00:00Z", requires_approval: false }] } });
    }
    return Promise.resolve({ data: {} });
  });
});

async function reachVehicle() {
  render(<PublicBooking />);
  const date = await screen.findByTestId("b-date");
  expect(date).not.toBeDisabled();
  expect(date).toHaveAttribute("min", "2026-11-18");
  expect(date).toHaveAttribute("max", "2026-12-09");
  fireEvent.change(date, { target: { value: "2026-11-18" } });
  fireEvent.click(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z"));
  fireEvent.click(screen.getByTestId("b-next"));
}

test("the owner books on the shop form and the quote uses the shop wholesale card", async () => {
  await reachVehicle();
  expect(screen.getByTestId("owner-shop")).toHaveValue("shop-1");
  expect(screen.getByRole("option", { name: "Preferred Auto Glass" })).toBeInTheDocument();
  expect(await screen.findByRole("option", { name: "Jarvis Glass" })).toBeInTheDocument();
  expect(screen.getByTestId("cal-type-dynamic")).toHaveTextContent("$75.00");
  expect(screen.getByTestId("cal-type-static")).toHaveTextContent("$115.00");
  expect(screen.getByTestId("cal-type-dual")).toHaveTextContent("$165.00");
  expect(screen.queryByText(/invoice me/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/until the owner approves/i)).not.toBeInTheDocument();
  expect(screen.queryByTestId("warranty-redo")).not.toBeInTheDocument();
  expect(screen.getByText("The card on file is charged when the job is completed.")).toBeInTheDocument();
});

test("the owner can type a time and is not asked to invoice or wait for approval", async () => {
  api.post.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/availability")) {
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T14:00:00Z", requires_approval: true }] } });
    }
    if (path.includes("/book")) {
      return Promise.resolve({ data: {
        booking_reference: "ABCD1234",
        status: "requested",
        requires_approval: true,
        price: 115,
        scheduled_start: "2026-11-18T14:15:00.000Z",
      } });
    }
    return Promise.resolve({ data: {} });
  });

  render(<PublicBooking />);
  const date = await screen.findByTestId("b-date");
  fireEvent.change(date, { target: { value: "2026-11-18" } });
  const slot = await screen.findByTestId("b-slot-2026-11-18T14:00:00Z");
  expect(slot).toHaveTextContent("Pending approval");
  fireEvent.change(screen.getByTestId("owner-custom-time"), { target: { value: "07:15" } });
  expect(screen.getByTestId("b-next")).not.toBeDisabled();
  fireEvent.click(screen.getByTestId("b-next"));

  expect(screen.queryByText(/until the owner approves/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/invoice me/i)).not.toBeInTheDocument();
  expect(screen.getByTestId("b-next")).toHaveTextContent("Confirm Booking");

  fireEvent.change(screen.getByTestId("b-ln"), { target: { value: "Ng" } });
  fireEvent.change(screen.getByTestId("b-make"), { target: { value: "Honda" } });
  fireEvent.change(screen.getByTestId("b-model"), { target: { value: "Civic" } });
  fireEvent.click(screen.getByTestId("b-next"));

  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/shops/shop-1/book", expect.objectContaining({
    scheduled_start: "2026-11-18T14:15:00.000Z",
    invoice_instead: false,
    customer_last_name: "Ng",
    job_address: preferred.address,
    calibration_type: "static",
  })));
  const body = api.post.mock.calls.find((call) => call[0] === "/shops/shop-1/book")[1];
  expect(body.warranty_of_job_id).toBeUndefined();
  expect(await screen.findByTestId("booking-confirmed")).toHaveTextContent("Pending approval");
  expect(screen.getByTestId("booking-confirmed")).not.toHaveTextContent("until the owner approves");
  expect(screen.getByTestId("booking-confirm-price")).toHaveTextContent("$115.00");
  expect(screen.queryByText("View My Jobs")).not.toBeInTheDocument();
});

test("picking another shop opens that shop's booking form", async () => {
  render(<PublicBooking />);
  expect(await screen.findByRole("option", { name: "Jarvis Glass" })).toBeInTheDocument();
  fireEvent.change(screen.getByTestId("owner-shop"), { target: { value: "shop-2" } });
  expect(mockRouter.nav).toHaveBeenCalledWith("/shops/shop-2/book");
});

test("a closed shop stays closed for the owner", async () => {
  api.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/shops/")) {
      return Promise.resolve({ data: {
        ...preferred,
        id: "shop-1",
        booking_open: false,
        booking_message: "Add a card in Settings before booking.",
      } });
    }
    return Promise.resolve({ data: [] });
  });
  render(<PublicBooking />);
  expect(await screen.findByTestId("booking-closed")).toHaveTextContent("Add a card in Settings before booking.");
  expect(screen.queryByTestId("b-date")).not.toBeInTheDocument();
  expect(screen.queryByText(/invoice me/i)).not.toBeInTheDocument();
});
