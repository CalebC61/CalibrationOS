/** A card charge that already succeeded. A free warranty redo is not a payment. */
export function jobLooksPaid(job) {
  if (!job || job.warranty_eligible) return false;
  return Boolean(job.charged_at)
    || job.payment_status === "paid"
    || job.payment_status === "succeeded"
    || job.invoice_status === "paid";
}

/** Keep the newer job when a slow or cached list arrives after a draft was filed. */
export function fresherJob(current, incoming) {
  if (!incoming) return current;
  if (!current) return incoming;
  const currentAt = current.updated_at || "";
  const incomingAt = incoming.updated_at || "";
  if (currentAt && incomingAt && incomingAt < currentAt) return current;
  const merged = { ...current, ...incoming };
  const laterFailure = incoming.payment_status === "payment_failed"
    && incomingAt
    && (!currentAt || incomingAt >= currentAt);
  if (jobLooksPaid(current) && !jobLooksPaid(incoming) && !laterFailure) {
    merged.charged_at = current.charged_at;
    merged.charged_amount = current.charged_amount;
    merged.payment_status = current.payment_status;
    if (current.invoice_status === "paid") merged.invoice_status = "paid";
  }
  return merged;
}

export function mergeJobList(current, incoming) {
  return (incoming || []).map(job => fresherJob(
    (current || []).find(item => item.id === job.id),
    job,
  ));
}
