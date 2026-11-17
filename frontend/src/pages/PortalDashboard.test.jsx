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

test("a shop with no jobs sees an empty day instead of a valley map", async () => {
  show({ own: [], date: "2026-11-18" });
  expect(await screen.findByTestId("portal-day-empty")).toHaveTextContent("No jobs on this day");
  expect(screen.queryByTestId("portal-map")).not.toBeInTheDocument();
  expect(screen.queryByText(/other shops/i)).not.toBeInTheDocument();
});

test("the day map does not draw another shop's stop", async () => {
  show({
    own: [{
      id: "job-1",
      job_lat: 33.45,
      job_lng: -112.07,
      scheduled_start: "2026-11-18T16:00:00+00:00",
      scheduled_end: "2026-11-18T17:00:00+00:00",
      status: "booked",
      vehicle_year: 2022,
      vehicle_make: "Honda",
      vehicle_model: "Civic",
      calibration_label: "Static",
      customer_last_name: "Ng",
      price: 125,
    }],
    others: [{
      id: "job-secret",
      job_lat: 33.111111,
      job_lng: -111.222222,
      scheduled_start: "2026-11-18T16:00:00+00:00",
      drive_minutes_from_you: 40,
    }],
  });
  expect(await screen.findByTestId("portal-own-job-job-1")).toBeInTheDocument();
  expect(screen.getAllByTestId("map-marker")).toHaveLength(1);
  expect(screen.queryByText(/other shops/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/min drive/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/job-secret/)).not.toBeInTheDocument();
});
