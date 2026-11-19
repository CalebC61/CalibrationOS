import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { resetPlacesLoader } from "../components/AddressField";

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock("../components/PortalShell", () => ({ children }) => <div>{children}</div>);
jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);

jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn(), post: jest.fn() },
}));

jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn() },
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
  resetPlacesLoader();
  delete window.google;
  delete process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
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

test("a shop that still owes charge terms is sent to accept them, not to replace the card", async () => {
  portalApi.get.mockImplementation((url) => {
    if (String(url).includes("/portal/me")) {
      return Promise.resolve({
        data: {
          shop,
          setup: {
            allowed: false,
            has_card: true,
            accepted: false,
            charge_failed: false,
            suspended: false,
            message: "Accept the charge terms in Settings before booking.",
          },
        },
      });
    }
    return Promise.resolve({ data: [] });
  });
  render(<PortalBook />);
  expect(await screen.findByTestId("booking-closed")).toHaveTextContent("Accept the charge terms in Settings before booking.");
  expect(screen.getByTestId("goto-add-card")).toHaveTextContent("Accept charge terms");
});

test("a shop with no card is still sent to update the card", async () => {
  portalApi.get.mockImplementation((url) => {
    if (String(url).includes("/portal/me")) {
      return Promise.resolve({
        data: {
          shop,
          setup: {
            allowed: false,
            has_card: false,
            accepted: false,
            suspended: false,
            message: "Add a card in Settings before booking. A shop needs a valid card on file.",
          },
        },
      });
    }
    return Promise.resolve({ data: [] });
  });
  render(<PortalBook />);
  expect(await screen.findByTestId("goto-add-card")).toHaveTextContent("Update card");
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

test("editing the prefilled shop address shows suggestions and keeps the service-area check", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const fetchSuggestions = jest.fn(async ({ input }) => ({
    suggestions: [{
      placePrediction: {
        text: { text: input },
        toPlace() {
          return {
            fetchFields: async () => {},
            formattedAddress: "200 Other St, Mesa, AZ 85201, USA",
            id: "ChIJmesa",
            location: { lat: () => 33.42, lng: () => -111.83 },
          };
        },
      },
    }],
  }));
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => ({
        AutocompleteSuggestion: { fetchAutocompleteSuggestions: fetchSuggestions },
      })),
    },
  };

  render(<PortalBook />);
  const address = await screen.findByTestId("b-addr");
  await waitFor(() => expect(address.getAttribute("data-address-mode")).toBe("places"));
  expect(address).toHaveValue(shop.address);
  expect(screen.getByText("In our Phoenix service area.")).toBeInTheDocument();
  expect(fetchSuggestions).not.toHaveBeenCalled();

  fireEvent.change(address, { target: { value: "200 Other St, Mesa, AZ" } });
  expect(screen.queryByText("In our Phoenix service area.")).not.toBeInTheDocument();
  expect(screen.getByTestId("b-date")).toBeDisabled();
  const option = await screen.findByRole("option");
  expect(option).toHaveTextContent("200 Other St, Mesa, AZ");
  expect(fetchSuggestions).toHaveBeenCalledWith(expect.objectContaining({
    input: "200 Other St, Mesa, AZ",
  }));

  await waitFor(() => expect(screen.getByText("In our Phoenix service area.")).toBeInTheDocument());
  expect(portalApi.post).toHaveBeenCalledWith("/geocode", { address: "200 Other St, Mesa, AZ" });
  expect(screen.getByTestId("b-date")).not.toBeDisabled();
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
  expect(screen.queryByTestId("warranty-charge-notice")).not.toBeInTheDocument();
});

