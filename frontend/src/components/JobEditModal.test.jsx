import { fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("../lib/api", () => ({
  api: { get: jest.fn(), patch: jest.fn() },
}));

import JobEditModal from "./JobEditModal";
import { api } from "../lib/api";

const job = {
  id: "job-1",
  shop_id: "shop-1",
  job_address: "1 Main St, Gilbert, AZ",
  customer_last_name: "Ng",
  customer_first_name: "Ana",
  vehicle_year: 2020,
  vehicle_make: "Honda",
  vehicle_model: "Civic",
  calibration_type: "static",
  price: 125,
  scheduled_start: "2026-11-18T17:00:00Z",
  zone: "east",
  notes: "",
};

const past = {
  id: "old-1",
  vehicle: "2019 Toyota Camry",
  customer: "Luis Martinez",
  completed_on: "2026-11-01",
  warranty_through: "2026-12-01",
};

beforeEach(() => {
  api.get.mockResolvedValue({ data: [past] });
  api.patch.mockResolvedValue({ data: {} });
});

test("the owner can link a completed job as a warranty redo", async () => {
  render(<JobEditModal open job={job} onClose={() => {}} onDone={() => {}} />);
  expect(await screen.findByRole("option", { name: /2019 Toyota Camry · Luis Martinez/ })).toBeInTheDocument();
  fireEvent.change(screen.getByTestId("edit-warranty"), { target: { value: "old-1" } });
  fireEvent.click(screen.getByTestId("edit-save"));
  await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
    "/jobs/job-1",
    expect.objectContaining({ warranty_of_job_id: "old-1" }),
  ));
  const body = api.patch.mock.calls[0][1];
  expect(body.price).toBeUndefined();
});

test("clearing the warranty link sends a null id", async () => {
  render(<JobEditModal open job={{ ...job, warranty_of_job_id: "old-1", price: 0 }} onClose={() => {}} onDone={() => {}} />);
  await screen.findByRole("option", { name: /2019 Toyota Camry/ });
  fireEvent.change(screen.getByTestId("edit-warranty"), { target: { value: "" } });
  fireEvent.click(screen.getByTestId("edit-save"));
  await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
    "/jobs/job-1",
    expect.objectContaining({ warranty_of_job_id: null }),
  ));
});

test("a shop edit does not offer the warranty link", () => {
  render(<JobEditModal open shopEdit job={job} client={{ get: jest.fn(), patch: jest.fn() }} onClose={() => {}} />);
  expect(screen.queryByTestId("edit-warranty")).not.toBeInTheDocument();
});
