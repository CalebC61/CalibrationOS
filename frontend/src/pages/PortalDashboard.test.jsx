import { render, screen } from "@testing-library/react";

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
  };
}, { virtual: true });

jest.mock("leaflet", () => ({
  divIcon: () => ({}),
  latLngBounds: () => ({}),
}));

jest.mock("react-leaflet", () => {
  const React = require("react");
  return {
    MapContainer: ({ children }) => React.createElement("div", { "data-testid": "portal-map-canvas" }, children),
    Marker: ({ children }) => React.createElement("div", { "data-testid": "map-marker" }, children),
    Tooltip: ({ children }) => React.createElement("div", null, children),
    useMap: () => ({ setView() {}, fitBounds() {} }),
  };
});

jest.mock("../components/DarkBasemap", () => () => null);
jest.mock("../components/PortalShell", () => ({ children }) => children);

jest.mock("../lib/api", () => ({
  phoenixTodayStr: () => "2026-11-18",
  jobStatusLabel: (status) => status || "",
}));

jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn() },
}));

import PortalDashboard from "./PortalDashboard";
import { portalApi } from "../lib/portalApi";

function show(day) {
  portalApi.get.mockImplementation((url) => {
    if (String(url).includes("day-map")) return Promise.resolve({ data: day });
    return Promise.resolve({ data: { setup: null } });
  });
  return render(<PortalDashboard />);
}

test("an empty route shows a note instead of a valley map", async () => {
  show({ own: [], others: [], date: "2026-11-18" });
  expect(await screen.findByTestId("portal-day-empty")).toHaveTextContent("No stops on this day");
  expect(screen.queryByTestId("portal-map")).not.toBeInTheDocument();
});

test("other stops stay on the map as a time window", async () => {
  show({
    own: [{
      id: "job-1",
      route_order: 2,
      job_lat: 33.45,
      job_lng: -112.07,
      scheduled_start: "2026-11-18T16:00:00+00:00",
      scheduled_end: "2026-11-18T17:00:00+00:00",
      status: "booked",
      vehicle_year: 2022,
      vehicle_make: "Honda",
      vehicle_model: "Civic",
      job_address: "1 E Washington St",
      calibration_label: "Static",
      customer_last_name: "Ng",
      price: 125,
    }],
    others: [{
      route_order: 1,
      job_lat: 33.111,
      job_lng: -111.222,
      arrival_start: "2026-11-18T15:00:00+00:00",
      arrival_end: "2026-11-18T16:00:00+00:00",
    }],
  });
  expect(await screen.findByTestId("portal-own-job-job-1")).toBeInTheDocument();
  expect(screen.getAllByTestId("map-marker")).toHaveLength(2);
  expect(screen.getByTestId("portal-other-stop-1")).toHaveTextContent("Stop 1");
  expect(screen.getByTestId("portal-map-legend")).toHaveTextContent("time window only");
  expect(screen.getAllByText(/Honda/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/other shops/i)).not.toBeInTheDocument();
});

test("a free warranty redo is marked on the shop day list", async () => {
  show({
    own: [{
      id: "job-free",
      route_order: 1,
      job_lat: 33.45,
      job_lng: -112.07,
      scheduled_start: "2026-11-18T16:00:00+00:00",
      status: "booked",
      vehicle_year: 2020,
      vehicle_make: "Honda",
      vehicle_model: "Civic",
      job_address: "1 E Washington St",
      calibration_label: "Static",
      customer_last_name: "Ng",
      price: 0,
      warranty_of_job_id: "old-1",
      warranty_eligible: true,
      warranty_label: "Warranty redo (free)",
    }],
    others: [],
  });
  const banner = await screen.findByTestId("warranty-badge-job-free");
  expect(banner).toHaveTextContent("Warranty");
  expect(banner).toHaveTextContent("not charged");
});

test("a shop with no jobs of its own still sees the rest of the route", async () => {
  show({
    own: [],
    others: [{
      route_order: 1,
      job_lat: 33.111,
      job_lng: -111.222,
      arrival_start: "2026-11-18T15:00:00+00:00",
      arrival_end: "2026-11-18T16:00:00+00:00",
    }],
  });
  expect(await screen.findByTestId("portal-map")).toBeInTheDocument();
  expect(screen.queryByTestId("portal-day-empty")).not.toBeInTheDocument();
  expect(screen.getByText(/No jobs from your shop on this day/)).toBeInTheDocument();
});