test("a redo past 30 days asks before it books and does not book on cancel", async () => {
  portalApi.get.mockImplementation((url) => {
    if (String(url).includes("/portal/me")) {
      return Promise.resolve({ data: { shop, setup: { allowed: true } } });
    }
    if (String(url).includes("/portal/warranty-jobs")) {
      return Promise.resolve({ data: [{
        id: "old-1",
        vehicle: "2020 Honda Civic",
        customer: "Ana Ng",
        completed_on: "2026-10-01",
        warranty_through: "2026-10-31",
      }] });
    }
    return Promise.resolve({ data: [] });
  });

  render(<PortalBook />);
  fireEvent.change(await screen.findByTestId("b-date"), { target: { value: "2026-11-18" } });
  fireEvent.click(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z"));
  fireEvent.click(screen.getByTestId("b-next"));
  fireEvent.click(screen.getByTestId("warranty-redo"));
  fireEvent.change(await screen.findByTestId("warranty-of"), { target: { value: "old-1" } });
  expect(screen.getByTestId("warranty-preview")).toHaveTextContent("Past 30-day warranty — billed normally");
  fireEvent.change(screen.getByTestId("b-ln"), { target: { value: "Ng" } });
  fireEvent.change(screen.getByTestId("b-make"), { target: { value: "Honda" } });
  fireEvent.change(screen.getByTestId("b-model"), { target: { value: "Civic" } });
  fireEvent.click(screen.getByTestId("b-next"));

  expect(await screen.findByTestId("warranty-charge-notice")).toHaveTextContent("charged at full price");
  expect(portalApi.post).not.toHaveBeenCalledWith("/portal/book", expect.anything());

  fireEvent.click(screen.getByTestId("warranty-charge-cancel"));
  expect(screen.queryByTestId("warranty-charge-notice")).not.toBeInTheDocument();
  expect(portalApi.post).not.toHaveBeenCalledWith("/portal/book", expect.anything());

  fireEvent.click(screen.getByTestId("b-next"));
  fireEvent.click(await screen.findByTestId("warranty-charge-continue"));
  await waitFor(() => expect(portalApi.post).toHaveBeenCalledWith("/portal/book", expect.objectContaining({
    warranty_of_job_id: "old-1",
  })));
});

test("picking a business suggestion confirms the street when geocoding the typed name fails", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const street = "496 N 5th St, Phoenix, AZ 85004, USA";
  const typed = "Downtown Phoenix Inc";
  const pending = [];
  portalApi.post.mockImplementation((url, body) => {
    if (String(url).includes("/geocode")) {
      return new Promise((resolve, reject) => {
        pending.push({
          address: body.address,
          reject: () => reject({ response: { data: { detail: "We couldn't find that address, please check it" } } }),
          resolve: () => resolve({ data: { in_metro: true } }),
        });
      });
    }
    if (String(url).includes("/portal/availability")) {
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T16:00:00Z", requires_approval: false }] } });
    }
    return Promise.resolve({ data: {} });
  });
  const fetchSuggestions = jest.fn(async ({ input }) => ({
    suggestions: [{
      placePrediction: {
        text: { text: "SIXT Rent a Car Phoenix Arizona Center" },
        toPlace() {
          return {
            fetchFields: async () => {},
            formattedAddress: `SIXT Rent a Car, ${street}`,
            displayName: { text: "SIXT Rent a Car" },
            id: "ChIJsixt",
            location: { lat: () => 33.453, lng: () => -112.071 },
            addressComponents: [
              { longText: "496", shortText: "496", types: ["street_number"] },
              { longText: "North 5th Street", shortText: "N 5th St", types: ["route"] },
              { longText: "Phoenix", shortText: "Phoenix", types: ["locality", "political"] },
              { longText: "Arizona", shortText: "AZ", types: ["administrative_area_level_1", "political"] },
              { longText: "85004", shortText: "85004", types: ["postal_code"] },
              { longText: "United States", shortText: "US", types: ["country", "political"] },
              { longText: "SIXT Rent a Car", shortText: "SIXT Rent a Car", types: ["establishment", "point_of_interest"] },
            ],
          };
        },
      },
    }],
  }));
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => ({
        AutocompleteSuggestion: { fetchAutocompleteSuggestions: fetchSuggestions },
      })),
    },
  };

  render(<PortalBook />);
  const address = await screen.findByTestId("b-addr");
  await waitFor(() => expect(address.getAttribute("data-address-mode")).toBe("places"));
  fireEvent.change(address, { target: { value: "Dow" } });
  await waitFor(() => expect(fetchSuggestions).toHaveBeenCalledWith(expect.objectContaining({ input: "Dow" })));
  fireEvent.change(address, { target: { value: typed } });
  await waitFor(() => expect(fetchSuggestions).toHaveBeenLastCalledWith(expect.objectContaining({ input: typed })));
  await waitFor(() => expect(pending.some((call) => call.address === typed)).toBe(true));

  fireEvent.click(await screen.findByRole("option"));
  await waitFor(() => expect(address).toHaveValue(street));
  await act(async () => {
    pending.splice(0).forEach((call) => call.reject());
  });

  expect(screen.queryByText("We couldn't find that address, please check it")).not.toBeInTheDocument();
  expect(screen.getByText("In our Phoenix service area.")).toBeInTheDocument();
  expect(screen.getByTestId("b-date")).not.toBeDisabled();
  expect(address).toHaveValue(street);
});

