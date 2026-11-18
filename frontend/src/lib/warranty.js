/** Labels the server stores on a warranty redo. Keep these strings in step with backend/warranty.py. */
export const WARRANTY_FREE = "Warranty redo (free)";
export const WARRANTY_BILLED = "Past 30-day warranty — billed normally";

export function warrantyText(job) {
  if (!job || (!job.warranty_of_job_id && !job.warranty_label)) return null;
  if (job.warranty_label) return job.warranty_label;
  return job.warranty_eligible ? WARRANTY_FREE : WARRANTY_BILLED;
}

export function formatCivilDate(isoDay) {
  if (!isoDay || !/^\d{4}-\d{2}-\d{2}$/.test(isoDay)) return isoDay || "";
  const [year, month, day] = isoDay.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function warrantyOptionLabel(row) {
  if (!row) return "";
  return [row.vehicle, row.customer, formatCivilDate(row.completed_on)].filter(Boolean).join(" · ");
}

/** True when the redo's Phoenix day is on or before the original job's warranty_through day. */
export function redoIsFree(warrantyThrough, redoDay) {
  if (!warrantyThrough || !redoDay) return false;
  return redoDay <= warrantyThrough;
}
