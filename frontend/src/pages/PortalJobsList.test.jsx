import { render, screen } from "@testing-library/react";

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
  };
}, { virtual: true });

jest.mock("../components/PortalShell", () => ({ children }) => children);

jest.mock("../lib/api", () => ({
  jobStatusLabel: (status) => status || "",
}));

jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn() },
}));

import PortalJobsList from "./PortalJobsList";
import { portalApi } from "../lib/portalApi";

test("My Jobs shows the warranty badge on a redo", async () => {
  portalApi.get.mockResolvedValue({ data: [
    {
      id: "free-1",
      status: "booked",
      vehicle_year: 2020,
      vehicle_make: "Honda",
      vehicle_model: "Civic",
      calibration_label: "Static",
      customer_last_name: "Ng",
      scheduled_start: "2026-11-18T17:00:00Z",
      price: 0,
      warranty_of_job_id: "old-1",
      warranty_eligible: true,
      warranty_label: "Warranty redo (free)",
    },
    {
      id: "billed-1",
      status: "booked",
      vehicle_year: 2019,
      vehicle_make: "Toyota",
      vehicle_model: "Camry",
      calibration_label: "Dynamic",
      customer_last_name: "Reed",
      scheduled_start: "2026-11-18T18:00:00Z",
      price: 125,
      warranty_of_job_id: "old-2",
      warranty_eligible: false,
      warranty_label: "Past 30-day warranty — billed normally",
    },
  ] });
  render(<PortalJobsList />);
  expect(await screen.findByTestId("warranty-badge-free-1")).toHaveTextContent("Warranty redo (free)");
  expect(screen.getByTestId("warranty-badge-billed-1")).toHaveTextContent("Past 30-day warranty — billed normally");
});