test("a business name does not show a geocode error while suggestions are open", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const typed = "Downtown Phoenix Inc";
  portalApi.post.mockImplementation((url) => {
    if (String(url).includes("/geocode")) {
      return Promise.reject({ response: { data: { detail: "We couldn't find that address, please check it" } } });
    }
    return Promise.resolve({ data: {} });
  });
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => ({
        AutocompleteSuggestion: {
          fetchAutocompleteSuggestions: jest.fn(async ({ input }) => ({
            suggestions: [{
              placePrediction: {
                text: { text: input },
                toPlace() {
                  return {
                    fetchFields: async () => {},
                    formattedAddress: "1 E Washington St, Phoenix, AZ 85004, USA",
                    id: "ChIJdowntown",
                    location: { lat: () => 33.448, lng: () => -112.074 },
                  };
                },
              },
            }],
          })),
        },
      })),
    },
  };

  render(<PortalBook />);
  const address = await screen.findByTestId("b-addr");
  await waitFor(() => expect(address.getAttribute("data-address-mode")).toBe("places"));
  fireEvent.change(address, { target: { value: typed } });
  expect(await screen.findByRole("option")).toHaveTextContent(typed);
  await waitFor(() => expect(portalApi.post).toHaveBeenCalledWith("/geocode", { address: typed }));
  expect(screen.queryByText("We couldn't find that address, please check it")).not.toBeInTheDocument();
  expect(screen.getByRole("listbox")).toBeInTheDocument();

  fireEvent.blur(address);
  expect(await screen.findByText("We couldn't find that address, please check it")).toBeInTheDocument();
  expect(screen.getByTestId("b-date")).toBeDisabled();
});

test("a nonsense address shows the geocode error on blur", async () => {
  const typed = "zzzz qqqq nowhere 99999";
  portalApi.post.mockImplementation((url) => {
    if (String(url).includes("/geocode")) {
      return Promise.reject({ response: { data: { detail: "We couldn't find that address, please check it" } } });
    }
    return Promise.resolve({ data: {} });
  });

  render(<PortalBook />);
  const address = await screen.findByTestId("b-addr");
  fireEvent.change(address, { target: { value: typed } });
  await waitFor(() => expect(portalApi.post).toHaveBeenCalledWith("/geocode", { address: typed }));
  expect(screen.queryByText("We couldn't find that address, please check it")).not.toBeInTheDocument();

  fireEvent.blur(address);
  expect(await screen.findByText("We couldn't find that address, please check it")).toBeInTheDocument();
  expect(screen.getByTestId("b-date")).toBeDisabled();
});

test("an unreadable date is not sent and does not show Invalid date", async () => {
  render(<PortalBook />);
  const input = await screen.findByTestId("b-date");
  fireEvent.change(input, { target: { value: "Invalid date" } });
  fireEvent.change(input, { target: { value: "not-a-date" } });
  expect(portalApi.post).not.toHaveBeenCalledWith("/portal/availability", expect.anything());
  expect(screen.queryByText("Invalid date")).not.toBeInTheDocument();
  expect(screen.queryByTestId("portal-slots-message")).not.toBeInTheDocument();
  expect(screen.getByTestId("b-next")).toBeDisabled();
  expect(input).toHaveValue("");
});

