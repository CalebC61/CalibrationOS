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
export function redoIsFree(warrantyThroughDay, redoDay) {
  if (!warrantyThroughDay || !redoDay) return false;
  return redoDay <= warrantyThroughDay;
}

/** Phoenix day 30 days after the original completion. That day is still free. */
export function warrantyThrough(completedOn) {
  if (!completedOn || !/^\d{4}-\d{2}-\d{2}$/.test(completedOn)) return "";
  const [year, month, day] = completedOn.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + 30);
  return date.toISOString().slice(0, 10);
}

export function isFreeWarranty(job) {
  return Boolean(job && job.warranty_eligible && (job.warranty_of_job_id || job.warranty_label));
}

/** A linked redo whose Phoenix day is after the 30-day window. */
export function redoWouldBeBilled(job, redoDay) {
  if (!job?.warranty_of_job_id || !redoDay) return false;
  const through = job.warranty_through || warrantyThrough(job.warranty_original_completed_on);
  if (!through) return job.warranty_eligible === false;
  return !redoIsFree(through, redoDay);
}
