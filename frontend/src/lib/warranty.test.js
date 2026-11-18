import { formatCivilDate, redoIsFree, redoWouldBeBilled, warrantyOptionLabel, warrantyText, warrantyThrough } from "./warranty";

test("warranty copy follows the server label", () => {
  expect(warrantyText(null)).toBeNull();
  expect(warrantyText({ price: 125 })).toBeNull();
  expect(warrantyText({
    warranty_of_job_id: "old",
    warranty_eligible: true,
    warranty_label: "Warranty redo (free)",
  })).toBe("Warranty redo (free)");
  expect(warrantyText({
    warranty_of_job_id: "old",
    warranty_eligible: false,
    warranty_label: "Past 30-day warranty — billed normally",
  })).toBe("Past 30-day warranty — billed normally");
});

test("a redo on the warranty-through day is free and the next day is billed", () => {
  expect(warrantyThrough("2026-11-01")).toBe("2026-12-01");
  expect(redoIsFree("2026-12-01", "2026-12-01")).toBe(true);
  expect(redoIsFree("2026-12-01", "2026-12-02")).toBe(false);
  expect(redoWouldBeBilled({
    warranty_of_job_id: "old",
    warranty_original_completed_on: "2026-11-01",
  }, "2026-12-02")).toBe(true);
  expect(redoWouldBeBilled({
    warranty_of_job_id: "old",
    warranty_original_completed_on: "2026-11-01",
  }, "2026-12-01")).toBe(false);
  expect(formatCivilDate("2026-11-01")).toBe("Nov 1, 2026");
  expect(warrantyOptionLabel({
    vehicle: "2020 Honda Civic",
    customer: "Ana Ng",
    completed_on: "2026-11-01",
  })).toBe("2020 Honda Civic · Ana Ng · Nov 1, 2026");
});