test("a date set on the input element loads that day", async () => {
  render(<PortalBook />);
  const input = await screen.findByTestId("b-date");
  expect(input).toHaveAttribute("min", "2026-11-18");
  expect(input).toHaveAttribute("max", "2026-12-09");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => {
    setter.call(input, "2026-11-18");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z")).toBeInTheDocument();
  expect(input).toHaveValue("2026-11-18");
  expect(portalApi.post).toHaveBeenCalledWith("/portal/availability", expect.objectContaining({
    date: "2026-11-18",
    job_address: shop.address,
  }));

  await act(async () => {
    setter.call(input, "11/18/2026");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const dates = portalApi.post.mock.calls
    .filter((call) => String(call[0]).includes("/portal/availability"))
    .map((call) => call[1].date);
  expect(dates.every((day) => /^\d{4}-\d{2}-\d{2}$/.test(day))).toBe(true);
  expect(dates).not.toContain("11/18/2026");
  expect(dates).not.toContain("Invalid date");
  expect(screen.queryByText("Invalid date")).not.toBeInTheDocument();
});

test("a past-date message clears once a later valid date has slots", async () => {
  const pastResponses = [];
  portalApi.post.mockImplementation((url, body) => {
    if (String(url).includes("/portal/availability")) {
      if (body.date === "2020-01-01") {
        return new Promise((resolve) => {
          pastResponses.push(resolve);
        });
      }
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T16:00:00Z", requires_approval: false }] } });
    }
    return Promise.resolve({ data: {} });
  });
  render(<PortalBook />);
  const input = await screen.findByTestId("b-date");

  fireEvent.change(input, { target: { value: "2020-01-01" } });
  await act(async () => {
    pastResponses.shift()({ data: { slots: [], message: "That date is in the past." } });
  });
  expect(screen.getByTestId("portal-slots-message")).toHaveTextContent("That date is in the past.");

  fireEvent.change(input, { target: { value: "2026-11-18" } });
  expect(screen.queryByText("That date is in the past.")).not.toBeInTheDocument();
  expect(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z")).toBeInTheDocument();

  fireEvent.change(input, { target: { value: "2020-01-01" } });
  fireEvent.change(input, { target: { value: "2026-11-18" } });
  expect(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z")).toBeInTheDocument();
  await act(async () => {
    pastResponses.shift()({ data: { slots: [], message: "That date is in the past." } });
  });
  expect(screen.queryByText("That date is in the past.")).not.toBeInTheDocument();
  expect(screen.getByTestId("b-slot-2026-11-18T16:00:00Z")).toBeInTheDocument();
  expect(screen.getByTestId("b-next")).toBeDisabled();
});

test("a shop still sees pending approval, the warranty redo, and invoice me", async () => {
  portalApi.post.mockImplementation((url) => {
    if (String(url).includes("/portal/availability")) {
      return Promise.resolve({ data: { slots: [{ start: "2026-11-18T14:00:00Z", requires_approval: true }] } });
    }
    return Promise.resolve({ data: {} });
  });
  render(<PortalBook />);
  fireEvent.change(await screen.findByTestId("b-date"), { target: { value: "2026-11-18" } });
  const slot = await screen.findByTestId("b-slot-2026-11-18T14:00:00Z");
  expect(slot).toHaveTextContent("Pending approval");
  fireEvent.click(slot);
  fireEvent.click(screen.getByTestId("b-next"));
  expect(screen.getByTestId("approval-note")).toHaveTextContent("This time is held until the owner approves it.");
  expect(screen.getByTestId("invoice-instead")).toBeInTheDocument();
  expect(screen.getByText("Please invoice me instead")).toBeInTheDocument();
  expect(screen.getByTestId("warranty-redo")).toBeInTheDocument();
  expect(screen.getByTestId("b-next")).toHaveTextContent("Request this time");
  expect(screen.queryByTestId("owner-custom-time")).not.toBeInTheDocument();
  expect(screen.queryByTestId("owner-shop")).not.toBeInTheDocument();
});
